"""Offline tests voor de Huis-app (tech.weyn.homecontrol).

Draait op gewone Python tegen de stubs in tests/stubs/, zodat het paneel en het
scherm na te kijken zijn zonder badge en zonder broker.

    python3 tests/test_homecontrol.py

De brug wordt hier vervangen door een nep-exemplaar in sys.modules. Dat is niet
alleen makkelijker dan de echte, het is ook precies hoe de app hem in het echt
vindt: apps kunnen elkaar niet importeren, maar delen wel één sys.modules.

Wat hier bewaakt wordt en wat op een badge duur is om te ontdekken: dat een knop
niet omgaat voor er bewijs is, dat een kapotte publicatie een werkend paneel niet
wist, en dat een knop met `confirm` twee tikken vraagt.
"""

import os
import sys
import types

sys.dont_write_bytecode = True   # laat nooit __pycache__ in de app-map achter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP_DIR = os.path.join(ROOT, "tech.weyn.homecontrol")
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, APP_DIR)


# --- de nep-brug ------------------------------------------------------------

class FakeBridge:
    BADGE_NAME = "keuken"
    connected = True
    last_error = None
    subscribers = {}
    published = []
    publish_ok = True

    @classmethod
    def reset(cls):
        cls.BADGE_NAME = "keuken"
        cls.connected = True
        cls.last_error = None
        cls.subscribers = {}
        cls.published = []
        cls.publish_ok = True

    @classmethod
    def subscribe(cls, suffix, callback):
        cls.subscribers[suffix] = callback
        return True

    @classmethod
    def unsubscribe(cls, suffix):
        cls.subscribers.pop(suffix, None)

    @classmethod
    def publish(cls, suffix, payload, retain=False):
        if not cls.publish_ok or not cls.connected:
            return False
        cls.published.append((suffix, payload))
        return True

    @classmethod
    def wake(cls):
        return True

    @classmethod
    def deliver(cls, suffix, text):
        """Wat de brug doet als er iets binnenkomt: de callback aanroepen met
        het volledige topic en bytes, zoals umqtt het aanlevert."""
        callback = cls.subscribers.get(suffix)
        if callback is None:
            return False
        payload = text.encode("utf-8") if isinstance(text, str) else text
        callback("home/badges/%s/%s" % (cls.BADGE_NAME, suffix), payload)
        return True


import json                                            # noqa: E402
import time                                            # noqa: E402

import lvgl as lv                                      # noqa: E402
import mpos                                            # noqa: E402
import mpos.ui                                         # noqa: E402
import mpos.config                                     # noqa: E402

import hcpanel as service                              # noqa: E402
from homecontrol import HomeControl, grid, MIN_CELL    # noqa: E402

FAILURES = []
CHECKS = {"n": 0}


def check(label, condition):
    CHECKS["n"] += 1
    if not condition:
        FAILURES.append(label)
        print("FAIL:", label)


def equal(label, got, want):
    check("%s (%r != %r)" % (label, got, want), got == want)


PANEL = json.dumps({
    "title": "Huis",
    "buttons": [
        {"id": "alarm_aan", "label": "Alarm aan", "state": "alarm",
         "confirm": True, "color": "CC5555"},
        {"id": "koepel_dicht", "label": "Koepel dicht", "state": "koepel"},
        {"id": "koepel_lucht", "label": "Op ventilatie", "state": "koepel"},
        {"id": "licht_uit", "label": "Licht beneden uit", "state": "licht"},
    ],
})


def fresh(panel=PANEL, state=None):
    """Een schone module met de brug erin en, als je wil, een paneel."""
    FakeBridge.reset()
    mpos.config._STORE.clear()
    sys.modules[service.BRIDGE_MODULE] = FakeBridge
    service.buttons = []
    service.panel_title = service.DEFAULT_TITLE
    service.panel_seq = 0
    service.states = {}
    service.state_seq = 0
    service.press_seq = 0
    service.press_error = None
    service.reset()
    service.sync_bridge()
    service.subscribe_all()
    if panel is not None:
        FakeBridge.deliver(service.SUFFIX_PANEL, panel)
    if state is not None:
        FakeBridge.deliver(service.SUFFIX_STATE, state)
    return service


