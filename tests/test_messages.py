"""Offline tests voor de Berichtjes-app (tech.weyn.messages).

Draait op gewone Python tegen de stubs in tests/stubs/, zodat de berichtlogica en
de schermlogica na te kijken zijn zonder badge en zonder broker.

    python3 tests/test_messages.py

**De MQTT-kant staat hier niet meer in.** Die is verhuisd naar tech.weyn.badgecontroller, en
wat daarover te testen valt staat in tests/test_badge.py: verbinden, de last
will, het client-id uit het MAC, de discovery en de batterij. Wat hier overblijft
is wat deze app zelf doet: een bericht aannemen, het tonen, en het bevestigen.

De brug wordt hier vervangen door een nep-exemplaar in sys.modules. Dat is niet
alleen makkelijker dan de echte, het is ook precies hoe de app hem in het echt
vindt: apps kunnen elkaar niet importeren, maar delen wel één sys.modules.
"""

import os
import sys
import types

sys.dont_write_bytecode = True   # laat nooit __pycache__ in de app-map achter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP_DIR = os.path.join(ROOT, "tech.weyn.messages")
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, APP_DIR)

_config = types.ModuleType("messages_config")
_config.LED_ALERT = True
_config.ACK_TIMEOUT_MIN = 30
sys.modules["messages_config"] = _config


# --- de nep-brug ------------------------------------------------------------
# Zo klein als de echte API is. Dat de app met zo weinig toe kan is zelf een
# uitkomst: alles wat de brug meer zou moeten aanbieden is iets dat eigenlijk
# aan de kant van de badge hoort.

class FakeBridge:
    BADGE_NAME = "alice"
    connected = True
    last_error = None
    subscribers = {}
    published = []
    wakes = 0
    publish_ok = True
    klok = "18:30"

    @classmethod
    def reset(cls):
        cls.BADGE_NAME = "alice"
        cls.connected = True
        cls.last_error = None
        cls.subscribers = {}
        cls.published = []
        cls.wakes = 0
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
        cls.wakes += 1
        return True

    @classmethod
    def clock_text(cls, epoch):
        return cls.klok if epoch else ""

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


import lvgl as lv                                     # noqa: E402
import mpos                                           # noqa: E402
import mpos.ui                                        # noqa: E402
import mpos.config                                    # noqa: E402
from mpos.lights import LightsManager                 # noqa: E402

import messages_service as service                  # noqa: E402
from messages_service import MessagesService      # noqa: E402
from messages import Messages                     # noqa: E402
from msgsettings import MessagesSettings             # noqa: E402
from msgsend import MessagesSend, grid                # noqa: E402

FAILURES = []
CHECKS = {"n": 0}


def check(label, condition):
    CHECKS["n"] += 1
    if not condition:
        FAILURES.append(label)
        print("FAIL:", label)


def equal(label, got, want):
    check("%s (got %r, want %r)" % (label, got, want), got == want)


class Clock:
    now = 1_000_000.0

    @classmethod
    def time(cls):
        return cls.now

    @classmethod
    def advance(cls, seconds):
        cls.now += seconds


_fake_time = types.ModuleType("time")
_fake_time.time = Clock.time
service.time = _fake_time


def fresh_service(met_brug=True):
    """Een service met of zonder brug in sys.modules."""
    LightsManager.reset()
    mpos.config._STORE.clear()
    mpos.NotificationManager.reset()
    mpos.AppManager.reset()
    mpos.TaskManager.reset()
    FakeBridge.reset()
    Clock.now = 1_000_000.0

    if met_brug:
        sys.modules[service.BRIDGE_MODULE] = FakeBridge
    else:
        sys.modules.pop(service.BRIDGE_MODULE, None)

    service.last_message = None
    service.last_message_seq = 0
    service.last_message_time = None
    service.acked_seq = 0
    service.connected = False
    service.last_error = None
    # _leds_write slaat een schrijfactie over als de strip al toont wat gevraagd
    # wordt, dus een blijven staan vlag hier zou de LED-controles om de verkeerde
    # reden laten slagen.
    service.leds_lit = False
    service.pending_ack = None
    service.LED_ALERT = True
    service.ACK_TIMEOUT_MIN = 30
    service.CHILD_NAME = "badge"
    service.buttons = []
    service.buttons_title = service.DEFAULT_SEND_TITLE
    service.buttons_seq = 0
    service.send_error = None

    svc = MessagesService()
    svc.onCreate()
    svc.onStart(None)
    svc._pump()          # de eerste pomp zoekt de brug en abonneert
    return svc


