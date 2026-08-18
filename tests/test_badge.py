"""Offline tests voor de Badge-app (tech.weyn.badgecontroller).

Draait op gewone Python tegen de stubs in tests/stubs/, zodat de MQTT-brug, de
telemetrie en de schermdimmer na te kijken zijn zonder badge en zonder broker.

    python3 tests/test_badge.py

Het grootste deel van wat hier staat komt uit test_messages.py. Die code is
mee verhuisd met de verbinding: het brokeradres, de last will, het client-id uit
het MAC en de discovery zijn eigenschappen van de badge en niet van een app die
berichten toont. De commentaren zijn meegekomen, want daar staat in wat ze een
keer gekost hebben.
"""

import json
import os
import sys
import types

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP_DIR = os.path.join(ROOT, "tech.weyn.badgecontroller")
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, APP_DIR)

# badge_config.py is gitignored en houdt het echte wachtwoord, dus de app-map
# heeft er misschien geen, en als hij er wel een heeft mogen de tests er niet
# van afhangen. Zet er een bekende in.
_config = types.ModuleType("badge_config")
_config.BADGE_NAME = "alice"
_config.MQTT_BROKER = "broker.example"
_config.MQTT_PORT = 1883
_config.MQTT_USER = "example-user"
_config.MQTT_PASS = "example-secret"
_config.DISCOVERY_PREFIX = "homeassistant"
_config.SCREEN_OFF_S = 0
_config.DEBUG_LED = 0
_config.IDLE_MODE = "uit"
_config.CLOCK_DAY = 30
_config.CLOCK_NIGHT = 5
_config.NIGHT_FROM = 23
_config.NIGHT_TO = 7
_config.WEER_TOPIC = "home/badges/weer"
_config.TIMEZONE = "CET-1CEST,M3.5.0,M10.5.0/3"
sys.modules["badge_config"] = _config

import network                                        # noqa: E402
from umqtt.simple import BROKER                       # noqa: E402
import mpos                                           # noqa: E402
import mpos.ui                                        # noqa: E402
import mpos.config                                    # noqa: E402
import mpos.board                                     # noqa: E402

import badge_service as service                       # noqa: E402
from badge_service import BadgeService                # noqa: E402

FAILURES = []
CHECKS = {"n": 0}


def check(label, condition):
    CHECKS["n"] += 1
    if not condition:
        FAILURES.append(label)
        print("FAIL:", label)


def equal(label, got, want):
    check("%s (got %r, want %r)" % (label, got, want), got == want)


# --- een klok die wij zetten ------------------------------------------------
# De service plant herverbindingen op time.time(). De tests moeten dat vooruit
# kunnen zetten zonder te slapen.

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


# nu_epoch wordt in de schermtests vervangen door een vast tijdstip; hier staat
# het origineel zodat elke verse service er weer mee begint.
_echte_nu_epoch = service.nu_epoch


def fresh_service(**prefs):
    """Een brug op een werkende broker, verbonden."""
    BROKER.reset()
    mpos.config._STORE.clear()
    mpos.TaskManager.reset()
    mpos.ui.main_display.reset()
    mpos.io_expander.reset()
    network.STATE["active"] = True
    network.STATE["connected"] = True
    network.STATE["rssi"] = -54
    mpos.BatteryManager.reset()
    Clock.now = 1_000_000.0

    service._subscribers.clear()
    service.connected = False
    service.last_error = None
    service.battery_pct = None
    service.battery_volt = None
    service.wifi_rssi = None
    service.screen_off = False
    service._bright_saved = None
    service.screen_state = service.SCHERM_NORMAAL
    service._vorige_stil = 0
    service._kijk_tot = 0
    service._kijk_negeer = 0
    service._overlay = None
    service._klok_seconde = None
    service._klok_bright = None
    service._knop = None
    service._knop_vorige = 1
    service._expander_vorige = None
    service.weer = {}
    service.nu_epoch = _echte_nu_epoch
    mpos.board.fri3d_2026.btn_start.release()
    service.SCREEN_OFF_S = 0
    service.DEBUG_LED = 0
    service.IDLE_MODE = "uit"
    service.CLOCK_DAY = 30
    service.CLOCK_NIGHT = 5
    service.NIGHT_FROM = 23
    service.NIGHT_TO = 7
    service.MQTT_BROKER = _config.MQTT_BROKER
    service.MQTT_PORT = _config.MQTT_PORT
    service.MQTT_USER = _config.MQTT_USER
    service.MQTT_PASS = _config.MQTT_PASS
    service.set_badge_name("alice")
    for key, value in prefs.items():
        setattr(service, key, value)

    svc = BadgeService()
    svc.onCreate()
    svc.onStart(None)
    svc._pump()          # de eerste pomp verbindt
    return svc


def _regel_in_bron(tekst):
    for i, regel in enumerate(SOURCE.split("\n")):
        if regel.strip() == tekst:
            return i
    return -1


def configs():
    """De discoveryberichten, op topic."""
    return dict((topic, payload) for topic, payload in BROKER.published
                if topic.startswith("homeassistant/"))


def abos():
    """De abonnementen bij de broker, zonder het weertopic.

    Het weer is geen app die zich aanmeldt maar iets wat de service zelf neemt,
    dus het hoort niet thuis in een test over de API voor apps."""
    return [t for t in BROKER.subscriptions if t != service.WEER_TOPIC]


def suffixen():
    return [s for s in service._subscribers if s != service.WEER_TOPIC]


def published(suffix):
    return [(t, p) for t, p in BROKER.published if t.endswith("/" + suffix)]


# ===========================================================================
# Topics, identiteit en configuratie
# ===========================================================================

equal("topicprefix draagt de naam", service.TOPIC_PREFIX, "home/badges/alice/")
equal("topic() plakt het achtervoegsel eraan", service.topic("msg"),
      "home/badges/alice/msg")
equal("een volledig topic blijft zoals het is",
      service.topic("homeassistant/status"), "homeassistant/status")
equal("statustopic", service.TOPIC_STATUS, "home/badges/alice/status")
equal("client-id is per badge en per toestel", service.CLIENT_ID,
      "badge_alice_" + service.DEVICE_SUFFIX)
check("configbestand is opgepikt", service.CONFIG_OK)
equal("de login komt uit de config", service.MQTT_USER, "example-user")

# De service mag geen LVGL-objecten maken: een service heeft geen scherm.
# Controleer de broncode, en vertrouw niet op een commentaar dat waar blijft.
with open(os.path.join(APP_DIR, "badge_service.py")) as fh:
    SOURCE = fh.read()
check("de service bouwt geen widgets",
      "lv.obj(" not in SOURCE and "lv.label(" not in SOURCE)