def scherm(**kw):
    fresh(**kw)
    act = HomeControl()
    act.onCreate()
    act.onResume(act.screen)
    return act


def button_by_id(ident):
    for b in service.buttons:
        if b.get("id") == ident:
            return b
    return None


# ===========================================================================
# Het paneel
# ===========================================================================

fresh()
equal("vier knoppen uit de configuratie", len(service.buttons), 4)
equal("en de titel erbij", service.panel_title, "Huis")
equal("een knop houdt zijn id", service.buttons[0]["id"], "alarm_aan")
equal("en zijn opschrift", service.buttons[0]["label"], "Alarm aan")
equal("confirm komt mee", service.buttons[0].get("confirm"), True)
equal("een knop zonder confirm heeft het veld niet",
      "confirm" in service.buttons[1], False)

# Een knop zonder id doet stilletjes niets. Die tonen we niet.
knoppen, _titel = service.parse_panel(json.dumps(
    {"buttons": [{"label": "Naamloos"}, {"id": "ok", "label": "Wel"}]}))
equal("een knop zonder id valt weg", len(knoppen), 1)
equal("de knop met id blijft", knoppen[0]["id"], "ok")

# Zonder opschrift is het id het opschrift: beter dan een lege knop.
knoppen, _titel = service.parse_panel(json.dumps({"buttons": [{"id": "scene_film"}]}))
equal("zonder opschrift staat het id erop", knoppen[0]["label"], "scene_film")

# Meer dan MAX_BUTTONS zou knoppen opleveren die te klein zijn voor een vinger.
veel = [{"id": "k%d" % i} for i in range(12)]
knoppen, _titel = service.parse_panel(json.dumps({"buttons": veel}))
equal("de lijst wordt afgekapt", len(knoppen), service.MAX_BUTTONS)

lang = {"id": "x", "label": "een veel te lang opschrift dat niet past"}
knoppen, _titel = service.parse_panel(json.dumps({"buttons": [lang]}))
equal("een lang opschrift wordt gekapt",
      len(knoppen[0]["label"]), service.LABEL_MAX)

# Een lege retained payload is hoe MQTT "vergeet dit" zegt.
fresh()
FakeBridge.deliver(service.SUFFIX_PANEL, "")
equal("een lege payload wist het paneel", service.buttons, [])

# Kapotte JSON is iets anders: dan is er ergens een fout gemaakt, en een werkend
# paneel weggooien om een verkeerde publicatie helpt niemand.
fresh()
FakeBridge.deliver(service.SUFFIX_PANEL, "{dit is geen json")
equal("kapotte JSON laat het paneel staan", len(service.buttons), 4)
FakeBridge.deliver(service.SUFFIX_PANEL, json.dumps({"buttons": "geen lijst"}))
equal("en een paneel zonder lijst ook", len(service.buttons), 4)

# Dezelfde configuratie nog eens is geen wijziging, anders tekent het scherm
# zich suf op elk retained bericht na een herverbinding.
fresh()
seq = service.panel_seq
equal("hetzelfde paneel verandert niets", service.set_panel(PANEL), False)
equal("en laat de teller staan", service.panel_seq, seq)


# ===========================================================================
# Het paneel overleeft een herstart
# ===========================================================================

fresh()
equal("het paneel is bewaard",
      mpos.config.SharedPreferences(service.PREFS_APP_ID)
      .get_string("panel_json", "") != "", True)

# Zonder brug, zoals bij een koude start: het paneel staat er meteen.
service.buttons = []
service.panel_seq = 0
sys.modules.pop(service.BRIDGE_MODULE, None)
equal("de cache vult het paneel", service.load_cached_panel(), True)
equal("met alle knoppen", len(service.buttons), 4)

