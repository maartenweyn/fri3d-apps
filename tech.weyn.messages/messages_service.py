"""Berichten voor de Berichtjes-app.

Draait als MicroPythonOS-service op `boot_completed`, zodat er geluisterd blijft
worden welke app er ook op het scherm staat. Bij een bericht plaatst hij een
Notification (het systeem speelt de meldingstoon op de buzzer), laat de LEDs
knipperen tot iemand bevestigt, en haalt het Berichtjes-scherm naar voren.

**De MQTT-verbinding staat hier niet meer in.** Die hoort bij de badge, niet bij
een app: het brokeradres, het wachtwoord, de naam van de badge, de last will, de
batterijsensoren en het toestel-id uit het MAC zijn allemaal eigenschappen van
het toestel. Ze wonen in `tech.weyn.badgecontroller`, en deze module leent daar een
verbinding. Twee MQTT-clients van hetzelfde toestel naar dezelfde broker was
overigens ook geen optie: dat is precies de fout die deze app al een keer gekost
heeft, want een broker gooit de oudste van twee clients met dezelfde id eruit.

De brug wordt elke tick opgezocht in `sys.modules` en niet één keer bewaard. De
volgorde waarin services starten ligt niet vast, en een app die de brug één keer
mist zou hem nooit meer vinden. Is hij er niet, dan zegt het scherm
"geen verbinding", en dat is de waarheid.

De activity leest de globals van deze module rechtstreeks. Service en activity
draaien in hetzelfde MicroPython-proces, dus een gewone import is het hele
verhaal.

Niets hier maakt LVGL-objecten aan: een service heeft geen scherm.
"""

import json
import sys
import time


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
    raise ImportError("messages: no %s in mpos or %s" % (name, paths))


Service = _mpos("Service", "mpos.app.service")
Notification = _mpos("Notification", "mpos.notification", "mpos.ui.notification")
NotificationManager = _mpos("NotificationManager", "mpos.notification",
                            "mpos.ui.notification")
Intent = _mpos("Intent", "mpos.content.intent")
AppManager = _mpos("AppManager", "mpos.content.app_manager")
TaskManager = _mpos("TaskManager", "mpos.task_manager")
SharedPreferences = _mpos("SharedPreferences", "mpos.config")

APP_FULLNAME = "tech.weyn.messages"
PREFS_APP_ID = APP_FULLNAME

# De app die de verbinding en de identiteit van de badge bezit.
BRIDGE_APP = "tech.weyn.badgecontroller"
BRIDGE_MODULE = "badge_service"

# Het achtervoegsel waar Home Assistant naartoe publiceert en waar wij op
# antwoorden. De brug plakt er `home/badges/<naam>/` voor, en schrijft ons bij
# een hernoeming vanzelf opnieuw in. Vandaar een achtervoegsel en geen topic:
# wie zich op het volledige topic abonneert hoort niets meer zodra de badge
# anders heet.
SUFFIX_MSG = "msg"
SUFFIX_ACK = "ack"

# Een badge kan ook zelf sturen. Home Assistant zet de knoppen retained op
# `buttons`, en een druk zet een verzoek op `send`, waar een automatisatie in
# Home Assistant op afgaat.
#
# **Niet rechtstreeks naar het `msg`-topic van de andere badge.** Dat werkt wel
# en gaat langs Home Assistant heen, en dan blijft het dashboard grijs: geen
# tijdstempel, geen rood, geen groen. Eén plek hoort te bepalen wat sturen
# betekent, en dat is de plek waar de knoppen op het dashboard ook langsgaan.
SUFFIX_BUTTONS = "buttons"
SUFFIX_SEND = "send"

# Twaalf past er op 320 bij 240 in een raster van vier bij drie, met knoppen die
# nog groot genoeg zijn voor een vinger. Meer tonen betekent kleinere knoppen, en
# dat is precies hoe een knop een knop wordt die je niet raakt.
MAX_BUTTONS = 12
LABEL_MAX = 14
TEXT_MAX = 120
BUTTONS_CACHE_MAX = 2000
DEFAULT_SEND_TITLE = "Sturen"

# --- configuratie -----------------------------------------------------------
# Alleen nog wat over berichten gaat. Broker, login en de naam van de badge
# staan in tech.weyn.badgecontroller.
LED_ALERT = True
ACK_TIMEOUT_MIN = 30
CONFIG_OK = False