# ===========================================================================
# De brug vinden
# ===========================================================================

svc = fresh_service()
equal("de app abonneert zich op achtervoegsels en niet op topics",
      sorted(FakeBridge.subscribers), ["buttons", "msg"])
equal("de naam van de badge is geleend", service.CHILD_NAME, "alice")
equal("en de verbinding ook", service.connected, True)
equal("geen klacht als de brug er is", service.bridge_missing_reason(), None)

# De volgorde waarin services starten ligt niet vast. Een app die de brug één
# keer mist en dat onthoudt zou hem nooit meer vinden.
svc = fresh_service(met_brug=False)
equal("zonder brug niet verbonden", service.connected, False)
equal("en het zegt waarom", service.bridge_missing_reason(), "Badge-app draait niet")
sys.modules[service.BRIDGE_MODULE] = FakeBridge
svc._pump()
equal("een brug die later opstart wordt alsnog gevonden",
      service.connected, True)
equal("en er wordt alsnog geabonneerd", sorted(FakeBridge.subscribers),
      ["buttons", "msg"])

# Zonder brug mag niets omvallen: geen tijd, geen naam, geen ack, maar ook geen
# traceback.
svc = fresh_service(met_brug=False)
equal("zonder brug geen tijdstip", service.clock_text(1_000_000.0), "")
equal("zonder brug lukt een ack niet", service.publish_ack(1), False)


# ===========================================================================
# Ontvangen
# ===========================================================================

svc = fresh_service()
FakeBridge.deliver("msg", "Eten over 10 minuten")

equal("eerste bericht bewaard", service.last_message, "Eten over 10 minuten")
equal("de teller begint op een", service.last_message_seq, 1)
check("tijdstip genoteerd", service.last_message_time is not None)
equal("een melding geplaatst", len(mpos.NotificationManager.posted), 1)
equal("app naar de voorgrond", mpos.AppManager.started, ["tech.weyn.messages"])
equal("alle vijf LEDs aan bij aankomst", LightsManager.lit(), 5)
check("er staat een onbevestigd bericht", service.has_unacked())

# Een bericht op een donkere badge is geen bericht. De brug bezit het scherm.
equal("het scherm wordt gewekt", FakeBridge.wakes, 1)

posted = mpos.NotificationManager.posted[0]
equal("de melding draagt de tekst", posted.text, "Eten over 10 minuten")
equal("de melding is hoge prioriteit", posted.priority,
      mpos.Notification.PRIORITY_HIGH)
equal("de melding hoort bij deze app", posted.app_fullname,
      "tech.weyn.messages")
check("het pictogram is een niet-lege string",
      isinstance(posted.icon, str) and posted.icon)
equal("erop tikken opent deze app", posted.intent.app_fullname,
      "tech.weyn.messages")
equal("de titel is de naam van de badge, met hoofdletter", posted.title, "Alice")

# De voor de hand liggende manier om deze app te schrijven is de binnenkomende
# tekst met de vorige vergelijken om dubbels te vermijden. Dat slikt stilletjes
# het tweede "Eten over 10 minuten" van de avond op, precies het bericht dat
# telt.
FakeBridge.deliver("msg", "Eten over 10 minuten")
equal("dezelfde tekst twee keer is twee berichten", service.last_message_seq, 2)
equal("en waarschuwt twee keer", len(mpos.AppManager.started), 2)

svc = fresh_service()
FakeBridge.deliver("msg", "   ")
equal("lege payload genegeerd", service.last_message_seq, 0)
equal("geen melding voor een lege payload",
      len(mpos.NotificationManager.posted), 0)

svc = fresh_service()
FakeBridge.deliver("msg", b"\xff\xfe kapot")
check("een payload die niet te decoderen is laat de service leven",
      service.last_message_seq == 1)

svc = fresh_service()
FakeBridge.deliver("msg", " Kom eens naar beneden\n")
equal("de payload is bijgesneden", service.last_message,
      "Kom eens naar beneden")