# Te groot om te bewaren mag geen uitzondering worden midden in een callback.
fresh()
groot = json.dumps({"buttons": [{"id": "x", "label": "y" * 3000}]})
equal("een te grote payload wordt niet bewaard",
      service.remember_panel(groot), False)


# ===========================================================================
# De toestand
# ===========================================================================
# Home Assistant stuurt tekst, geen entiteitstoestand. De badge weet niet wat
# armed_home betekent en hoeft dat ook nooit te leren.

fresh(state=json.dumps({"alarm": "uit", "koepel": "dicht", "licht": "aan"}))
equal("drie sleutels", len(service.states), 3)
equal("de tekst komt door", service.states["koepel"]["text"], "dicht")
equal("zonder kleur is de kleur None", service.states["koepel"]["color"], None)

FakeBridge.deliver(service.SUFFIX_STATE, json.dumps(
    {"alarm": {"text": "aan (thuis)", "color": "44AA44"}}))
equal("een dict geeft tekst", service.states["alarm"]["text"], "aan (thuis)")
equal("en een kleur", service.states["alarm"]["color"], "44AA44")

FakeBridge.deliver(service.SUFFIX_STATE, json.dumps({"licht": True}))
equal("een boolean wordt leesbaar", service.states["licht"]["text"], "aan")

FakeBridge.deliver(service.SUFFIX_STATE, json.dumps({"licht": "x" * 40}))
equal("een lange toestand wordt gekapt",
      len(service.states["licht"]["text"]), service.STATE_MAX)

vorige = dict(service.states)
FakeBridge.deliver(service.SUFFIX_STATE, "[1, 2, 3]")
equal("een toestand die geen object is laat de vorige staan",
      service.states, vorige)
FakeBridge.deliver(service.SUFFIX_STATE, "{kapot")
equal("kapotte JSON ook", service.states, vorige)

fresh(state=json.dumps({"koepel": "dicht"}))
knop = button_by_id("koepel_dicht")
equal("de knop vindt zijn toestand", service.state_of(knop)["text"], "dicht")
equal("een knop zonder sleutel heeft er geen",
      service.state_of({"id": "los"}), None)


# ===========================================================================
# Drukken
# ===========================================================================

fresh(state=json.dumps({"licht": "aan"}))
knop = button_by_id("licht_uit")
equal("de druk komt weg", service.press(knop), True)
suffix, payload = FakeBridge.published[-1]
equal("op het press-topic", suffix, service.SUFFIX_PRESS)
verstuurd = json.loads(payload)
equal("met het id van de knop", verstuurd["id"], "licht_uit")
equal("en de naam van de badge", verstuurd["from"], "keuken")
equal("de teller loopt op", verstuurd["seq"], 1)
check("de badge stuurt geen servicenaam mee",
      "service" not in verstuurd and "entity_id" not in verstuurd)
check("de knop wacht op bewijs", "licht_uit" in service.pending)
equal("en staat dus niet al op gelukt",
      service.status_of(knop)[0], "wacht")

# Een tweede druk krijgt een eigen volgnummer, anders kan een trage ack bij de
# verkeerde druk terechtkomen.
service.press(knop)
equal("elke druk heeft zijn eigen nummer",
      json.loads(FakeBridge.published[-1][1])["seq"], 2)

# Geen brug: niets versturen, en zeggen waarom.
fresh()
sys.modules.pop(service.BRIDGE_MODULE, None)
service.sync_bridge()
equal("zonder brug komt er niets weg", service.press(button_by_id("licht_uit")), False)
equal("en staat er waarom", service.press_error, "Badge-app draait niet")

# Wel een brug, geen link.
fresh()
FakeBridge.publish_ok = False
equal("zonder link komt er niets weg", service.press(button_by_id("licht_uit")), False)
equal("en staat er waarom", service.press_error, "geen verbinding")
check("een mislukte druk laat geen wachtende knop achter", not service.pending)