# bgclock wordt bij het importeren van deze module geladen en niet pas als er een
# klok nodig is. Een service draait met sys.path op ['lib', '', '.frozen', '/lib']
# en cwd op '/', en de map van de app staat daar niet in: een import binnen een
# functie geeft daar ImportError. Op de badge gemeten. Het gevolg was stil, en
# dat is het ergste soort: de badge ging gewoon uit in plaats van een klok te
# tonen, want zonder klok is donker beter dan een verlicht leeg scherm.
check("bgclock wordt op modulehoogte geladen",
      _regel_in_bron("import bgclock as _bgclock") > 0)
equal("en er staat er maar een",
      [r.strip() for r in SOURCE.split("\n")
       if r.strip().startswith("import bgclock")],
      ["import bgclock as _bgclock"])

# CPython heeft deze; MicroPython 1.27 op deze badge niet. Gemeten met dir(str)
# op het toestel. Een desktoptest kan een aanroep hiervan niet vangen, want
# desktop Python antwoordt gewoon en de badge gooit AttributeError.
MISSING_ON_BADGE = (
    "capitalize", "casefold", "expandtabs", "format_map", "isdecimal",
    "isidentifier", "isprintable", "ljust", "maketrans", "removeprefix",
    "removesuffix", "rjust", "swapcase", "title", "translate", "zfill",
)
# En dit: een module-level NAAM = const(...) wordt door de compiler onderschept
# als constantendeclaratie en laat de hele module vallen met
# SyntaxError: not a constant.
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
    for regel in text.split("\n"):
        gestript = regel.strip()
        if gestript.startswith("#") or "`" in gestript:
            continue
        check("%s: %s wordt als constante gelezen" % (name, gestript[:32]),
              " = const(" not in gestript)

check("titlecase vervangt str.capitalize", service.titlecase("alice") == "Alice")
check("titlecase overleeft een lege naam", service.titlecase("") == "")

equal("een naam met spaties wordt een topicnaam",
      service.normalize_name("  Test Naam!  "), "test-naam")
equal("schuine strepen vallen weg", service.normalize_name("a/b#c"), "abc")
equal("een lege naam blijft leeg", service.normalize_name("///"), "")

equal("een poort buiten bereik telt niet", service.normalize_port("70000"), 0)
equal("een poort die geen getal is telt niet", service.normalize_port("x"), 0)
equal("een gewone poort telt wel", service.normalize_port(" 1883 "), 1883)


# ===========================================================================
# Verbinden
# ===========================================================================

svc = fresh_service()
equal("verbonden na de eerste pomp", service.connected, True)
check("de login is aan de client gegeven",
      svc._mqtt.user == "example-user" and svc._mqtt.password == "example-secret")

# De last will reist mee in het CONNECT-pakket, dus hij moet ervoor gezet zijn.
# Een badge die leegloopt of buiten bereik raakt wordt anders niet offline gezet
# en blijft zijn batterijstand van gisteren tonen.
equal("de last will staat op het statustopic", BROKER.will,
      ("home/badges/alice/status", "offline", True))
equal("en online is retained", BROKER.retained.get("home/badges/alice/status"),
      "online")

# Oudere umqtt.simple-builds kennen geen socket_timeout.
BROKER.supports_socket_timeout = False
svc = fresh_service()
equal("valt terug op de oude signature zonder socket_timeout",
      service.connected, True)
BROKER.supports_socket_timeout = True

# De storing die mensen echt tegenkomen: de broker staat er en zegt nee.
svc = fresh_service()
BROKER.accept_auth = False
svc._close()
Clock.advance(120)
svc._pump()
equal("een geweigerde login staat in woorden op het scherm",
      service.last_error, "login geweigerd")
equal("en niet verbonden", service.connected, False)
BROKER.accept_auth = True

# Een badge aan een lanyard is echt tijden buiten bereik. Daar elke seconde
# opnieuw proberen kost stroom voor niets.
svc = fresh_service()
BROKER.up = False
svc._pump()
eerste = svc._backoff
svc._close()
Clock.advance(1000)
svc._pump()
check("de wachttijd verdubbelt na een mislukking", svc._backoff > eerste)
check("en loopt niet voorbij het plafond", svc._backoff <= service.RETRY_MAX)
BROKER.up = True

# Buiten wifi wordt er niet eens verbonden.
svc = fresh_service()
svc._close()
network.STATE["connected"] = False
pogingen = BROKER.attempts
Clock.advance(1000)
svc._pump()
equal("zonder wifi geen verbindingspoging", BROKER.attempts, pogingen)
network.STATE["connected"] = True

# Keepalive: de broker gooit een stille client eruit na `keepalive` seconden.
svc = fresh_service()
pings = BROKER.pings
Clock.advance(service.PING_EVERY + 1)
svc._pump()
check("er wordt gepingd binnen de keepalive", BROKER.pings > pings)


# ===========================================================================
# Abonneren en publiceren: de API waar andere apps op leunen
# ===========================================================================

ontvangen = []


def onthoud(topic, payload):
    ontvangen.append((topic, payload))


svc = fresh_service()
del ontvangen[:]
service.subscribe("msg", onthoud)
equal("abonneren vertaalt het achtervoegsel naar een topic",
      abos(), ["home/badges/alice/msg"])

BROKER.deliver("home/badges/alice/msg", "Eten over 10 minuten")
svc._pump()
equal("de abonnee kreeg het bericht", len(ontvangen), 1)
equal("met het volledige topic erbij", ontvangen[0][0], "home/badges/alice/msg")
equal("en de payload als bytes", ontvangen[0][1], b"Eten over 10 minuten")

# Een tweede keer abonneren op hetzelfde achtervoegsel vervangt de callback en
# zet er geen tweede naast: anders krijgt een app na een herstart elk bericht
# dubbel.
service.subscribe("msg", onthoud)
equal("twee keer abonneren is niet twee abonnementen",
      len(suffixen()), 1)
equal("en het levert geen tweede subscribe op", abos(),
      ["home/badges/alice/msg"])

# Een callback die gooit mag de anderen niet meenemen, en al helemaal niet de
# verbinding: een app met een bug hoort de badge niet van de broker te halen.
def stukke_callback(topic, payload):
    raise ValueError("kapot")


service.subscribe("stuk", stukke_callback)
BROKER.deliver("home/badges/alice/stuk", "x")
BROKER.deliver("home/badges/alice/msg", "nog een")
svc._pump()
svc._pump()
equal("de goede abonnee kreeg zijn bericht toch", len(ontvangen), 2)
equal("en de verbinding staat nog", service.connected, True)
service.unsubscribe("stuk")