# ===========================================================================
# Bevestigen
# ===========================================================================

svc = fresh_service()
FakeBridge.deliver("msg", "Eten")
equal("bevestigen lukt", service.publish_ack(), True)
equal("en gaat naar het ack-achtervoegsel",
      FakeBridge.published[-1], ("ack", "Eten"))
equal("de LEDs gaan uit", LightsManager.lit(), 0)
check("er staat niets meer open", not service.has_unacked())

# Het mag niet twee keer verstuurd worden: dat zou de wachtklok van Home
# Assistant herstarten voor een bericht dat niemand net gelezen heeft.
aantal = len(FakeBridge.published)
equal("een tweede tik stuurt niets", service.publish_ack(), False)
equal("en publiceert dus niets", len(FakeBridge.published), aantal)

# Een slaapkamer aan de rand van de wifi is precies waar een kind op de knop
# drukt en de publish mislukt. Kwijtraken betekent dat Home Assistant een half
# uur rood staat voor een bericht dat gelezen is.
svc = fresh_service()
FakeBridge.deliver("msg", "Eten")
FakeBridge.publish_ok = False
equal("zonder link mislukt het versturen", service.publish_ack(), False)
check("maar hij is wel bewaard", service.pending_ack == "Eten")
check("en lokaal als bevestigd geteld", not service.has_unacked())
equal("de LEDs gaan toch uit", LightsManager.lit(), 0)

FakeBridge.publish_ok = True
svc._pump()
equal("zodra de link terug is gaat hij alsnog weg",
      FakeBridge.published[-1], ("ack", "Eten"))
equal("en wordt hij niet nog eens vastgehouden", service.pending_ack, None)


# ===========================================================================
# LEDs
# ===========================================================================

svc = fresh_service()
FakeBridge.deliver("msg", "Eten")
equal("aan bij aankomst", LightsManager.lit(), 5)
service._leds_tick()
equal("en knipperen", LightsManager.lit(), 0)
service._leds_tick()
equal("heen en weer", LightsManager.lit(), 5)

# Een lampje dat de hele nacht flikkert in een slaapkamer is erger dan een
# bericht dat niemand beantwoordde. Het bericht blijft wel staan.
Clock.advance(service.ACK_TIMEOUT_MIN * 60 + 1)
service._leds_tick()
equal("na de tijd stopt het knipperen", LightsManager.lit(), 0)
check("het bericht staat er nog", service.last_message == "Eten")
check("en is nog te bevestigen", service.has_unacked())

svc = fresh_service()
service.LED_ALERT = False
FakeBridge.deliver("msg", "Eten")
equal("met de LEDs uit blijft het donker", LightsManager.lit(), 0)


# ===========================================================================
# Eén lus
# ===========================================================================

svc = fresh_service()
taken = len(mpos.TaskManager.tasks)
svc.onStart(None)
equal("twee keer starten geeft geen tweede lus",
      len(mpos.TaskManager.tasks), taken)

tweede = MessagesService()
tweede.onCreate()
equal("de nieuwe instantie is de service", service._service, tweede)
equal("en de oude is stilgezet", svc._running, False)


# ===========================================================================
# Het scherm
# ===========================================================================

def fresh_screen():
    svc = fresh_service()
    scherm = Messages()
    scherm.onCreate()
    scherm.onResume(scherm._view)
    return svc, scherm


svc, scherm = fresh_screen()
equal("zonder bericht staat er een nette zin", scherm.msg_label.text,
      "Geen berichten")
equal("de naam van de badge staat bovenaan", scherm.title.text, "Alice")
equal("en de verbinding klopt", scherm.link.text, "verbonden")

FakeBridge.deliver("msg", "Eten over 10 minuten")
scherm._refresh()
equal("het bericht staat op het scherm", scherm.msg_label.text,
      "Eten over 10 minuten")
equal("met het tijdstip erbij", scherm.time_label.text, "gestuurd om 18:30")
equal("en het zegt dat het nieuw is", scherm.status_label.text, "Nieuw bericht!")

scherm.ack_btn.click()
equal("tikken bevestigt", scherm.status_label.text, "Bevestigd")
equal("en het ging de deur uit", FakeBridge.published[-1], ("ack", "Eten over 10 minuten"))

