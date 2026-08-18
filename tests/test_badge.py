"""Offline tests voor de Badge-app (be.weyn.badge).

Draait op gewone Python tegen de stubs in tests/stubs/, zodat de MQTT-brug, de
telemetrie en de schermdimmer na te kijken zijn zonder badge en zonder broker.

    python3 tests/test_badge.py

Het grootste deel van wat hier staat komt uit test_dinerbadge.py. Die code is
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
APP_DIR = os.path.join(ROOT, "be.weyn.badge")
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
_config.TIMEZONE = "CET-1CEST,M3.5.0,M10.5.0/3"
sys.modules["badge_config"] = _config

import network                                        # noqa: E402
from umqtt.simple import BROKER                       # noqa: E402
import mpos                                           # noqa: E402
import mpos.ui                                        # noqa: E402
import mpos.config                                    # noqa: E402

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
    service.SCREEN_OFF_S = 0
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


def configs():
    """De discoveryberichten, op topic."""
    return dict((topic, payload) for topic, payload in BROKER.published
                if topic.startswith("homeassistant/"))


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
      BROKER.subscriptions, ["home/badges/alice/msg"])

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
      len(service._subscribers), 1)
equal("en het levert geen tweede subscribe op", BROKER.subscriptions,
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
equal("na hernoemen luistert hij op de nieuwe naam", BROKER.subscriptions,
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
# Het scherm
# ===========================================================================

svc = fresh_service()
service.SCREEN_OFF_S = 0
mpos.ui.main_display.inactive_ms = 10 * 60 * 1000
service.screen_tick()
equal("nul betekent nooit uit", service.screen_off, False)
equal("en de helderheid blijft", mpos.io_expander.lcd_brightness, 100)

service.SCREEN_OFF_S = 30
mpos.io_expander.lcd_brightness = 40      # iemand zette hem lager
mpos.ui.main_display.inactive_ms = 29_000
service.screen_tick()
equal("net voor de tijd blijft het scherm aan", service.screen_off, False)

mpos.ui.main_display.inactive_ms = 31_000
service.screen_tick()
equal("na de tijd gaat het uit", service.screen_off, True)
equal("uit is helderheid nul", mpos.io_expander.lcd_brightness, 0)

mpos.ui.main_display.inactive_ms = 0      # een vinger
service.screen_tick()
equal("een aanraking wekt het", service.screen_off, False)
# Een badge die op 40 stond hoort niet op 100 wakker te worden.
equal("en het komt terug op de helderheid van ervoor",
      mpos.io_expander.lcd_brightness, 40)

# wake() is wat een app aanroept die iets te melden heeft terwijl het scherm net
# uit ging. Een bericht op een donkere badge is geen bericht.
mpos.ui.main_display.inactive_ms = 60_000
service.screen_tick()
equal("scherm uit", service.screen_off, True)
triggers = mpos.ui.main_display.activity_triggers
service.wake()
equal("wake zet het scherm aan", service.screen_off, False)
check("en reset de inactiviteitsteller",
      mpos.ui.main_display.activity_triggers > triggers)

# Uitzetten van de timeout terwijl het scherm net uit is, moet het aandoen.
service.SCREEN_OFF_S = 30
mpos.ui.main_display.inactive_ms = 60_000
service.screen_tick()
equal("scherm uit", service.screen_off, True)
service.SCREEN_OFF_S = 0
service.screen_tick()
equal("timeout op nooit doet het scherm weer aan", service.screen_off, False)


# ===========================================================================
# Instellingen overnemen van Berichtjes
# ===========================================================================
# Deze badge is ooit op het toestel zelf ingesteld toen Berichtjes de verbinding
# nog bezat. Zonder overnemen valt hij na een update terug op het configbestand
# en moet iemand naam, broker, gebruiker en wachtwoord opnieuw intypen op een
# aanraakscherm.

mpos.config._STORE.clear()
oud = mpos.config.SharedPreferences(service.LEGACY_PREFS_APP_ID).edit()
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

print("\n%d checks, %d mislukt" % (CHECKS["n"], len(FAILURES)))
for f in FAILURES:
    print("  -", f)
sys.exit(1 if FAILURES else 0)