# Publiceren gaat op achtervoegsel, en een dict wordt onderweg JSON.
equal("publiceren lukt", service.publish("ack", "gelezen"), True)
equal("op het juiste topic", published("ack")[-1][0], "home/badges/alice/ack")
service.publish("state", {"battery": 87})
laatste = published("state")[-1]
equal("een dict gaat als JSON de lijn op", json.loads(laatste[1])["battery"], 87)

BROKER.up = False
equal("zonder link geeft publiceren False terug",
      service.publish("ack", "gelezen"), False)
BROKER.up = True


# ===========================================================================
# Hernoemen
# ===========================================================================

svc = fresh_service()
del ontvangen[:]
service.subscribe("msg", onthoud)
BROKER.subscriptions[:] = []
service.set_badge_name("bob")
Clock.advance(1000)
svc._pump()
equal("na hernoemen luistert hij op de nieuwe naam", abos(),
      ["home/badges/bob/msg"])
equal("de topics zijn mee", service.topic("msg"), "home/badges/bob/msg")
equal("en het client-id ook", service.CLIENT_ID,
      "badge_bob_" + service.DEVICE_SUFFIX)

# Hernoemen laat een retained meting achter op het oude topic die niets ooit nog
# bijwerkt en niets ooit nog opruimt. Een lege payload is hoe MQTT er een wist.
equal("de retained toestand van alice is gewist",
      BROKER.retained.get("home/badges/alice/state"), "")
equal("en zijn beschikbaarheid ook",
      BROKER.retained.get("home/badges/alice/status"), "")


# ===========================================================================
# Batterij en discovery
# ===========================================================================

svc = fresh_service()
gevonden = configs()
equal("drie sensoren aangekondigd", len(gevonden), 3)

# Het unieke id bepaalt of Home Assistant de historiek bewaart over een
# hernoeming. Op het MAC gesleuteld doet hij dat; op de naam zou elke hernoeming
# de oude entiteit laten stranden en een nieuwe vanaf nul beginnen.
battery = json.loads(gevonden[
    "homeassistant/sensor/badge_%s/battery/config" % service.DEVICE_SUFFIX])
equal("het unieke id hangt aan het toestel", battery["uniq_id"],
      "fri3d_badge_%s_battery" % service.DEVICE_SUFFIX)
equal("het entity-id draagt de naam", battery["obj_id"], "badge_alice_battery")
equal("de waarde komt van het statustopic", battery["stat_t"],
      "home/badges/alice/state")
equal("beschikbaarheid hangt aan het statustopic", battery["avty_t"],
      "home/badges/alice/status")
equal("het apparaat is gesleuteld op het MAC", battery["dev"]["ids"],
      ["fri3d_badge_%s" % service.DEVICE_SUFFIX])
check("de discovery is retained",
      all(topic in BROKER.retained for topic in gevonden))

# Elke tick melden zou een zaagtand op de grafiek zetten en radioverkeer voor
# een meting die over uren beweegt.
svc = fresh_service()
voor = len(published("state"))
svc._pump()
equal("de batterij wordt niet elke tick gemeld", len(published("state")), voor)
Clock.advance(service.STATE_EVERY + 1)
svc._pump()
equal("maar wel na het interval", len(published("state")), voor + 1)

# Een badge op USB zonder cel kent zijn signaalsterkte nog steeds, en een badge
# die geen van beide kan lezen mag geen leeg object publiceren.
svc = fresh_service()
mpos.BatteryManager.present = False
Clock.advance(service.STATE_EVERY + 1)
voor = len(published("state"))
svc._pump()
staat = json.loads(published("state")[-1][1])
equal("zonder cel wordt de signaalsterkte nog gemeld", staat["rssi"], -54)
check("en er staat geen batterij in", "battery" not in staat)

mpos.BatteryManager.present = False
network.STATE["rssi"] = None
Clock.advance(service.STATE_EVERY + 1)
voor = len(published("state"))
svc._pump()
equal("niets meetbaar betekent niets publiceren", len(published("state")), voor)
network.STATE["rssi"] = -54
mpos.BatteryManager.reset()


class _BrokenBattery:
    """Een ADC die gooit is een echte storing, en dan moet de rest doorgaan."""

    @staticmethod
    def has_battery():
        return True

    @staticmethod
    def get_battery_percentage():
        raise OSError("adc kapot")

    @staticmethod
    def read_battery_voltage():
        raise OSError("adc kapot")


svc = fresh_service()
echte_manager = mpos.BatteryManager
mpos.BatteryManager = _BrokenBattery
try:
    Clock.advance(service.STATE_EVERY + 1)
    svc._pump()
    staat = json.loads(published("state")[-1][1])
    equal("een kapotte ADC houdt de signaalsterkte niet tegen", staat["rssi"], -54)
    equal("en de verbinding blijft staan", service.connected, True)
finally:
    mpos.BatteryManager = echte_manager


# ===========================================================================
# Eén lus, wat er ook gebeurt
# ===========================================================================
# Twee lussen op één service delen zijn client en zijn client-id, en de broker
# gooit de oudste van twee clients met dezelfde id eruit. Die twee duwen elkaar
# dan om beurten van de lijn, voor altijd, en het lijkt op een haperend netwerk.

svc = fresh_service()
taken = len(mpos.TaskManager.tasks)
svc.onStart(None)
equal("twee keer starten geeft geen tweede lus",
      len(mpos.TaskManager.tasks), taken)

# Een verse instantie moet het netjes overnemen in plaats van ernaast te draaien.
tweede = BadgeService()
tweede.onCreate()
equal("de nieuwe instantie is de service", service._service, tweede)
equal("en de oude is stilgezet", svc._running, False)


# ===========================================================================
# Het weerbericht
# ===========================================================================
# Komt van Home Assistant over MQTT, uit een template in andermans configuratie.
# Ruim zijn in wat je accepteert is hier geen slordigheid maar de enige manier
# om niet elke keer dat iemand zijn YAML aanpast een lege klok te krijgen.

equal("het afgesproken bericht", service.parse_weer(
    b'{"toestand": "rainy", "nu": 12.4, "max": 15, "min": 8}'),
    {"toestand": "rainy", "nu": 12.4, "max": 15.0, "min": 8.0})
equal("de Engelse namen uit Home Assistant werken ook", service.parse_weer(
    '{"condition": "sunny", "temperature": 21, "templow": 11}'),
    {"toestand": "sunny", "nu": 21.0, "min": 11.0})
equal("een dict mag rechtstreeks", service.parse_weer({"state": "cloudy"}),
      {"toestand": "cloudy"})
equal("null in een veld gooit de rest niet weg", service.parse_weer(
    '{"toestand": "rainy", "nu": null, "max": 15}'),
    {"toestand": "rainy", "max": 15.0})
equal("een temperatuur die geen getal is valt weg", service.parse_weer(
    '{"toestand": "rainy", "nu": "unavailable"}'), {"toestand": "rainy"})