# Een knop zonder id kan niet bestaan na parse_panel, maar de publicatie hoort
# zich niet op de parser te verlaten.
fresh()
equal("een knop zonder id gaat de deur niet uit", service.press({"label": "x"}), False)
equal("iets dat geen knop is ook", service.press("licht_uit"), False)


# ===========================================================================
# Een knop liegt niet
# ===========================================================================

# Het bewijs voor een knop met een toestandssleutel is die toestand.
fresh(state=json.dumps({"licht": "aan"}))
knop = button_by_id("licht_uit")
service.press(knop)
FakeBridge.deliver(service.SUFFIX_STATE, json.dumps({"licht": "uit"}))
equal("de toestandswissel bevestigt de druk", service.status_of(knop)[0], "ok")
equal("met de nieuwe toestand erbij", service.status_of(knop)[1], "uit")
check("en de knop wacht niet meer", "licht_uit" not in service.pending)

# Dezelfde toestand nog eens is geen bewijs: het licht was al uit.
fresh(state=json.dumps({"licht": "uit"}))
knop = button_by_id("licht_uit")
service.press(knop)
FakeBridge.deliver(service.SUFFIX_STATE, json.dumps({"licht": "uit"}))
equal("dezelfde toestand bevestigt niets", service.status_of(knop)[0], "wacht")

# En na de wachttijd staat er dat er niets terugkwam. Niet groen: er is geen
# bewijs dat er iets gebeurd is.
equal("de wachttijd loopt af",
      service.tick(time.time() + service.PENDING_SECONDS + 1), True)
equal("zonder antwoord is het niet gelukt", service.status_of(knop)[0], "fout")
equal("en dat staat er ook", service.status_of(knop)[1], "geen antwoord")

# Een knop zonder toestandssleutel kan alleen op een ack wachten: een scene
# heeft geen toestand om naar te kijken.
fresh(panel=json.dumps({"buttons": [{"id": "scene_film", "label": "Film"}]}))
knop = button_by_id("scene_film")
service.press(knop)
equal("een scene wacht", service.status_of(knop)[0], "wacht")
FakeBridge.deliver(service.SUFFIX_ACK, json.dumps(
    {"id": "scene_film", "seq": 1, "ok": True, "text": "Film aan"}))
equal("de ack bevestigt hem", service.status_of(knop)[0], "ok")
equal("met de tekst van Home Assistant", service.status_of(knop)[1], "Film aan")

# Een ack zonder tekst pakt de toestand die er op dat moment staat. Zo hoeft
# Home Assistant de vertaling van toestand naar tekst niet twee keer te
# schrijven, een keer voor het toestandsbericht en een keer voor de ack.
fresh(state=json.dumps({"koepel": "dicht"}))
knop = button_by_id("koepel_lucht")
service.press(knop)
FakeBridge.deliver(service.SUFFIX_STATE, json.dumps({"koepel": "5%"}))
FakeBridge.deliver(service.SUFFIX_ACK, json.dumps({"id": "koepel_lucht", "seq": 1}))
equal("een ack zonder tekst pakt de toestand", service.status_of(knop)[1], "5%")

# En op een koepel die al open stond verandert er niets, en dan is de ack het
# enige antwoord dat er komt. Hij mag dan niet leeg blijven.
fresh(state=json.dumps({"koepel": "5%"}))
knop = button_by_id("koepel_lucht")
service.press(knop)
FakeBridge.deliver(service.SUFFIX_ACK, json.dumps({"id": "koepel_lucht", "seq": 1}))
equal("zonder wissel bevestigt de ack alsnog", service.status_of(knop)[0], "ok")
equal("met de toestand die er staat", service.status_of(knop)[1], "5%")

# Een ack die niet lukte is ook een antwoord.
fresh(panel=json.dumps({"buttons": [{"id": "scene_film", "label": "Film"}]}))
knop = button_by_id("scene_film")
service.press(knop)
FakeBridge.deliver(service.SUFFIX_ACK, json.dumps(
    {"id": "scene_film", "seq": 1, "ok": False, "text": "geen Sonos"}))