try:
    import messages_config as _cfg
    LED_ALERT = getattr(_cfg, "LED_ALERT", True)
    ACK_TIMEOUT_MIN = getattr(_cfg, "ACK_TIMEOUT_MIN", ACK_TIMEOUT_MIN)
    CONFIG_OK = True
except ImportError:
    print("messages: no messages_config.py, using defaults")

TICK = 0.5               # lusperiode, en tegelijk de halve knipperperiode

# --- gedeelde toestand, gelezen door de activity ----------------------------
last_message = None
last_message_seq = 0     # loopt op per bericht, zodat dezelfde tekst twee keer
                         # nog steeds twee berichten zijn. Vergelijk nooit tekst.
last_message_time = None
acked_seq = 0
connected = False        # bijgehouden vanuit de brug, elke tick
last_error = None
leds_lit = False         # wat de LEDs doen, zodat de tests het kunnen zien
pending_ack = None       # een bevestiging waar de link niet voor omhoog was
CHILD_NAME = "badge"     # de naam van de badge, geleend van de brug

buttons = []             # wat Home Assistant op deze badge wil zien staan
buttons_title = DEFAULT_SEND_TITLE
buttons_seq = 0          # loopt op bij elke wijziging, zodat het scherm weet
                         # dat het opnieuw moet tekenen
send_error = None        # waarom de laatste druk niet wegkwam, of None

_service = None


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


def titlecase(name):
    """Eerste letter een hoofdletter.

    Zestien stringmethodes van CPython ontbreken op deze firmware, waaronder de
    methode die hier vanzelfsprekend zou zijn."""
    return name[:1].upper() + name[1:]


def clock_text(epoch):
    """De tijd zoals een keukenklok hem toont, via de brug.

    Staat daar omdat de tijdzone een eigenschap van de badge is en niet van deze
    app. Zonder brug liever niets tonen dan een tijd die er twee uur naast zit."""
    b = bridge()
    if b is None:
        return ""
    try:
        return b.clock_text(epoch)
    except Exception:
        return ""


def sync_bridge():
    """De geleende toestand overnemen: naam en verbinding.

    Wordt elke tick aangeroepen, en ook door de activity voor het geval de
    service nog niet draait."""
    global CHILD_NAME, connected, last_error
    b = bridge()
    if b is None:
        connected = False
        last_error = bridge_missing_reason()
        return None
    CHILD_NAME = b.BADGE_NAME
    connected = bool(b.connected)
    last_error = b.last_error
    return b


# Nieuwste eerst. De app heette be.weyn.dinerbadge, heette vanmiddag kort
# tech.weyn.dinerbadge, en heet nu tech.weyn.messages: "diner" was een fossiel
# uit de tijd dat hij alleen de kinderen aan tafel riep.
LEGACY_PREFS_APP_IDS = ("tech.weyn.dinerbadge", "be.weyn.dinerbadge")


def migrate_prefs():
    """Overnemen wat er onder de oude app-id stond, een keer.

    Voorkeuren hangen aan het app-id, dus de hernoeming naar
    tech.weyn.messages zou de LED-keuze en de wachttijd stil terugzetten. Nul
    is hier een bewuste waarde (LEDs uit), dus -1 is wat "staat er niet" zegt.
    """
    try:
        prefs = SharedPreferences(PREFS_APP_ID)
        if prefs.get_int("ack_timeout_min", 0):
            return False
        for oud_id in LEGACY_PREFS_APP_IDS:
            oud = SharedPreferences(oud_id)
            editor = None
            overgenomen = []
            for key in ("ack_timeout_min", "led_alert"):
                waarde = oud.get_int(key, -1)
                if waarde < 0:
                    continue
                if editor is None:
                    editor = prefs.edit()
                editor.put_int(key, waarde)
                overgenomen.append(key)
            if editor is None:
                continue
            editor.commit()
            print("messages: instellingen overgenomen van %s:" % oud_id,
                  ", ".join(overgenomen))
            return True
        return False
    except Exception as e:
        print("messages: kon de oude instellingen niet overnemen:", e)
        return False


migrate_prefs()