# Het scherm is eerlijk: gelezen op de badge maar niet afgeleverd is niet
# hetzelfde als bevestigd.
svc, scherm = fresh_screen()
FakeBridge.deliver("msg", "Eten")
scherm._refresh()
FakeBridge.publish_ok = False
scherm.ack_btn.click()
equal("een mislukte verzending zegt dat ook",
      scherm.status_label.text, "Bevestigd, nog niet verzonden")
FakeBridge.publish_ok = True
svc._pump()
scherm._refresh()
equal("en wordt vanzelf Bevestigd zodra het weg is",
      scherm.status_label.text, "Bevestigd")

# "geen Badge-app" en "geen verbinding" vragen om verschillende reparaties.
svc, scherm = fresh_screen()
FakeBridge.connected = False
scherm._refresh()
equal("geen broker zegt geen verbinding", scherm.link.text, "geen verbinding")
sys.modules.pop(service.BRIDGE_MODULE, None)
scherm._refresh()
equal("geen brug zegt geen Badge-app", scherm.link.text, "geen Badge-app")
sys.modules[service.BRIDGE_MODULE] = FakeBridge

# Een naam die in de Badge-app wijzigt hoort hier zonder herstart door te komen.
svc, scherm = fresh_screen()
FakeBridge.BADGE_NAME = "bob"
scherm._refresh()
equal("een hernoeming komt door op het scherm", scherm.title.text, "Bob")

# Trefvlakken. Events versturen bewijst niets over een vinger: een knop van 60
# bij 24 aan de rand van een rij is met een duim niet te raken.
svc, scherm = fresh_screen()
for naam, knop in (("Ontvangen", scherm.ack_btn), ("tandwiel", scherm.gear_btn)):
    check("de %s-knop is minstens 44 hoog" % naam,
          knop.size is not None and knop.size[1] >= 44)


# ===========================================================================
# Het instelscherm
# ===========================================================================

svc = fresh_service()
instellingen = MessagesSettings()
instellingen.onCreate()
instellingen.onResume(instellingen._view)

# Het scherm scrollt niet, dus alles moet passen: 16 voor de titel plus de
# rijen en hun gaten binnen 224.
hoogte = 16 + instellingen.rows * (instellingen.ROW_HEIGHT if hasattr(
    instellingen, "ROW_HEIGHT") else 44)
hoogte += instellingen.rows * 6
check("de rijen passen op het scherm", hoogte <= 224)
equal("drie rijen: badge, LEDs, stoppen na", instellingen.rows, 3)

voor = len(mpos.AppManager.started)
instellingen._open_badge()
equal("de knop opent de Badge-app", mpos.AppManager.started[-1],
      "tech.weyn.badgecontroller")
check("en start niet zichzelf", len(mpos.AppManager.started) == voor + 1)

instellingen._cycle_timeout(-1)
equal("de timeout gaat in stappen van vijf", instellingen.timeout_min, 25)
for _ in range(20):
    instellingen._cycle_timeout(-1)
equal("en zakt niet onder de vijf minuten", instellingen.timeout_min, 5)
for _ in range(30):
    instellingen._cycle_timeout(1)
equal("en gaat niet boven het uur", instellingen.timeout_min, 60)

instellingen.led_alert = False
instellingen.timeout_min = 15
instellingen.onPause(instellingen._view)
equal("bewaren werkt", service.ACK_TIMEOUT_MIN, 15)
equal("en de LED-instelling ook", service.LED_ALERT, False)

# Zonder brug hoort het instelscherm te zeggen wat er scheelt, want anders komt
# er niets binnen en legt niets uit waarom.
svc = fresh_service(met_brug=False)
instellingen = MessagesSettings()
instellingen.onCreate()
equal("het instelscherm klaagt over de ontbrekende app",
      instellingen.hint.text, "Badge-app draait niet")


# ===========================================================================
# Wat MicroPython niet heeft
# ===========================================================================

with open(os.path.join(APP_DIR, "messages_service.py")) as fh:
    SOURCE = fh.read()
check("de service bouwt geen widgets",
      "lv.obj(" not in SOURCE and "lv.label(" not in SOURCE)