equal("een mislukte ack maakt de knop niet groen", service.status_of(knop)[0], "fout")

# Een ack op een vorige druk mag de huidige niet afmelden.
fresh(panel=json.dumps({"buttons": [{"id": "scene_film", "label": "Film"}]}))
knop = button_by_id("scene_film")
service.press(knop)
service.press(knop)
FakeBridge.deliver(service.SUFFIX_ACK, json.dumps({"id": "scene_film", "seq": 1}))
equal("een oude ack telt niet", service.status_of(knop)[0], "wacht")
FakeBridge.deliver(service.SUFFIX_ACK, json.dumps({"id": "scene_film", "seq": 2}))
equal("de ack van deze druk wel", service.status_of(knop)[0], "ok")

# Een ack voor een knop waar niemand op drukte is geen fout, maar hij hoort ook
# geen wachtende knop van iets anders af te melden.
fresh()
FakeBridge.deliver(service.SUFFIX_ACK, "{kapot")
FakeBridge.deliver(service.SUFFIX_ACK, json.dumps({"seq": 1}))
equal("een ack zonder id doet niets", service.results, {})


# ===========================================================================
# Abonneren
# ===========================================================================

fresh()
for suffix in (service.SUFFIX_PANEL, service.SUFFIX_STATE, service.SUFFIX_ACK):
    check("geabonneerd op %s" % suffix, suffix in FakeBridge.subscribers)
check("en niet op het press-topic",
      service.SUFFIX_PRESS not in FakeBridge.subscribers)
# Geen schuine streep in een achtervoegsel: badge_service.topic() laat alles met
# een `/` erin staan zoals het is, want zo hangt het weer aan een gedeeld topic.
# `control/panel` zou dus het letterlijke topic worden en elke badge naar
# hetzelfde laten luisteren.
for suffix in (service.SUFFIX_PANEL, service.SUFFIX_STATE,
               service.SUFFIX_PRESS, service.SUFFIX_ACK):
    check("%s heeft geen schuine streep" % suffix, "/" not in suffix)
    check("%s botst niet met Berichtjes" % suffix,
          suffix not in ("msg", "ack", "buttons", "send", "apps"))
service.unsubscribe_all()
equal("afmelden laat niets staan", FakeBridge.subscribers, {})

# Een callback die gooit mag de brug niet meenemen: een app met een bug hoort de
# badge niet van de broker te halen.
fresh()
kapot = service.set_panel
service.set_panel = lambda *a, **k: 1 / 0
try:
    FakeBridge.deliver(service.SUFFIX_PANEL, PANEL)
    check("een gooiende callback komt niet naar buiten", True)
except ZeroDivisionError:
    check("een gooiende callback komt niet naar buiten", False)
finally:
    service.set_panel = kapot


# ===========================================================================
# Het scherm
# ===========================================================================

cols, rows, cell_w, cell_h = grid(4)
equal("vier knoppen in twee kolommen", cols, 2)
equal("en twee rijen", rows, 2)
check("een cel is vingergroot", cell_h >= MIN_CELL and cell_w >= 100)
check("en past op het scherm", 2 * cell_w + 3 * 6 <= 320)

cols, rows, cell_w, cell_h = grid(2)
equal("twee knoppen krijgen de volle breedte", cols, 1)
check("en zijn dus breed", cell_w >= 300)

cols, rows, cell_w, cell_h = grid(service.MAX_BUTTONS)
check("zes knoppen passen nog altijd vingergroot", cell_h >= MIN_CELL)
check("en het raster past in de hoogte",
      rows * cell_h + (rows - 1) * 6 <= 240 - 2 * 6 - 22)

act = scherm(state=json.dumps({"alarm": "uit", "koepel": "dicht",
                               "licht": "aan"}))
