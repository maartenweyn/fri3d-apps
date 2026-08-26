"""Huis: de logica achter het bedieningspaneel. Geen LVGL.

De app kent **geen enkele entiteit en geen enkele service**. Home Assistant zet
retained op `home/badges/<naam>/control_panel` welke knoppen deze badge heeft,
en de badge tekent wat er binnenkomt. Een druk zet het id van die knop op
`home/badges/<naam>/control_press`, waar een automatisatie het juiste script van
maakt.

**Waarom de badge geen servicenaam stuurt.** Een payload met
`{"service": "light.turn_off", "target": ...}` scheelt werk in Home Assistant en
maakt tegelijk van brokerreferenties het recht om elke service in huis aan te
roepen. Dit toestel ligt op een aanrecht en gaat mee op kamp. De vertaling van
id naar script hoort op één plek te staan, en dat is dezelfde plek waar het
dashboard ook langsgaat.

**Waarom er geen service in het manifest staat.** Berichtjes heeft er een omdat
een bericht ongevraagd binnenkomt en dan moet er ook geluisterd worden als er
een spel op het scherm staat. Een knoppenpaneel is het omgekeerde: er gebeurt
alleen iets als er iemand voor staat. Abonneren bij het openen is genoeg, want
een broker levert retained berichten opnieuw aan zodra je je inschrijft. Dat
scheelt een resident abonnement voor een scherm waar niemand naar kijkt, en het
betekent dat een update meteen werkt in plaats van na een herstart.

De brug wordt elke tick opgezocht in `sys.modules` en niet één keer bewaard. De
volgorde waarin apps laden ligt niet vast, en een app die de brug één keer mist
zou hem nooit meer vinden.
"""

import json
import sys
import time

APP_FULLNAME = "tech.weyn.homecontrol"
PREFS_APP_ID = APP_FULLNAME

# De app die de verbinding en de identiteit van de badge bezit.
BRIDGE_APP = "tech.weyn.badgecontroller"
BRIDGE_MODULE = "badge_service"


def _mpos(name, *paths):
    import mpos
    if hasattr(mpos, name):
        return getattr(mpos, name)
    for path in paths:
        try:
            mod = __import__(path, None, None, (name,))
            if hasattr(mod, name):
                return getattr(mod, name)
        except Exception:
            pass
    raise ImportError("homecontrol: no %s in mpos or %s" % (name, paths))


SharedPreferences = _mpos("SharedPreferences", "mpos.config")

# Achtervoegsels, geen volledige topics: de brug plakt er `home/badges/<naam>/`
# voor en schrijft ons bij een hernoeming vanzelf opnieuw in. Een eigen
# `control_`-voorvoegsel zodat `msg`, `ack`, `buttons` en `send` van Berichtjes
# vrij blijven; de abonneelijst van de brug is er een voor alle apps samen.
#
# **Geen schuine streep in een achtervoegsel.** `badge_service.topic()` laat
# alles met een `/` erin staan zoals het is, want zo hangt het weer aan een
# gedeeld topic. Een achtervoegsel `control/panel` zou dus het letterlijke topic
# `control/panel` worden, zonder de naam van de badge, en dan luistert elke
# badge naar hetzelfde.
SUFFIX_PANEL = "control_panel"    # retained, HA -> badge
SUFFIX_STATE = "control_state"    # retained, HA -> badge
SUFFIX_PRESS = "control_press"    # badge -> HA
SUFFIX_ACK = "control_ack"        # HA -> badge

# Zes past er op 320 bij 240 in twee kolommen van drie, met knoppen van 152 bij
# 60. Meer tonen betekent kleinere knoppen, en dat is precies hoe een knop een
# knop wordt die je niet raakt. Een zevende hoort op een tweede paneel, niet in
# een kleiner vakje.
MAX_BUTTONS = 6
LABEL_MAX = 18
STATE_MAX = 12
PANEL_CACHE_MAX = 2000
DEFAULT_TITLE = "Huis"

# Een druk op "alarm aan" wil je niet per ongeluk doen. Twee tikken binnen deze
# tijd, anders vergeet de knop dat hij aangetikt was.
CONFIRM_SECONDS = 6

# Zolang wacht een knop op bewijs dat er iets gebeurd is. Daarna staat er dat
# het niet bevestigd is. Vier seconden is te kort voor een dakkoepel die vier
# seconden loopt en dan pas zijn positie meldt.
PENDING_SECONDS = 10