def load_prefs():
    """Lezen wat het instelscherm schrijft, en toepassen."""
    global LED_ALERT, ACK_TIMEOUT_MIN
    try:
        prefs = SharedPreferences(PREFS_APP_ID)
        LED_ALERT = bool(prefs.get_int("led_alert", 1 if LED_ALERT else 0))
        ACK_TIMEOUT_MIN = prefs.get_int("ack_timeout_min", ACK_TIMEOUT_MIN)
    except Exception as e:
        print("messages: could not read prefs:", e)
    return False


def has_unacked():
    return last_message_seq > acked_seq


def alert_expired():
    """True zodra de LEDs lang genoeg gezeurd hebben.

    Het bericht blijft op het scherm en blijft te bevestigen; alleen het
    knipperen geeft op, want een slaapkamer met een lampje dat de hele nacht
    flikkert is erger dan een bericht dat niemand beantwoordde."""
    if not has_unacked() or not last_message_time:
        return False
    return (time.time() - last_message_time) >= ACK_TIMEOUT_MIN * 60


def publish_ack(seq=None):
    """Aangeroepen door de activity als het kind op 'Ontvangen' tikt.

    Markeert het bericht ook lokaal als bevestigd wanneer de publish mislukt,
    zodat de knop niet liegt over wat hij deed."""
    global acked_seq, pending_ack
    if seq is None:
        seq = last_message_seq
    if seq <= 0 or seq <= acked_seq:
        # Al bevestigd. Opnieuw publiceren zou de wachtklok van Home Assistant
        # herstarten voor een bericht dat niemand net gelezen heeft.
        return False
    acked_seq = seq
    _leds_off()
    text = last_message or "ack"
    b = bridge()
    if b is not None and b.publish(SUFFIX_ACK, text):
        pending_ack = None
        print("messages: ack published")
        return True
    # Een slaapkamer aan de rand van de wifi is precies waar een kind op de knop
    # drukt en de publish mislukt. Houd hem vast: Home Assistant zou anders een
    # half uur rood staan voor een bericht dat gelezen is.
    pending_ack = text
    return False


# --- zelf sturen ------------------------------------------------------------
# De app kent geen enkele naam en geen enkele tekst. Home Assistant publiceert
# retained op `home/badges/<naam>/buttons` wat deze badge mag sturen, en de app
# tekent wat er binnenkomt. Een badge waar nooit iets naartoe gepubliceerd is
# heeft dus geen stuurknop, en dat is de instelling: één node knoppen geven is
# één keer iets publiceren, niet een vinkje op elk toestel.

def normalize_button(raw):
    """Eén knop uit de configuratie, of None als er niets bruikbaars in staat.

    Streng zijn loont hier: dit komt van het netwerk, wordt op een scherm gezet
    en gaat daarna weer het netwerk op. Een knop zonder doel of zonder tekst is
    een knop die stilletjes niets doet, en die tonen we liever niet.
    """
    if not isinstance(raw, dict):
        return None
    target = str(raw.get("target") or "").strip().lower()
    text = str(raw.get("text") or "").strip()
    if not target or not text:
        return None
    label = str(raw.get("label") or "").strip() or titlecase(target)
    button = {"target": target, "text": text[:TEXT_MAX],
              "label": label[:LABEL_MAX]}
    # Vorm, teken en kleur zijn alle drie optioneel en alle drie zonder
    # betekenis voor deze app: hij tekent wat er staat.
    for key in ("figure", "symbol", "initial", "color"):
        value = raw.get(key)
        if value:
            button[key] = str(value).strip()
    return button


def parse_buttons(payload):
    """(knoppen, titel) uit een payload, of wat er stond als hij stuk is.

    Een lege retained payload is hoe MQTT "vergeet dit" zegt, en die wist de
    knoppen. Een payload die geen JSON is, is iets anders: dan is er ergens een
    fout gemaakt, en een werkend paneel weggooien om een verkeerde publicatie
    helpt niemand.
    """
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = payload.decode("utf-8")
        except Exception:
            return [], DEFAULT_SEND_TITLE
    text = (payload or "").strip()
    if not text:
        return [], DEFAULT_SEND_TITLE
    try:
        data = json.loads(text)
    except Exception as e:
        print("messages: knoppen niet te lezen:", e)
        return buttons, buttons_title
    title = DEFAULT_SEND_TITLE
    if isinstance(data, dict):
        title = str(data.get("title") or DEFAULT_SEND_TITLE).strip() \
            or DEFAULT_SEND_TITLE
        data = data.get("buttons")
    if not isinstance(data, (list, tuple)):
        print("messages: knoppen zonder lijst")
        return buttons, buttons_title
    out = []
    for raw in data:
        button = normalize_button(raw)
        if button is not None:
            out.append(button)
        if len(out) >= MAX_BUTTONS:
            break
    return out, title