# Een gewone import zou werken zolang deze app als laatste laadt en dan stil
# breken zodra de volgorde wisselt. Het moet de opzoeking in sys.modules zijn.
# Alleen echte importregels tellen; het commentaar mag het woord noemen.
check("de service importeert de brug niet rechtstreeks",
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
    check("%s definieert geen functie die const heet" % name,
          "def const(" not in text)

check("titlecase vervangt str.capitalize", service.titlecase("alice") == "Alice")
check("titlecase overleeft een lege naam", service.titlecase("") == "")


# ===========================================================================
# Instellingen overnemen van de oude app-id
# ===========================================================================
# Voorkeuren hangen aan het app-id, dus de hernoeming naar tech.weyn.messages
# zou de LED-keuze en de wachttijd stil terugzetten.

mpos.config._STORE.clear()
oud = mpos.config.SharedPreferences("be.weyn.dinerbadge").edit()
oud.put_int("ack_timeout_min", 45)
oud.put_int("led_alert", 0)      # uit is een bewuste nul
oud.commit()

equal("er valt iets over te nemen", service.migrate_prefs(), True)
nieuw = mpos.config.SharedPreferences(service.PREFS_APP_ID)
equal("de wachttijd is mee", nieuw.get_int("ack_timeout_min", 0), 45)
equal("en de LEDs blijven uit", nieuw.get_int("led_alert", 1), 0)
equal("een tweede keer neemt niets meer over", service.migrate_prefs(), False)

# De naam van vanmiddag telt ook mee: tech.weyn.dinerbadge heeft een uur
# bestaan, en een badge die in dat uur bijwerkte mag niets kwijt zijn.
mpos.config._STORE.clear()
kort = mpos.config.SharedPreferences("tech.weyn.dinerbadge").edit()
kort.put_int("ack_timeout_min", 20)
kort.commit()
equal("ook de naam van een uur oud telt", service.migrate_prefs(), True)
equal("en de wachttijd is mee",
      mpos.config.SharedPreferences(service.PREFS_APP_ID).get_int(
          "ack_timeout_min", 0), 20)

mpos.config._STORE.clear()
equal("zonder oude voorkeuren valt er niets over te nemen",
      service.migrate_prefs(), False)


# ===========================================================================
# Zelf sturen: de knoppen
# ===========================================================================

import json as _json                                   # noqa: E402

KNOPPEN = _json.dumps({
    "title": "Roepen",
    "buttons": [
        {"label": "15 eten", "target": "nina", "text": "Eten binnen 15 minuten",
         "figure": "woman", "color": "e05a8a"},
        {"label": "nu eten", "target": "nina", "text": "Eten is klaar",
         "figure": "woman", "color": "e05a8a"},
        {"label": "15 eten", "target": "mattijs", "text": "Eten binnen 15 minuten",
         "figure": "man", "color": "3a7bd5"},
        {"label": "nu eten", "target": "mattijs", "text": "Eten is klaar",
         "figure": "man", "color": "3a7bd5"},
    ],
})

svc = fresh_service()
equal("een badge zonder configuratie heeft geen knoppen",
      service.visible_buttons(), [])

FakeBridge.deliver("buttons", KNOPPEN)
equal("de knoppen komen binnen", len(service.buttons), 4)
equal("met hun eigen titel", service.buttons_title, "Roepen")
equal("doel en tekst blijven heel", service.buttons[0]["target"], "nina")
equal("en de tekst ook", service.buttons[0]["text"], "Eten binnen 15 minuten")
equal("het opschrift is wat er staat", service.buttons[0]["label"], "15 eten")
equal("de vorm reist mee", service.buttons[2]["figure"], "man")
equal("er is iets veranderd", service.buttons_seq, 1)

# Twee keer hetzelfde publiceren is geen wijziging. Anders bouwt het scherm zijn
# raster opnieuw op bij elke herverbinding, en dat ziet een vinger als knipperen.
FakeBridge.deliver("buttons", KNOPPEN)
equal("dezelfde configuratie verandert niets", service.buttons_seq, 1)

# De app kent geen namen. Alles wat er staat komt van Home Assistant, dus alles
# wat er niet deugt hoort hier te sneuvelen en niet op het scherm.
svc = fresh_service()
service.set_buttons(_json.dumps([
    {"target": "nina", "text": "Kom eens"},
    {"target": "", "text": "Zonder doel"},
    {"target": "bob", "text": ""},
    "geen woordenboek",
    {"target": "BOB", "text": "  Hoofdletters en spaties  "},
]))
equal("wat geen doel of tekst heeft valt af", len(service.buttons), 2)
equal("een doel wordt kleingeletterd", service.buttons[1]["target"], "bob")
equal("en de tekst getrimd", service.buttons[1]["text"], "Hoofdletters en spaties")
equal("zonder opschrift wordt het het doel", service.buttons[0]["label"], "Nina")

# Meer knoppen dan er op het scherm passen is geen fout, maar ze allemaal tonen
# maakt er knoppen van die je niet raakt.
svc = fresh_service()
service.set_buttons(_json.dumps([{"target": "nina", "text": "n%d" % i}
                                 for i in range(30)]))
equal("de lijst wordt afgekapt", len(service.buttons), service.MAX_BUTTONS)

# Een lege retained payload is hoe MQTT "vergeet dit" zegt.
svc = fresh_service()
FakeBridge.deliver("buttons", KNOPPEN)
FakeBridge.deliver("buttons", "")
equal("een lege payload wist de knoppen", service.buttons, [])

# Stukke JSON is iets anders dan een lege payload: dan is er ergens een fout
# gemaakt, en een werkend paneel weggooien helpt niemand.
svc = fresh_service()
FakeBridge.deliver("buttons", KNOPPEN)
FakeBridge.deliver("buttons", "{dit is geen json")
equal("onleesbare configuratie laat staan wat er stond",
      len(service.buttons), 4)

# Na een herstart moeten de knoppen er meteen staan, niet pas als de broker
# antwoordt.
svc = fresh_service()
FakeBridge.deliver("buttons", KNOPPEN)
service.buttons = []
service.buttons_seq = 0
equal("de knoppen zijn bewaard", service.load_cached_buttons(), True)
equal("en staan er weer", len(service.buttons), 4)

# Naar zichzelf sturen laat een badge zichzelf piepen. Dat is nooit de bedoeling,
# en het wordt gefilterd op de naam van nu en niet op die van toen de knoppen
# binnenkwamen.
svc = fresh_service()
FakeBridge.deliver("buttons", _json.dumps([
    {"target": "nina", "text": "Kom eens"},
    {"target": "alice", "text": "Naar mezelf"},
]))
equal("de knop naar zichzelf wordt niet getoond",
      [b["target"] for b in service.visible_buttons()], ["nina"])
FakeBridge.BADGE_NAME = "nina"
svc._pump()
equal("en na een hernoeming schuift dat mee",
      [b["target"] for b in service.visible_buttons()], ["alice"])


# ===========================================================================
# Zelf sturen: de druk
# ===========================================================================

svc = fresh_service()
FakeBridge.deliver("buttons", KNOPPEN)
knop = service.visible_buttons()[0]
equal("een druk komt weg", service.publish_send(knop), True)
suffix, payload = FakeBridge.published[-1]
equal("op het send-topic van deze badge", suffix, "send")
verzoek = _json.loads(payload)
equal("met het doel erin", verzoek["target"], "nina")
equal("de tekst voluit", verzoek["text"], "Eten binnen 15 minuten")
equal("en wie het stuurde", verzoek["from"], "alice")
check("niets blijft hangen", service.pending_ack is None)
check("en er is niets mis", service.send_error is None)

# Een bevestiging blijft wachten tot ze aankomt. "Eten binnen tien minuten" is
# een half uur later geen bericht meer maar een leugen, dus die niet.
svc = fresh_service()
FakeBridge.deliver("buttons", KNOPPEN)
knop = service.visible_buttons()[0]
FakeBridge.publish_ok = False
equal("zonder link mislukt de druk", service.publish_send(knop), False)
equal("en het zegt waarom", service.send_error, "geen verbinding")
FakeBridge.publish_ok = True
svc._pump()
equal("er wordt niets nagestuurd", FakeBridge.published, [])

svc = fresh_service(met_brug=False)
equal("zonder brug mislukt de druk ook",
      service.publish_send({"target": "nina", "text": "Kom"}), False)
equal("met de reden die ertoe doet", service.send_error, "Badge-app draait niet")

svc = fresh_service()
equal("naar zichzelf sturen wordt geweigerd",
      service.publish_send({"target": "alice", "text": "Kom"}), False)
equal("ook als de knop er langs het scherm om komt",
      service.send_error, "niet naar zichzelf")


# ===========================================================================
# Zelf sturen: het scherm
# ===========================================================================

# Het raster, zonder scherm na te rekenen. Onder de 44 is een knop een knop die
# je niet raakt.
for aantal, kolommen in ((1, 2), (4, 2), (6, 3), (8, 4), (12, 4)):
    cols, rows, cell_w, cell_h = grid(aantal)
    equal("%d knoppen geeft %d kolommen" % (aantal, kolommen), cols, kolommen)
    check("%d knoppen: elke knop is minstens 44 hoog" % aantal, cell_h >= 44)
    check("%d knoppen: en minstens 44 breed" % aantal, cell_w >= 44)
    check("%d knoppen: alles past op 320 breed" % aantal,
          cols * cell_w + (cols - 1) * 6 <= 308)
    check("%d knoppen: en op 240 hoog" % aantal,
          rows * cell_h + (rows - 1) * 6 <= 206)

equal("acht knoppen worden vier bij twee", grid(8)[:2], (4, 2))
equal("twaalf knoppen vier bij drie", grid(12)[:2], (4, 3))


def stuurscherm():
    scherm = MessagesSend()
    scherm.onCreate()
    scherm.onResume(scherm._view)
    return scherm


svc = fresh_service()
FakeBridge.deliver("buttons", KNOPPEN)
scherm = stuurscherm()
knoppen = [k for k in scherm.holder.children if k.cbs]
equal("er staat een knop per configuratieregel", len(knoppen), 4)
equal("de titel komt uit de configuratie", scherm.title.text, "Roepen")
check("de knoppen zijn vingergroot",
      all(k.size is not None and k.size[1] >= 44 for k in knoppen))

knoppen[0].click()
equal("drukken stuurt", FakeBridge.published[-1][0], "send")
equal("en het scherm zegt het", scherm.status.text, "verstuurd")

FakeBridge.publish_ok = False
knoppen[1].click()
equal("een mislukte druk zegt waarom", scherm.status.text, "geen verbinding")

# Zonder configuratie is het scherm niet leeg maar behulpzaam: er staat waar de
# knoppen vandaan zouden moeten komen.
svc = fresh_service()
scherm = stuurscherm()
equal("zonder knoppen geen knoppen",
      [k for k in scherm.holder.children if k.cbs], [])
check("maar wel uitleg",
      any("buttons" in (k.text or "") for k in scherm.holder.children))

# De stuurknop op het hoofdscherm bestaat alleen op een badge die mag sturen.
svc, hoofd = fresh_screen()
check("geen stuurknop zonder configuratie",
      hoofd.send_btn.has_flag(lv.obj.FLAG.HIDDEN))
FakeBridge.deliver("buttons", KNOPPEN)
hoofd._refresh()
check("met configuratie staat hij er",
      not hoofd.send_btn.has_flag(lv.obj.FLAG.HIDDEN))
check("en hij is vingergroot",
      hoofd.send_btn.size is not None and hoofd.send_btn.size[1] >= 44)

# Een bijgewerkte activity draait meteen, een service pas na een herstart. In dat
# uur praat nieuw schermwerk met een oude service, en dat is geen hypothese: het
# gebeurde bij de eerste installatie op de badge. Geen stuurknop is het goede
# antwoord, een traceback op het scherm van een kind niet.
_seq, _zichtbaar = service.buttons_seq, service.visible_buttons
del service.buttons_seq
del service.visible_buttons
try:
    hoofd._shown_send = None
    hoofd._refresh()
    check("een oude service geeft geen stuurknop en geen fout",
          hoofd.send_btn.has_flag(lv.obj.FLAG.HIDDEN))
finally:
    service.buttons_seq, service.visible_buttons = _seq, _zichtbaar

# ===========================================================================

print("\n%d checks, %d mislukt" % (CHECKS["n"], len(FAILURES)))
for f in FAILURES:
    print("  -", f)
sys.exit(1 if FAILURES else 0)