# Hoe lang de statusregel blijft staan.
FLASH_SECONDS = 4

# --- gedeelde toestand, gelezen door de activity ----------------------------
buttons = []
panel_title = DEFAULT_TITLE
panel_seq = 0            # loopt op bij elke wijziging, zodat het scherm weet
                         # dat het opnieuw moet tekenen
states = {}              # sleutel -> {"text": str, "color": str of None}
state_seq = 0
pending = {}             # knop-id -> {"seq", "until", "key", "was"}
results = {}             # knop-id -> {"text", "ok", "until"}
press_seq = 0
press_error = None
connected = False
last_error = None
BADGE_NAME = "badge"


def bridge():
    """De brug, of None.

    Geen `import badge_service`: de map van die app staat niet op `sys.path` van
    deze app. Alle apps draaien wel in dezelfde MicroPython-VM met één
    `sys.modules`, dus opzoeken werkt wel."""
    return sys.modules.get(BRIDGE_MODULE)


def bridge_missing_reason():
    """Waarom er geen brug is, in woorden voor op het scherm."""
    if bridge() is not None:
        return None
    return "Badge-app draait niet"


def sync_bridge():
    """De geleende toestand overnemen: naam en verbinding."""
    global BADGE_NAME, connected, last_error
    b = bridge()
    if b is None:
        connected = False
        last_error = bridge_missing_reason()
        return None
    BADGE_NAME = b.BADGE_NAME
    connected = bool(b.connected)
    last_error = b.last_error
    return b


def _text(payload):
    """Een payload als str, of "" als hij niet te lezen is."""
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = payload.decode("utf-8")
        except Exception:
            return ""
    return (payload or "").strip()


# --- het paneel -------------------------------------------------------------

def normalize_button(raw):
    """Eén knop uit de configuratie, of None als er niets bruikbaars in staat.

    Streng zijn loont: dit komt van het netwerk, komt op een scherm terecht en
    gaat daarna weer het netwerk op. Een knop zonder id doet stilletjes niets,
    en die tonen we liever niet.
    """
    if not isinstance(raw, dict):
        return None
    ident = str(raw.get("id") or "").strip()
    if not ident:
        return None
    label = str(raw.get("label") or "").strip() or ident
    button = {"id": ident, "label": label[:LABEL_MAX]}
    if raw.get("confirm"):
        button["confirm"] = True
    # Sleutel, teken en kleur zijn alle drie optioneel en alle drie zonder
    # betekenis voor deze app: hij tekent wat er staat.
    for key in ("state", "symbol", "initial", "color"):
        value = raw.get(key)
        if value:
            button[key] = str(value).strip()
    return button


def parse_panel(payload):
    """(knoppen, titel) uit een payload, of wat er stond als hij stuk is.

    Een lege retained payload is hoe MQTT "vergeet dit" zegt, en die wist het
    paneel. Een payload die geen JSON is, is iets anders: dan is er ergens een
    fout gemaakt, en een werkend paneel weggooien om een verkeerde publicatie
    helpt niemand.
    """
    text = _text(payload)
    if not text:
        return [], DEFAULT_TITLE
    try:
        data = json.loads(text)
    except Exception as e:
        print("homecontrol: paneel niet te lezen:", e)
        return buttons, panel_title
    heading = DEFAULT_TITLE
    if isinstance(data, dict):
        heading = str(data.get("title") or DEFAULT_TITLE).strip() or DEFAULT_TITLE
        data = data.get("buttons")
    if not isinstance(data, (list, tuple)):
        print("homecontrol: paneel zonder lijst")
        return buttons, panel_title
    out = []
    for raw in data:
        button = normalize_button(raw)
        if button is not None:
            out.append(button)
        if len(out) >= MAX_BUTTONS:
            break
    return out, heading


def set_panel(payload, remember=True):
    """Nieuwe knopconfiguratie toepassen. True als er iets veranderde."""
    global buttons, panel_title, panel_seq
    items, heading = parse_panel(payload)
    if items == buttons and heading == panel_title:
        return False
    buttons = items
    panel_title = heading
    panel_seq += 1
    if remember:
        remember_panel(payload)
    print("homecontrol: %d knoppen" % len(buttons))
    return True