equal("er staan vier knoppen", len(act.tiles), 4)
knop, note = act.tiles["koepel_dicht"]
equal("de toestand staat op de knop", note.text, "dicht")
knop, note = act.tiles["licht_uit"]
equal("elke knop de zijne", note.text, "aan")

# Een knop zonder toestandssleutel houdt zijn onderregel leeg. Dat is geen
# gebrek: er valt niets te melden.
act = scherm(panel=json.dumps({"buttons": [{"id": "scene_film", "label": "Film"}]}))
equal("een scene heeft een lege onderregel", act.tiles["scene_film"][1].text, "")

# Drukken op een gewone knop stuurt meteen.
act = scherm(state=json.dumps({"licht": "aan"}))
act.tiles["licht_uit"][0].click()
equal("een tik stuurt", len(FakeBridge.published), 1)
equal("en de knop wacht zichtbaar", act.tiles["licht_uit"][1].text, "...")
FakeBridge.deliver(service.SUFFIX_STATE, json.dumps({"licht": "uit"}))
act._refresh()
equal("na de toestandswissel staat het er", act.tiles["licht_uit"][1].text, "uit")

# Een knop met confirm vraagt twee tikken. Een alarm dat aangaat omdat iemand
# de badge oppakte is geen alarm.
act = scherm(state=json.dumps({"alarm": "uit"}))
act.tiles["alarm_aan"][0].click()
equal("de eerste tik stuurt niets", len(FakeBridge.published), 0)
equal("en vraagt om nog een tik", act.tiles["alarm_aan"][1].text, "nog eens")
act.tiles["alarm_aan"][0].click()
equal("de tweede tik stuurt wel", len(FakeBridge.published), 1)
equal("met het juiste id",
      json.loads(FakeBridge.published[0][1])["id"], "alarm_aan")

# De bevestiging verloopt. Wie een minuut later langsloopt en de badge aantikt
# hoort het alarm niet aan te zetten.
act = scherm(state=json.dumps({"alarm": "uit"}))
act.tiles["alarm_aan"][0].click()
act._armed = ("alarm_aan", time.time() - 1)
act._refresh()
act.tiles["alarm_aan"][0].click()
equal("een verlopen bevestiging stuurt niets", len(FakeBridge.published), 0)

# Een tik op een andere knop haalt de bevestiging weg.
act = scherm(state=json.dumps({"alarm": "uit", "licht": "aan"}))
act.tiles["alarm_aan"][0].click()
act.tiles["licht_uit"][0].click()
equal("de andere knop stuurt", len(FakeBridge.published), 1)
equal("en dat is niet het alarm",
      json.loads(FakeBridge.published[0][1])["id"], "licht_uit")
act.tiles["alarm_aan"][0].click()
equal("het alarm vraagt weer om twee tikken", len(FakeBridge.published), 1)

# Zonder knoppen staat er waar ze vandaan zouden moeten komen.
act = scherm(panel="")
equal("geen knoppen", len(act.tiles), 0)
check("maar wel uitleg",
      any("control_panel" in (kind.text or "") for kind in act.holder.children))

# Geen verbinding hoort er te staan, en de reden erbij: "geen verbinding" en
# "Badge-app draait niet" vragen om iets heel anders.
act = scherm()
FakeBridge.connected = False
FakeBridge.last_error = "broker weg"
act._refresh()
equal("een verbroken link staat op het scherm", act.status.text, "broker weg")

act = scherm()
sys.modules.pop(service.BRIDGE_MODULE, None)
act._refresh()
equal("en een ontbrekende Badge-app ook", act.status.text, "Badge-app draait niet")
sys.modules[service.BRIDGE_MODULE] = FakeBridge

# Het scherm meldt zich af als het weggaat, en meldt zich weer aan als het
# terugkomt: retained berichten komen dan vanzelf opnieuw binnen.
act = scherm()
act.onPause(act.screen)
equal("weg is weg", FakeBridge.subscribers, {})
act.onResume(act.screen)
check("en terug is terug", service.SUFFIX_PANEL in FakeBridge.subscribers)