equal("geen JSON is geen weerbericht", service.parse_weer(b"unknown"), {})
equal("en leeg ook niet", service.parse_weer(b""), {})
equal("een lijst is geen weerbericht", service.parse_weer("[1, 2]"), {})

# Een kapot bericht mag het vorige niet wissen: dan staat de klok zonder weer
# omdat een sensor even niet beschikbaar was.
svc = fresh_service()
service._on_weer("home/badges/weer", b'{"toestand": "sunny", "nu": 20}')
equal("het weer is binnengekomen", service.weer.get("toestand"), "sunny")
service._on_weer("home/badges/weer", b"unavailable")
equal("en een kapot bericht laat het staan", service.weer.get("toestand"),
      "sunny")

check("de service is geabonneerd op het weertopic",
      service.WEER_TOPIC in service._subscribers)
equal("op het gedeelde topic, niet op dat van deze badge",
      service.topic(service.WEER_TOPIC), "home/badges/weer")
check("en de broker heeft dat abonnement gezien",
      "home/badges/weer" in BROKER.subscriptions)


# ===========================================================================
# Datum, en wanneer het nacht is
# ===========================================================================

def epoch_op(jaar, maand, dag, uur, minuut=0):
    """Een tijdstip in lokale tijd, in de telling die de badge gebruikt.

    De badge telt vanaf 2000 en de stub rekent altijd met de zomertijdoffset van
    twee uur, wat voor augustus klopt."""
    import calendar
    unix = calendar.timegm((jaar, maand, dag, uur, minuut, 0, 0, 1, 0)) - 7200
    return unix - 946684800


equal("de klok in lokale tijd", service.clock_text(epoch_op(2026, 8, 17, 7, 16)),
      "07:16")
equal("de datum kort en klein", service.date_text(epoch_op(2026, 8, 17, 7, 16)),
      "ma 17 aug")
equal("en de dag klopt de volgende dag ook",
      service.date_text(epoch_op(2026, 8, 18, 23, 59)), "di 18 aug")
equal("zonder tijd geen datum", service.date_text(0), "")

# nu_epoch moet dezelfde telling gebruiken als local_parts. Op de badge zijn dat
# er twee: MicroPython telt vanaf 2000 en mpos.time.epoch_seconds() geeft
# Unix-seconden. Het verschil is 10957 hele dagen, dus het uur klopt en de datum
# niet. De badge zei donderdag 17 augustus terwijl het dinsdag de 18e was.
Clock.now = epoch_op(2026, 8, 18, 14, 5)
equal("nu_epoch telt zoals de rest", service.nu_epoch(), int(Clock.now))
equal("dus de klok klopt", service.clock_text(service.nu_epoch()), "14:05")
equal("en de datum ook", service.date_text(service.nu_epoch()), "di 18 aug")
Clock.now = 1_000_000.0
equal("een klok die nooit gezet is geeft niets",
      service.date_text(epoch_op(2001, 1, 1, 12)), "")

# Het venster loopt over middernacht. Dat is de normale vorm en niet het
# randgeval: 23 tot 7 moet 01:00 nacht noemen.
check("23:30 valt in de nacht",
      service.is_night(epoch_op(2026, 8, 17, 23, 30), 23, 7))
check("01:00 ook", service.is_night(epoch_op(2026, 8, 18, 1), 23, 7))
check("06:59 nog net", service.is_night(epoch_op(2026, 8, 18, 6, 59), 23, 7))
check("07:00 niet meer",
      not service.is_night(epoch_op(2026, 8, 18, 7), 23, 7))
check("en de namiddag zeker niet",
      not service.is_night(epoch_op(2026, 8, 18, 15), 23, 7))
check("een venster binnen één dag werkt gewoon",
      service.is_night(epoch_op(2026, 8, 18, 14), 13, 16))
check("van gelijk aan tot betekent: geen nacht",
      not service.is_night(epoch_op(2026, 8, 18, 3), 7, 7))
check("zonder klok is het geen nacht", not service.is_night(0, 23, 7))

# De trap waarlangs X en B lopen, en waar de twee instelschermen dezelfde
# waarden uit halen. Niet omslaan: van uit naar honderd met een misgetikte plus
# is precies wat je in een donkere kamer niet wil.
equal("een stap omhoog", service.stap((1, 2, 5, 10), 2, 1), 5)
equal("en omlaag", service.stap((1, 2, 5, 10), 5, -1), 2)
equal("onderaan blijft het onderaan", service.stap((1, 2, 5, 10), 1, -1), 1)
equal("en bovenaan bovenaan", service.stap((1, 2, 5, 10), 10, 1), 10)
equal("een waarde buiten de reeks vindt eerst zijn plaats",
      service.stap((1, 2, 5, 10), 4, 0), 5)
equal("en stapt dan vanaf daar", service.stap((1, 2, 5, 10), 4, 1), 10)
equal("iets dat geen getal is begint vooraan",
      service.stap((1, 2, 5, 10), None, 1), 2)

# X maakt de klok feller en B donkerder, en welke van de twee waarden je
# bijstelt hangt af van waar je bent. Zo dim je hem vanuit bed en staat hij
# morgenavond meteen goed.
svc = fresh_service()
service.nu_epoch = lambda: epoch_op(2026, 8, 18, 2)
service.NIGHT_FROM = 23
service.NIGHT_TO = 7
service.CLOCK_NIGHT = 5
service.CLOCK_DAY = 30
equal("'s nachts stelt B de nachtwaarde bij",
      service.klok_niveau_stap(-1), 3)
equal("de dagwaarde blijft", service.CLOCK_DAY, 30)
equal("en het is bewaard",
      mpos.config.SharedPreferences(service.PREFS_APP_ID).get_int(
          "clock_night", 0), 3)

# Een toets reset de inactiviteitsteller net zo goed als een vinger. Zonder dat
# die daling hier verbruikt wordt, zou de badge klaarwakker worden op de druk
# waarmee je hem juist wilde dimmen.
service.screen_state = service.SCHERM_KLOK
service._vorige_stil = 600_000
service.klok_niveau_stap(-1)
mpos.ui.main_display.inactive_ms = 0
service.SCREEN_OFF_S = 30
service.IDLE_MODE = "klok"
service.screen_tick()
equal("dimmen met B wekt de badge niet", service.screen_state,
      service.SCHERM_KLOK)

svc = fresh_service()
service.nu_epoch = lambda: epoch_op(2026, 8, 18, 14)
service.NIGHT_FROM = 23
service.NIGHT_TO = 7
service.CLOCK_DAY = 30
equal("overdag stelt X de dagwaarde bij", service.klok_niveau_stap(1), 50)
equal("de nachtwaarde blijft", service.CLOCK_NIGHT, 5)
equal("en ook dat is bewaard",
      mpos.config.SharedPreferences(service.PREFS_APP_ID).get_int(
          "clock_day", 0), 50)