def remember_panel(payload):
    """Bewaren zodat het paneel er meteen staat na een herstart.

    De broker levert retained berichten opnieuw aan, dus strikt nodig is dit
    niet. Wel prettig: anders is het scherm leeg tot de badge verbonden is, en
    dat duurt op een koude start langer dan iemand geduld heeft.
    """
    text = _text(payload)
    if len(text) > PANEL_CACHE_MAX:
        return False
    try:
        editor = SharedPreferences(PREFS_APP_ID).edit()
        editor.put_string("panel_json", text)
        editor.commit()
        return True
    except Exception as e:
        print("homecontrol: kon het paneel niet bewaren:", e)
        return False


def load_cached_panel():
    """Wat er de vorige keer stond, voor de broker antwoordt."""
    try:
        text = SharedPreferences(PREFS_APP_ID).get_string("panel_json", "")
    except Exception as e:
        print("homecontrol: kon het paneel niet lezen:", e)
        return False
    if not text:
        return False
    return set_panel(text, remember=False)


# --- de toestand ------------------------------------------------------------
# Home Assistant stuurt tekst, geen entiteitstoestand. "dicht", "5%", "aan
# (weg)": wat er op de knop hoort te staan weet HA en niet de badge. Zo hoeft
# deze app nooit te weten wat armed_home betekent, en verandert er hier niets
# als er een rolluik bijkomt.

def parse_state(payload):
    """De toestandssleutels uit een payload, of wat er stond als hij stuk is.

    Een waarde mag een string zijn of een dict met `text` en `color`. Een string
    is het gewone geval; de dict is er voor wie een knop wil laten oplichten.
    """
    text = _text(payload)
    if not text:
        return {}
    try:
        data = json.loads(text)
    except Exception as e:
        print("homecontrol: toestand niet te lezen:", e)
        return states
    if not isinstance(data, dict):
        print("homecontrol: toestand is geen object")
        return states
    out = {}
    for key in data:
        value = data[key]
        color = None
        if isinstance(value, dict):
            color = value.get("color")
            value = value.get("text")
        if value is None:
            continue
        if isinstance(value, bool):
            value = "aan" if value else "uit"
        out[str(key)] = {"text": str(value).strip()[:STATE_MAX],
                         "color": str(color).strip() if color else None}
    return out


def set_state(payload):
    """Nieuwe toestand toepassen. True als er iets veranderde."""
    global states, state_seq
    fresh = parse_state(payload)
    if fresh == states:
        return False
    states = fresh
    state_seq += 1
    _settle(time.time())
    return True


def state_of(button):
    """{"text", "color"} voor een knop, of None als hij geen sleutel heeft."""
    if not isinstance(button, dict):
        return None
    key = button.get("state")
    if not key:
        return None
    return states.get(key)


def _state_text(button):
    entry = state_of(button)
    return entry.get("text") if entry else None


# --- drukken ----------------------------------------------------------------

def press(button):
    """Het id van een knop op het press-topic. False als het niet wegkwam.

    Bewust niet vasthouden zoals Berichtjes een bevestiging wel vasthoudt. Een
    bevestiging blijft waar tot ze aankomt; "licht beneden uit" is vijf minuten
    later niet meer wat iemand bedoelde, en een commando dat later alsnog
    aankomt doet 's nachts het licht uit. Zeg dat het mislukt is en laat degene
    die voor de badge staat opnieuw drukken.
    """
    global press_seq, press_error
    if not isinstance(button, dict):
        press_error = "geen knop"
        return False
    ident = str(button.get("id") or "").strip()
    if not ident:
        press_error = "knop zonder id"
        return False
    b = bridge()
    if b is None:
        press_error = bridge_missing_reason()
        return False
    press_seq += 1
    payload = json.dumps({"id": ident, "seq": press_seq, "from": BADGE_NAME})
    if not b.publish(SUFFIX_PRESS, payload):
        press_error = "geen verbinding"
        return False
    press_error = None
    now = time.time()
    pending[ident] = {"seq": press_seq, "until": now + PENDING_SECONDS,
                      "key": button.get("state"), "was": _state_text(button)}
    results.pop(ident, None)
    print("homecontrol: gedrukt", ident)
    return True