def set_buttons(payload, remember=True):
    """Nieuwe knopconfiguratie toepassen. True als er iets veranderde."""
    global buttons, buttons_title, buttons_seq
    items, title = parse_buttons(payload)
    if items == buttons and title == buttons_title:
        return False
    buttons = items
    buttons_title = title
    buttons_seq += 1
    if remember:
        remember_buttons(payload)
    print("messages: %d knoppen" % len(buttons))
    return True


def remember_buttons(payload):
    """Bewaren zodat de knoppen er meteen staan na een herstart.

    De broker levert retained berichten opnieuw aan, dus strikt nodig is dit
    niet. Wel prettig: anders is het scherm leeg tot de badge verbonden is, en
    dat duurt op een koude start langer dan iemand geduld heeft.
    """
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = payload.decode("utf-8")
        except Exception:
            return False
    text = (payload or "").strip()
    if len(text) > BUTTONS_CACHE_MAX:
        return False
    try:
        editor = SharedPreferences(PREFS_APP_ID).edit()
        editor.put_string("buttons_json", text)
        editor.commit()
        return True
    except Exception as e:
        print("messages: kon de knoppen niet bewaren:", e)
        return False


def load_cached_buttons():
    """Wat er de vorige keer stond, voor de broker antwoordt."""
    try:
        text = SharedPreferences(PREFS_APP_ID).get_string("buttons_json", "")
    except Exception as e:
        print("messages: kon de knoppen niet lezen:", e)
        return False
    if not text:
        return False
    return set_buttons(text, remember=False)


def visible_buttons():
    """De knoppen die deze badge mag tonen.

    Een badge die naar zichzelf stuurt laat zichzelf piepen, en dat is nooit wat
    iemand bedoelde. Hier gefilterd en niet bij het inlezen, want de naam van de
    badge kan veranderen nadat de knoppen al binnen waren.
    """
    own = (CHILD_NAME or "").strip().lower()
    return [b for b in buttons if b.get("target") != own]


def publish_send(button):
    """Een verzoek op het send-topic. False als het niet wegkwam.

    Bewust niet vasthouden zoals een bevestiging dat wel doet. Een bevestiging
    blijft waar tot ze aankomt; "eten binnen tien minuten" is over een half uur
    geen bericht meer maar een leugen. Zeg dat het mislukt is en laat degene die
    voor de badge staat opnieuw drukken.
    """
    global send_error
    if not isinstance(button, dict):
        send_error = "geen knop"
        return False
    target = str(button.get("target") or "").strip().lower()
    text = str(button.get("text") or "").strip()
    if not target or not text:
        send_error = "knop is onvolledig"
        return False
    if target == (CHILD_NAME or "").strip().lower():
        # Ook hier, niet alleen bij het tekenen: een naamswissel mag geen badge
        # opleveren die zichzelf laat piepen.
        send_error = "niet naar zichzelf"
        return False
    b = bridge()
    if b is None:
        send_error = bridge_missing_reason()
        return False
    payload = json.dumps({"target": target, "text": text, "from": CHILD_NAME})
    if b.publish(SUFFIX_SEND, payload):
        send_error = None
        print("messages: verstuurd naar", target)
        return True
    send_error = "geen verbinding"
    return False


# --- LEDs ------------------------------------------------------------------
# mpos.lights op deze firmware. Alles hier is best-effort: geen LEDs mag nooit
# een bericht breken.

def _lights():
    try:
        import mpos.lights as lights
        mgr = getattr(lights, "LightsManager", lights)
        if hasattr(mgr, "is_available") and not mgr.is_available():
            return None
        return mgr
    except Exception:
        return None


def _leds_write(lit):
    global leds_lit
    if lit == leds_lit:
        return                     # schrijf de strip niet elke tick opnieuw
    mgr = _lights()
    if mgr is None:
        return
    try:
        if lit:
            mgr.set_all(60, 40, 0)
        elif hasattr(mgr, "clear"):
            mgr.clear()
        else:
            mgr.set_all(0, 0, 0)
        mgr.write()
        leds_lit = lit
    except Exception:
        pass