# Een raster wordt niet elke frame opnieuw gebouwd: dan zou een tik midden in
# het tekenen op een verdwenen knop landen.
act = scherm()
eerste = act.tiles["licht_uit"][0]
act._refresh()
act._refresh()
check("dezelfde knoppen blijven staan", act.tiles["licht_uit"][0] is eerste)
FakeBridge.deliver(service.SUFFIX_PANEL, json.dumps(
    {"buttons": [{"id": "licht_uit", "label": "Licht uit"}]}))
act._refresh()
equal("een nieuw paneel tekent opnieuw", len(act.tiles), 1)
check("en dat is een andere knop", act.tiles["licht_uit"][0] is not eerste)

# Scrollen annuleert een tik die een paar pixels meebeweegt. Dat mag hier niet
# kunnen: het raster past, dus het scrollt niet.
act = scherm()
for obj in (act.screen, act.holder):
    check("de container scrollt niet",
          not obj.has_flag(lv.obj.FLAG.SCROLLABLE))
check("en het opschrift eet de tik niet op",
      not act.tiles["licht_uit"][1].has_flag(lv.obj.FLAG.CLICKABLE))


# ===========================================================================
# Wat MicroPython niet heeft
# ===========================================================================

with open(os.path.join(APP_DIR, "hcpanel.py")) as fh:
    SOURCE = fh.read()
check("het paneel bouwt geen widgets",
      "lv.obj(" not in SOURCE and "lv.label(" not in SOURCE)
# Een gewone import zou werken zolang deze app als laatste laadt en dan stil
# breken zodra de volgorde wisselt. Het moet de opzoeking in sys.modules zijn.
check("het paneel importeert de brug niet rechtstreeks",
      not any(regel.strip().startswith(("import badge_service",
                                        "from badge_service"))
              for regel in SOURCE.split("\n")))
check("en zoekt hem op in sys.modules",
      "sys.modules.get(BRIDGE_MODULE)" in SOURCE)

MISSING_ON_BADGE = (
    "capitalize", "casefold", "expandtabs", "format_map", "isdecimal",
    "isidentifier", "isprintable", "ljust", "maketrans", "removeprefix",
    "removesuffix", "rjust", "swapcase", "title", "translate", "zfill",
)
for name in sorted(os.listdir(APP_DIR)):
    if not name.endswith(".py"):
        continue
    with open(os.path.join(APP_DIR, name)) as fh:
        text = fh.read()
    for method in MISSING_ON_BADGE:
        check("%s roept str.%s() niet aan, die bestaat niet op deze firmware"
              % (name, method), ".%s(" % method not in text)
    # Een module-level functie die const heet laat de hele module vallen: de
    # compiler leest hem als constantendeclaratie.
    check("%s definieert geen functie die const heet" % name,
          "def const(" not in text)
    # re.findall en re.finditer bestaan niet op deze firmware.
    check("%s gebruikt geen re.findall of re.finditer" % name,
          ".findall(" not in text and ".finditer(" not in text)

# lv.ANIM bestaat niet op deze build, lv.ANIM_OFF wel. En de wrap-constante is
# lv.label.LONG_MODE.WRAP: fout gespeld wordt set_long_mode stil overgeslagen en
# loopt lange tekst van het scherm.
with open(os.path.join(APP_DIR, "homecontrol.py")) as fh:
    SCREEN_SOURCE = fh.read()
check("het scherm gebruikt lv.ANIM niet", "lv.ANIM." not in SCREEN_SOURCE)
check("en spelt de wrap-constante zoals deze build hem heeft",
      "label.LONG_MODE.WRAP" in SCREEN_SOURCE
      and "lv.LABEL_LONG" not in SCREEN_SOURCE)

# ===========================================================================

print("\n%d checks, %d mislukt" % (CHECKS["n"], len(FAILURES)))
for f in FAILURES:
    print("  -", f)
sys.exit(1 if FAILURES else 0)