def on_ack(payload):
    """Home Assistant zegt dat het gelukt is, of niet.

    De ack is de enige bevestiging die een knop zonder toestandssleutel kan
    krijgen: een scene heeft geen toestand om naar te kijken.
    """
    text = _text(payload)
    if not text:
        return False
    try:
        data = json.loads(text)
    except Exception as e:
        print("homecontrol: ack niet te lezen:", e)
        return False
    if not isinstance(data, dict):
        return False
    ident = str(data.get("id") or "").strip()
    if not ident:
        return False
    wait = pending.get(ident)
    seq = data.get("seq")
    if wait is not None and seq is not None and seq != wait.get("seq"):
        # Een antwoord op een vorige druk. Laat de huidige wachten.
        return False
    ok = data.get("ok")
    ok = True if ok is None else bool(ok)
    note = str(data.get("text") or "").strip()
    if not note:
        # Een ack zonder tekst pakt de toestand die er nu staat. Zo hoeft Home
        # Assistant de vertaling van toestand naar tekst niet twee keer te
        # schrijven, een keer voor het toestandsbericht en een keer voor de ack.
        for known in buttons:
            if known.get("id") == ident:
                note = _state_text(known) or ""
                break
    _finish(ident, ok, note or ("gelukt" if ok else "mislukt"))
    return True


def _finish(ident, ok, note, now=None):
    now = time.time() if now is None else now
    pending.pop(ident, None)
    results[ident] = {"ok": bool(ok), "text": note,
                      "until": now + FLASH_SECONDS}


def _settle(now):
    """Knoppen die op een toestandswissel wachtten en die net gezien hebben."""
    for ident in list(pending.keys()):
        wait = pending[ident]
        key = wait.get("key")
        if not key:
            continue
        entry = states.get(key)
        text = entry.get("text") if entry else None
        if text != wait.get("was"):
            _finish(ident, True, text or "gelukt")


def tick(now=None):
    """Wat er verloopt: wachtende knoppen en de statusregel.

    True als er iets veranderd is en het scherm opnieuw moet kijken.
    """
    now = time.time() if now is None else now
    changed = False
    # Eerst opruimen, dan pas verlopen laten. Andersom zou een knop die net
    # afgemeld wordt in dezelfde tick alweer weg zijn.
    for ident in list(results.keys()):
        if now >= results[ident].get("until", 0):
            results.pop(ident, None)
            changed = True
    for ident in list(pending.keys()):
        if now >= pending[ident].get("until", 0):
            # Niet liegen. Er is geen bewijs dat er iets gebeurd is, dus staat
            # er dat er geen bewijs is. Vaak is de knop wel aangekomen en heeft
            # Home Assistant alleen niets teruggezegd; dat is dan iets om daar
            # op te lossen en niet iets om hier groen te kleuren.
            _finish(ident, False, "geen antwoord", now)
            changed = True
    return changed


def status_of(button):
    """("wacht" | "ok" | "fout" | None, tekst) voor een knop."""
    if not isinstance(button, dict):
        return None, None
    ident = button.get("id")
    if ident in pending:
        return "wacht", None
    done = results.get(ident)
    if done is not None:
        return ("ok" if done.get("ok") else "fout"), done.get("text")
    return None, None


def reset():
    """Alles wat aan een schermsessie hangt, voor een schone start."""
    pending.clear()
    results.clear()


# --- abonneren --------------------------------------------------------------

def subscribe_all():
    """Meeluisteren, zolang het scherm openstaat.

    Elke tick opnieuw vragen. Het is een woordenboekschrijving als we er al in
    staan, en het is wat een herstart van de brug repareert zonder dat dit
    scherm iets hoeft te merken.
    """
    b = bridge()
    if b is None:
        return False
    b.subscribe(SUFFIX_PANEL, _on_panel)
    b.subscribe(SUFFIX_STATE, _on_state)
    b.subscribe(SUFFIX_ACK, _on_ack)
    return True


def unsubscribe_all():
    b = bridge()
    if b is None:
        return False
    for suffix in (SUFFIX_PANEL, SUFFIX_STATE, SUFFIX_ACK):
        try:
            b.unsubscribe(suffix)
        except Exception:
            pass
    return True


def _on_panel(topic, payload):
    try:
        set_panel(payload)
    except Exception as e:
        print("homecontrol: paneel niet verwerkt:", e)


def _on_state(topic, payload):
    try:
        set_state(payload)
    except Exception as e:
        print("homecontrol: toestand niet verwerkt:", e)


def _on_ack(topic, payload):
    try:
        on_ack(payload)
    except Exception as e:
        print("homecontrol: ack niet verwerkt:", e)