def _leds_off():
    _leds_write(False)


def _leds_tick():
    """Knipperen zolang er een bericht wacht, donker anders."""
    if not LED_ALERT or not has_unacked() or alert_expired():
        _leds_off()
        return
    _leds_write(not leds_lit)


def _icon():
    """Een meldingspictogram dat op deze build bestaat."""
    try:
        import lvgl as lv
        sym = getattr(lv, "SYMBOL", None)
        for name in ("BELL", "ENVELOPE", "AUDIO", "OK"):
            value = getattr(sym, name, None)
            if isinstance(value, str) and value:
                return value
    except Exception:
        pass
    return "!"


class MessagesService(Service):

    def __init__(self):
        super().__init__()
        self._running = False

    def onCreate(self):
        global _service
        previous = _service
        if previous is not None and previous is not self:
            print("messages: retiring the previous service instance")
            try:
                previous.onDestroy()
            except Exception as e:
                print("messages: could not stop the previous service:", e)
        _service = self
        load_prefs()
        load_cached_buttons()
        sync_bridge()
        print("messages: service created for", CHILD_NAME)

    def onStart(self, intent=None):
        if self._running:
            # Twee keer gestart worden is geen hypothese: alles wat de app start
            # kan de services uit het manifest opnieuw starten.
            print("messages: already running, not starting a second loop")
            return
        self._running = True
        TaskManager.create_task(self._run())

    def onDestroy(self):
        self._running = False
        b = bridge()
        if b is not None:
            for suffix in (SUFFIX_MSG, SUFFIX_BUTTONS):
                try:
                    b.unsubscribe(suffix)
                except Exception:
                    pass
        _leds_off()

    # --- hoofdlus ----------------------------------------------------------

    async def _run(self):
        while self._running:
            try:
                self._pump()
            except Exception as e:            # de lus mag nooit sterven
                print("messages: loop error:", e)
            try:
                _leds_tick()
            except Exception:
                pass
            await TaskManager.sleep(TICK)

    def _pump(self):
        b = sync_bridge()
        if b is None:
            return
        # Elke tick opnieuw vragen. Het is een woordenboekschrijving als we er al
        # in staan, en het is wat een herstart van de brug repareert zonder dat
        # deze service iets hoeft te merken.
        b.subscribe(SUFFIX_MSG, self._on_message)
        b.subscribe(SUFFIX_BUTTONS, self._on_buttons)
        if connected:
            self._flush_ack()

    # --- binnenkomend ------------------------------------------------------

    def _on_message(self, topic, msg):
        global last_message, last_message_seq, last_message_time
        try:
            text = msg.decode("utf-8")
        except Exception:
            text = str(msg)
        text = text.strip()
        if not text:
            return

        last_message = text
        last_message_seq += 1
        last_message_time = time.time()
        print("messages: message", last_message_seq, repr(text))

        _leds_tick()

        # Een bericht op een donkere badge is geen bericht. De brug bezit het
        # scherm, dus die maakt het wakker.
        b = bridge()
        if b is not None:
            try:
                b.wake()
            except Exception as e:
                print("messages: wake failed:", e)

        try:
            NotificationManager.notify(Notification(
                notification_id=APP_FULLNAME + ".message",
                icon=_icon(),
                title=titlecase(CHILD_NAME),
                text=text,
                priority=Notification.PRIORITY_HIGH,
                intent=Intent(action="main", app_fullname=APP_FULLNAME),
                auto_cancel=True,
                app_fullname=APP_FULLNAME,
            ))
        except Exception as e:
            print("messages: notify failed:", e)

        # Haal de app naar voren, ook als het kind een spel speelde.
        try:
            AppManager.start_app(APP_FULLNAME)
        except Exception as e:
            print("messages: start_app failed:", e)

    def _on_buttons(self, topic, payload):
        """De knopconfiguratie van Home Assistant, retained."""
        try:
            set_buttons(payload)
        except Exception as e:
            print("messages: knoppen niet verwerkt:", e)

    # --- uitgaand ----------------------------------------------------------

    def _flush_ack(self):
        """Sturen wat de vorige storing opslokte, nu er een link is."""
        global pending_ack
        if pending_ack is None:
            return
        b = bridge()
        if b is not None and b.publish(SUFFIX_ACK, pending_ack):
            pending_ack = None
            print("messages: held-back ack sent")