svc = fresh_service()
equal("de klokhelderheid overdag",
      service.klok_helderheid(False), service.CLOCK_DAY)
equal("en 's nachts", service.klok_helderheid(True), service.CLOCK_NIGHT)
service.CLOCK_NIGHT = 0
equal("nul zou uit zijn, en dat is geen klok",
      service.klok_helderheid(True), 1)
service.CLOCK_NIGHT = 5


# ===========================================================================
# Het klokscherm
# ===========================================================================
# De klok is een overlay boven de app die draait, dus terugkeren is niets meer
# dan hem weghalen. Hier wordt niet getekend; wat geteld wordt is welke toestand
# de service kiest en op welke helderheid het scherm daarbij komt.

class Overlay:
    """Wat bgclock op het toestel doet, geteld in plaats van getekend."""

    def __init__(self):
        self.op = False
        self.updates = []
        self.gebouwd = 0

    def toon(self):
        if not self.op:
            self.gebouwd += 1
        self.op = True
        return True

    def weg(self):
        was = self.op
        self.op = False
        return was

    def zichtbaar(self):
        return self.op

    def werk_bij(self, tijd, datum, batterij, weer, naam=""):
        self.updates.append((tijd, datum, batterij, dict(weer or {}), naam))
        return True


NACHT = epoch_op(2026, 8, 18, 2)
DAG = epoch_op(2026, 8, 18, 14)


def scherm_opzet(uur_epoch, mode="klok", timeout=30):
    """Een verse service met een namaakklok en een tijdstip dat wij kiezen."""
    svc = fresh_service()
    service.SCREEN_OFF_S = timeout
    service.IDLE_MODE = mode
    service.NIGHT_FROM = 23
    service.NIGHT_TO = 7
    service.CLOCK_DAY = 30
    service.CLOCK_NIGHT = 5
    service.nu_epoch = lambda: uur_epoch
    overlay = Overlay()
    service._overlay = overlay
    mpos.io_expander.lcd_brightness = 100
    service.screen_tick()
    return svc, overlay


def stil(ms):
    mpos.ui.main_display.inactive_ms = ms
    service.screen_tick()


svc, overlay = scherm_opzet(DAG)
stil(29_000)
equal("net voor de tijd blijft de app staan", service.screen_state,
      service.SCHERM_NORMAAL)
stil(31_000)
equal("daarna komt de klok", service.screen_state, service.SCHERM_KLOK)
check("en hij is opgebouwd", overlay.op)
equal("op de daghelderheid", mpos.io_expander.lcd_brightness, 30)
equal("het scherm staat niet uit", service.screen_off, False)
check("en er staat iets op", overlay.updates and overlay.updates[-1][0])

stil(10 * 60 * 1000)
equal("overdag blijft de klok staan, hoe lang je ook wacht",
      service.screen_state, service.SCHERM_KLOK)

mpos.ui.main_display.inactive_ms = 0        # een vinger
service.screen_tick()
equal("een aanraking brengt de app terug", service.screen_state,
      service.SCHERM_NORMAAL)
check("en de klok is weg", not overlay.op)
equal("op de helderheid van ervoor", mpos.io_expander.lcd_brightness, 100)

# 's Nachts eerst de gedimde klok, daarna alsnog donker. De tweede stap gebruikt
# dezelfde wachttijd; een vijfde rij op het instelscherm zou niet passen.
svc, overlay = scherm_opzet(NACHT)
stil(31_000)
equal("'s nachts komt dezelfde klok", service.screen_state,
      service.SCHERM_KLOK)
equal("maar veel donkerder", mpos.io_expander.lcd_brightness, 5)
stil(59_000)
equal("na één keer wachten staat hij er nog", service.screen_state,
      service.SCHERM_KLOK)
stil(61_000)
equal("na twee keer gaat hij uit", service.screen_state, service.SCHERM_UIT)
equal("en dat is helderheid nul", mpos.io_expander.lcd_brightness, 0)
equal("screen_off zegt hetzelfde", service.screen_off, True)
check("de klok is opgeruimd", not overlay.op)

# Met de klok uitgeschakeld gedraagt de badge zich als voorheen.
svc, overlay = scherm_opzet(DAG, mode="uit")
stil(31_000)
equal("zonder klok gaat het scherm gewoon uit", service.screen_state,
      service.SCHERM_UIT)
check("en er is nooit een klok gebouwd", overlay.gebouwd == 0)


# ===========================================================================
# De S-knop in het donker
# ===========================================================================
# Even kijken hoe laat het is zonder de kamer te verlichten: eerst de klok, bij
# de tweede druk terug naar waar je was, en anders vanzelf weer donker.

BTN = mpos.board.fri3d_2026.btn_start


def druk():
    """Indrukken en loslaten, zoals een duim dat doet.

    Ook na het loslaten een tik, want de lus draait door en de flank wordt pas
    herkend als de knop eerst weer omhoog gezien is. Zonder die tweede tik zou
    een tweede druk in deze test onzichtbaar blijven."""
    BTN.press()
    service.screen_tick()
    BTN.release()
    service.screen_tick()


svc, overlay = scherm_opzet(NACHT)
stil(10 * 60 * 1000)
equal("het scherm is uit", service.screen_state, service.SCHERM_UIT)

druk()
equal("een druk op S toont de klok", service.screen_state, service.SCHERM_KIJK)
equal("op de nachthelderheid", mpos.io_expander.lcd_brightness, 5)
check("en de klok staat er", overlay.op)

# De druk reset de inactiviteitsteller net zo goed als een vinger. Zonder dat de
# knopafhandeling die daling verbruikt, zou de badge nu klaarwakker zijn.
mpos.ui.main_display.inactive_ms = 0
service.screen_tick()
equal("de reset van de knop wekt de badge niet", service.screen_state,
      service.SCHERM_KIJK)

# Een paar seconden later telt een aanraking wel weer. De klok laat een tik door
# naar de app eronder, dus dan hoort die app ook zichtbaar te worden.
Clock.advance(3)
mpos.ui.main_display.inactive_ms = 5_000      # de teller loopt weer op
service.screen_tick()
mpos.ui.main_display.inactive_ms = 0          # en dan een vinger
service.screen_tick()
equal("later wekt een aanraking hem wel", service.screen_state,
      service.SCHERM_NORMAAL)

# Terug het donker in, en dan uitkijken tot de klok vanzelf weggaat.
mpos.ui.main_display.inactive_ms = 10 * 60 * 1000
service.screen_tick()
druk()
equal("weer even kijken", service.screen_state, service.SCHERM_KIJK)
Clock.advance(service.KIJK_S + 1)
mpos.ui.main_display.inactive_ms = 500
service.screen_tick()
equal("na tien seconden gaat hij vanzelf terug uit", service.screen_state,
      service.SCHERM_UIT)

# En de tweede druk brengt je wel naar de app terug.
mpos.ui.main_display.inactive_ms = 10 * 60 * 1000
service.screen_tick()
druk()
equal("weer de klok", service.screen_state, service.SCHERM_KIJK)
triggers = mpos.ui.main_display.activity_triggers
druk()
equal("en nog een druk brengt de app terug", service.screen_state,
      service.SCHERM_NORMAAL)
check("met de inactiviteitsteller op nul, anders valt hij meteen weer weg",
      mpos.ui.main_display.activity_triggers > triggers)
check("de klok is weg", not overlay.op)
equal("en het scherm staat weer vol", mpos.io_expander.lcd_brightness, 100)

# Met het scherm aan hoort S van de badge te zijn en niet van deze service:
# Pomodoro gebruikt dezelfde knop om te starten.
svc, overlay = scherm_opzet(NACHT)
stil(1_000)
equal("de app staat op het scherm", service.screen_state,
      service.SCHERM_NORMAAL)
druk()
equal("een druk op S verandert daar niets aan", service.screen_state,
      service.SCHERM_NORMAAL)
check("en er is geen klok gebouwd", overlay.gebouwd == 0)

# De joystick regelt de helderheid, en X en B met opzet niet. Die twee doen al
# iets in het OS zelf: de driver van het bord roept bij elke druk eerst zijn
# eigen navigatiehaak aan, X is ESC (een scherm terug) en B is NEXT. Ze kapen zou
# betekenen dat de app onder de klok achteruit navigeert terwijl je denkt dat je
# dimt, en dat is niet vanaf hier uit te zetten.
svc, overlay = scherm_opzet(NACHT)
stil(31_000)
equal("de klok staat", service.screen_state, service.SCHERM_KLOK)
equal("op de nachtwaarde", service.CLOCK_NIGHT, 5)

JOY = mpos.io_expander


def beweeg(index):
    """De joystick even in een richting en weer los."""
    d = list(JOY.digital)
    d[index] = True
    JOY.digital = tuple(d)
    service.screen_tick()
    d[index] = False
    JOY.digital = tuple(d)
    service.screen_tick()


beweeg(service.JOY_OMLAAG)
equal("omlaag dimt de klok", service.CLOCK_NIGHT, 3)
equal("en de klok blijft staan", service.screen_state, service.SCHERM_KLOK)
equal("en het scherm volgt meteen", mpos.io_expander.lcd_brightness, 3)
equal("de klok blijft staan", service.screen_state, service.SCHERM_KLOK)
beweeg(service.JOY_OMHOOG)
beweeg(service.JOY_OMHOOG)
equal("omhoog maakt hem weer feller", service.CLOCK_NIGHT, 10)

# Vasthouden is één stap. De expander blijft True melden zolang de joystick
# staat, en dat mag niet als tien stappen tellen.
d = list(JOY.digital)
d[service.JOY_OMHOOG] = True
JOY.digital = tuple(d)
service.screen_tick()
service.screen_tick()
service.screen_tick()
equal("vasthouden is één stap", service.CLOCK_NIGHT, 20)
d[service.JOY_OMHOOG] = False
JOY.digital = tuple(d)
service.screen_tick()

# Links en rechts doen hier niets, maar ze resetten de inactiviteitsteller wel:
# het OS leest die knoppen ook. Zonder dat te verbruiken ging de klok weg zodra
# je de joystick aanraakte, wat precies het tegenovergestelde is van wat je
# bedoelde. Hetzelfde geldt voor de andere knoppen op de expander.
for index in (1, 2, 5, 6, 7, 8, 9):
    voor = (service.screen_state, service.CLOCK_NIGHT)
    d = list(JOY.digital)
    d[index] = True
    JOY.digital = tuple(d)
    mpos.ui.main_display.inactive_ms = 0        # de knop reset de teller
    service.screen_tick()
    d[index] = False
    JOY.digital = tuple(d)
    mpos.ui.main_display.inactive_ms = 50
    service.screen_tick()
    equal("knop %d laat de klok staan" % index,
          (service.screen_state, service.CLOCK_NIGHT), voor)

# Een vinger op het scherm wekt hem wel: dat is geen knop.
mpos.ui.main_display.inactive_ms = 5_000
service.screen_tick()
mpos.ui.main_display.inactive_ms = 0
service.screen_tick()
equal("een aanraking wekt de badge wel", service.screen_state,
      service.SCHERM_NORMAAL)

# Met de app op het scherm is de joystick van die app.
svc, overlay = scherm_opzet(NACHT)
stil(1_000)
equal("de app staat op het scherm", service.screen_state,
      service.SCHERM_NORMAAL)
voor = service.CLOCK_NIGHT
beweeg(service.JOY_OMLAAG)
equal("de joystick blijft dan van de app", service.CLOCK_NIGHT, voor)

# Een badge zonder S-knop mag hier niet op vallen.
service._knop = False
equal("geen knop is geen fout", service.knop_flank(), False)
service._knop = None


# ===========================================================================
# Wat de klok te zien krijgt
# ===========================================================================

svc, overlay = scherm_opzet(DAG)
service.battery_pct = 84
service.weer = {"toestand": "rainy", "nu": 12.4, "max": 15.0, "min": 8.0}
stil(31_000)
tijd, datum, batterij, weer, naam = overlay.updates[-1]
equal("de tijd", tijd, "14:00")
equal("de datum", datum, "di 18 aug")
equal("de batterij", batterij, 84)
equal("en het weer", weer.get("toestand"), "rainy")
# Wie drie badges in huis heeft wil 's nachts weten naar welke hij kijkt.
equal("en de naam van de badge, met een hoofdletter", naam, "Alice")


# ===========================================================================
# De helderheid van de app blijft van de app
# ===========================================================================
# Een badge die 's nachts op 5 stond hoort niet de volgende ochtend op 5 wakker
# te worden. Alleen het verlaten van de app-toestand onthoudt een helderheid.

svc, overlay = scherm_opzet(NACHT)
mpos.io_expander.lcd_brightness = 40      # iemand zette de app lager
stil(31_000)
equal("de klok gebruikt zijn eigen waarde", mpos.io_expander.lcd_brightness, 5)
stil(2 * 60 * 1000)
equal("en daarna uit", mpos.io_expander.lcd_brightness, 0)
mpos.ui.main_display.inactive_ms = 0
service.screen_tick()
equal("terug op de helderheid van de app, niet die van de klok",
      mpos.io_expander.lcd_brightness, 40)

# wake() is wat een app aanroept die iets te melden heeft terwijl het scherm net
# uit ging. Een bericht op een donkere badge is geen bericht.
stil(10 * 60 * 1000)
equal("scherm uit", service.screen_off, True)
service.wake()
equal("wake haalt de badge uit het donker", service.screen_state,
      service.SCHERM_NORMAAL)
equal("en het scherm staat aan", service.screen_off, False)

# Zonder timeout gebeurt er niets, hoe lang je ook wacht.
service.SCREEN_OFF_S = 0
stil(10 * 60 * 1000)
equal("nul betekent nooit uit", service.screen_state, service.SCHERM_NORMAAL)
equal("en de helderheid blijft", mpos.io_expander.lcd_brightness, 40)

# Zonder werkende klok is donker beter dan een verlicht leeg scherm.
svc, overlay = scherm_opzet(NACHT)
service._overlay = None


class KapotteKlok:
    def toon(self):
        raise RuntimeError("geen geheugen")


service._overlay = KapotteKlok()
stil(31_000)
equal("een klok die niet opkomt wordt donker en geen wit vlak",
      service.screen_state, service.SCHERM_UIT)
equal("met de verlichting uit", mpos.io_expander.lcd_brightness, 0)
service._overlay = None


# ===========================================================================
# Het debug-lampje
# ===========================================================================
# Het kleine lampje op de expander staat af fabriek op 50 en brandt dus altijd,
# ook 's nachts op een badge die ligt te laden. Van de vier lichtbronnen op deze
# badge is dit de enige die software kan uitzetten: de vijf RGB-LEDs horen bij
# de apps, en C, + en S hangen aan de CHRG- en STDBY-pinnen van de TP4056 en aan
# VUSB. Dat zijn uitgangen van de laadchip, geen GPIO.

svc = fresh_service()
mpos.io_expander.debug_led = 50
equal("op nul zetten lukt", service.apply_debug_led(0), True)
equal("en het lampje is uit", mpos.io_expander.debug_led, 0)
equal("een waarde erboven wordt afgekapt", service.apply_debug_led(500) and
      mpos.io_expander.debug_led, 100)
equal("en eronder ook", service.apply_debug_led(-5) and True, True)
equal("negatief wordt nul", mpos.io_expander.debug_led, 0)

# De voorkeur wordt toegepast bij het laden, niet alleen bewaard. De expander
# houdt zijn eigen instelling bij over een herstart heen, maar een reflash van
# die firmware zet hem terug op 50 en dan sta je weer met een lampje in het
# donker.
mpos.io_expander.debug_led = 50
mpos.config._STORE.clear()
mpos.config.SharedPreferences(service.PREFS_APP_ID).edit() \
    .put_string("badge_name", "alice").put_int("debug_led", 0).commit()
service.load_prefs()
equal("load_prefs past de voorkeur toe", mpos.io_expander.debug_led, 0)

mpos.io_expander.debug_led = 0
mpos.config.SharedPreferences(service.PREFS_APP_ID).edit() \
    .put_int("debug_led", 25).commit()
service.load_prefs()
equal("en een andere waarde ook", mpos.io_expander.debug_led, 25)

# apply_debug_led draait op modulehoogte via load_prefs, dus _expander moet er
# dan al zijn. Dezelfde valkuil als bij migrate_prefs, en dezelfde bewaking.
i_exp = _regel_in_bron("def _expander():")
i_apply = _regel_in_bron("def apply_debug_led(niveau):")
i_load = _regel_in_bron("def load_prefs():")
check("_expander staat voor apply_debug_led", 0 < i_exp < i_apply)
check("en apply_debug_led voor load_prefs", i_apply < i_load)


# ===========================================================================
# Instellingen overnemen van een oudere naam van deze app
# ===========================================================================
# Deze verbinding heeft twee keer een andere naam gehad: eerst zat hij in
# Berichtjes (be.weyn.dinerbadge), daarna in be.weyn.badge, en nu in
# tech.weyn.badgecontroller. Voorkeuren hangen aan het app-id, dus zonder overnemen valt
# een badge die al maanden hangt terug op het configbestand en moet iemand
# naam, broker, gebruiker en wachtwoord opnieuw intypen op een aanraakscherm.

equal("de nieuwste bron staat vooraan",
      [bron for bron, _ in service.LEGACY_SOURCES],
      ["tech.weyn.badge", "be.weyn.badge", "be.weyn.dinerbadge"])

mpos.config._STORE.clear()
oud = mpos.config.SharedPreferences("be.weyn.dinerbadge").edit()
oud.put_string("child_name", "badkamer")
oud.put_string("mqtt_host", "192.168.68.10")
oud.put_int("mqtt_port", 1884)
oud.put_string("mqtt_user", "badges")
oud.put_string("mqtt_pass", "geheim")
oud.commit()

equal("er valt iets over te nemen", service.migrate_prefs(), True)
nieuw = mpos.config.SharedPreferences(service.PREFS_APP_ID)
equal("de naam is mee", nieuw.get_string("badge_name", ""), "badkamer")
equal("de broker is mee", nieuw.get_string("mqtt_host", ""), "192.168.68.10")
equal("de poort is mee", nieuw.get_int("mqtt_port", 0), 1884)
equal("de gebruiker is mee", nieuw.get_string("mqtt_user", ""), "badges")
equal("het wachtwoord is mee", nieuw.get_string("mqtt_pass", ""), "geheim")

# Een tweede keer mag niets meer doen: wie in de Badge-app iets zet, hoort dat
# niet overschreven te zien door iets ouds.
nieuw.edit().put_string("badge_name", "keuken").commit()
equal("een tweede keer neemt niets meer over", service.migrate_prefs(), False)
equal("en laat staan wat er stond",
      nieuw.get_string("badge_name", ""), "keuken")

mpos.config._STORE.clear()
equal("zonder oude voorkeuren valt er niets over te nemen",
      service.migrate_prefs(), False)

# De hop van be.weyn.badge naar tech.weyn.badgecontroller. Daar heten de sleutels
# hetzelfde, en er staan er twee meer: het scherm en het debug-lampje.
mpos.config._STORE.clear()
vorig = mpos.config.SharedPreferences("be.weyn.badge").edit()
vorig.put_string("badge_name", "badkamer")
vorig.put_string("mqtt_host", "192.168.68.100")
vorig.put_int("mqtt_port", 1883)
vorig.put_int("screen_off_s", 120)
vorig.commit()

equal("de vorige naam telt ook als bron", service.migrate_prefs(), True)
nieuw = mpos.config.SharedPreferences(service.PREFS_APP_ID)
equal("de naam is mee", nieuw.get_string("badge_name", ""), "badkamer")
equal("de broker is mee", nieuw.get_string("mqtt_host", ""), "192.168.68.100")
equal("en de schermtimeout ook", nieuw.get_int("screen_off_s", 0), 120)

# De hop van vanmiddag: tech.weyn.badge bestond een uur, en een badge die in
# dat uur is bijgewerkt mag zijn instellingen niet kwijt zijn.
mpos.config._STORE.clear()
kort = mpos.config.SharedPreferences("tech.weyn.badge").edit()
kort.put_string("badge_name", "badkamer")
kort.put_string("mqtt_pass", "geheim")
kort.commit()
equal("ook de naam van een uur oud telt", service.migrate_prefs(), True)
equal("het wachtwoord is mee",
      mpos.config.SharedPreferences(service.PREFS_APP_ID).get_string(
          "mqtt_pass", ""), "geheim")

# Staan er twee oude bronnen, dan wint de nieuwste. Anders zou een naam van
# jaren geleden een recentere overschrijven.
mpos.config._STORE.clear()
mpos.config.SharedPreferences("be.weyn.dinerbadge").edit().put_string(
    "child_name", "van toen").commit()
mpos.config.SharedPreferences("be.weyn.badge").edit().put_string(
    "badge_name", "van gisteren").commit()
equal("er valt iets over te nemen", service.migrate_prefs(), True)
equal("en dat is de nieuwste van de twee",
      mpos.config.SharedPreferences(service.PREFS_APP_ID).get_string(
          "badge_name", ""), "van gisteren")

# De volgorde die het op hardware fout deed. Het instelscherm importeert deze
# module ook, en kan draaien voor de service ooit gestart is. Verliet je dat
# scherm, dan schreef het de standaard uit het configbestand als naam weg, en
# daarna zag de migratie een ingevulde naam en sloeg zichzelf over. De badge
# heette dan voorgoed iets anders dan hij heette. Vandaar dat de migratie bij
# het importeren gebeurt en niet in onCreate van de service.
BRON = SOURCE.split("\n")
def _regel(tekst):
    for i, r in enumerate(BRON):
        if r.strip() == tekst:
            return i
    return -1
i_migrate = _regel("migrate_prefs()")
i_load = _regel("load_prefs()")
i_klasse = _regel("class BadgeService(Service):")
check("migrate_prefs draait op modulehoogte", i_migrate > 0)
check("en load_prefs erna", i_load == i_migrate + 1)
check("allebei voor de klasse, dus voor een activity iets kan schrijven",
      0 < i_migrate < i_klasse)


# ===========================================================================
# Het klokscherm zelf
# ===========================================================================
# bgclock tekent met LVGL en hangt daarom niet in de service. Wat hier getest
# wordt is dat het gebouwd en weer weggehaald wordt, en dat het niet elke tik
# opnieuw tekent: dat laatste geeft geflikker op een klok die elke seconde
# bijgewerkt wordt.

import lvgl as lv                                     # noqa: E402
import bgclock                                        # noqa: E402

equal("regen is regen", bgclock.icoon_soort("pouring"), "regen")
equal("onweer telt als regen", bgclock.icoon_soort("lightning-rainy"), "regen")
equal("sneeuw ook", bgclock.icoon_soort("snowy"), "regen")
equal("een heldere hemel is zon", bgclock.icoon_soort("sunny"), "zon")
equal("en \'s nachts ook", bgclock.icoon_soort("clear-night"), "zon")
equal("al de rest is bewolkt", bgclock.icoon_soort("partlycloudy"), "bewolkt")
equal("iets onbekends is ook maar bewolkt",
      bgclock.icoon_soort("exceptional"), "bewolkt")
equal("zonder toestand geen pictogram", bgclock.icoon_soort(None), None)

equal("een temperatuur zoals je hem zegt", bgclock.graden(12.4), "12\u00b0")
equal("en afgerond", bgclock.graden(12.6), "13\u00b0")
equal("onder nul ook", bgclock.graden(-3.2), "-3\u00b0")
equal("niets is niets", bgclock.graden(None), "")
equal("en onzin ook", bgclock.graden("unavailable"), "")

# De niet-brandende segmenten staan uit en niet op een schaduw. Pomodoro zet ze
# op 18 zodat het op een echt display lijkt; hier is dat vijfendertig lampjes
# die \'s nachts licht geven voor de sier.
equal("een gedoofd segment geeft geen licht", bgclock.SEGMENT_UIT, 0)

laag = lv.layer_top()
kinderen = len(laag.children)
klok = bgclock.ClockOverlay()
check("een klok die nooit getoond is kost niets", not klok.zichtbaar())
equal("en hangt nergens", len(laag.children), kinderen)

klok.toon()
check("tonen bouwt hem op", klok.zichtbaar())
equal("in de laag boven alles", len(laag.children), kinderen + 1)

check("de eerste keer wordt er getekend",
      klok.werk_bij("07:16", "ma 17 aug", 84,
                    {"toestand": "rainy", "nu": 12.4, "max": 15, "min": 8}))
check("dezelfde inhoud tekent niet opnieuw",
      not klok.werk_bij("07:16", "ma 17 aug", 84,
                        {"toestand": "rainy", "nu": 12.4, "max": 15, "min": 8}))
check("een minuut later wel",
      klok.werk_bij("07:17", "ma 17 aug", 84,
                    {"toestand": "rainy", "nu": 12.4, "max": 15, "min": 8}))
check("en een ander weerbericht ook",
      klok.werk_bij("07:17", "ma 17 aug", 84, {"toestand": "sunny"}))
check("zonder weerbericht valt er niets om over te struikelen",
      klok.werk_bij("07:18", "ma 17 aug", 84, {}))
check("zonder batterij evenmin",
      klok.werk_bij("07:19", "ma 17 aug", None, None))
check("de naam hoort erbij en verandert het scherm",
      klok.werk_bij("07:19", "ma 17 aug", None, None, "Badkamer"))
check("en dezelfde naam tekent niet opnieuw",
      not klok.werk_bij("07:19", "ma 17 aug", None, None, "Badkamer"))

klok.weg()
check("weghalen laat niets staan", not klok.zichtbaar())
equal("en de laag is weer zoals hij was", len(laag.children), kinderen)
check("bijwerken zonder scherm is geen fout",
      not klok.werk_bij("07:20", "ma 17 aug", 84, {}))
klok.toon()
check("en opnieuw tonen bouwt hem gewoon weer op", klok.zichtbaar())
klok.weg()

# ===========================================================================

print("\n%d checks, %d mislukt" % (CHECKS["n"], len(FAILURES)))
for f in FAILURES:
    print("  -", f)
sys.exit(1 if FAILURES else 0)
