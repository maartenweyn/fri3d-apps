"""Offline tests for the Berichtjes app (be.weyn.dinerbadge).

Runs on desktop Python against the stubs in tests/stubs/, so the MQTT
handling and the screen logic can be checked without a badge or a broker.

    python3 tests/test_dinerbadge.py

The stubs mirror the firmware's quirks on purpose: MQTT payloads arrive as
bytes, a dropped link raises OSError from any client call, and
remove_event_cb matches callbacks by identity.
"""

import os
import sys
import types

sys.dont_write_bytecode = True   # never drop __pycache__ into the app folder

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.join(ROOT, "be.weyn.dinerbadge"))

# dinerbadge_config.py is gitignored (it holds the MQTT password), so the app
# folder may not have one. Inject a known config instead of depending on
# whatever the machine happens to hold.
_config = types.ModuleType("dinerbadge_config")
_config.CHILD_NAME = "alice"
_config.MQTT_BROKER = "broker.example"
_config.MQTT_PORT = 1883
_config.MQTT_USER = "example-user"
_config.MQTT_PASS = "example-secret"
_config.LED_ALERT = True
_config.ACK_TIMEOUT_MIN = 30
_config.TIMEZONE = "CET-1CEST,M3.5.0,M10.5.0/3"
sys.modules["dinerbadge_config"] = _config

import lvgl as lv                                    # noqa: E402
import network                                       # noqa: E402
from umqtt.simple import BROKER                       # noqa: E402
import mpos                                          # noqa: E402
import mpos.ui                                       # noqa: E402
import mpos.time                                     # noqa: E402
from mpos.lights import LightsManager                 # noqa: E402

import dinerbadge_service as service                  # noqa: E402
from dinerbadge_service import DinerBadgeService       # noqa: E402
from dinerbadge import DinerBadge                      # noqa: E402
from dbsettings import DinerBadgeSettings              # noqa: E402
from dbconnection import DinerBadgeConnection          # noqa: E402
import mpos.config                                    # noqa: E402

FAILURES = []
CHECKS = {"n": 0}


def check(label, condition):
    CHECKS["n"] += 1
    if not condition:
        FAILURES.append(label)
        print("FAIL:", label)


def equal(label, got, want):
    check("%s (got %r, want %r)" % (label, got, want), got == want)


# --- a clock we control ----------------------------------------------------
# The service schedules retries off time.time(). Tests must be able to step
# that forward without sleeping.

class Clock:
    now = 1_000_000.0

    @classmethod
    def time(cls):
        return cls.now

    @classmethod
    def advance(cls, seconds):
        cls.now += seconds


_real_time = service.time
_fake_time = types.ModuleType("time")
_fake_time.time = Clock.time
service.time = _fake_time


def fresh_service():
    """A service on a working broker, connected and subscribed."""
    BROKER.reset()
    LightsManager.reset()
    mpos.config._STORE.clear()          # the settings screen writes here
    mpos.NotificationManager.reset()
    mpos.AppManager.reset()
    mpos.TaskManager.reset()
    network.STATE["active"] = True
    network.STATE["connected"] = True
    Clock.now = 1_000_000.0

    service.last_message = None
    service.last_message_seq = 0
    service.last_message_time = None
    service.acked_seq = 0
    service.connected = False
    service.last_error = None
    # _leds_write skips a write when the strip already shows what is asked, so
    # a stale flag here would make the LED assertions pass for the wrong
    # reason.
    service.leds_lit = False
    service.pending_ack = None
    service.LED_ALERT = True
    service.ACK_TIMEOUT_MIN = 30
    service.MQTT_BROKER = _config.MQTT_BROKER
    service.MQTT_PORT = _config.MQTT_PORT
    service.MQTT_USER = _config.MQTT_USER
    service.MQTT_PASS = _config.MQTT_PASS
    service.set_child_name("alice")

    svc = DinerBadgeService()
    svc.onCreate()
    svc.onStart(None)
    svc._pump()          # first pump connects
    return svc


# ===========================================================================
# Service: topics and configuration
# ===========================================================================

equal("topic for incoming messages", service.TOPIC_MSG, "home/badges/alice/msg")
equal("topic for acknowledgements", service.TOPIC_ACK, "home/badges/alice/ack")
equal("client id is per badge and per device", service.CLIENT_ID,
      "badge_alice_" + service.DEVICE_SUFFIX)
check("config file was picked up", service.CONFIG_OK)
equal("credentials come from the config", service.MQTT_USER, "example-user")

svc = fresh_service()
equal("connected after the first pump", service.connected, True)
equal("subscribed exactly once", BROKER.subscriptions, ["home/badges/alice/msg"])
check("credentials were handed to the client",
      svc._mqtt.user == "example-user"
      and svc._mqtt.password == "example-secret")

# The service must not create LVGL objects: a Service has no screen. Assert on
# the source rather than trusting a comment to stay true.
APP_DIR = os.path.join(ROOT, "be.weyn.dinerbadge")
with open(os.path.join(APP_DIR, "dinerbadge_service.py")) as fh:
    SOURCE = fh.read()
check("service builds no widgets",
      "lv.obj(" not in SOURCE and "lv.label(" not in SOURCE)

# CPython has these; MicroPython 1.27 on this badge does not. Measured with
# dir(str) on the device, 2026-08-17. Desktop tests cannot catch a call to one
# of them, because desktop Python answers happily and the badge raises
# AttributeError at runtime. str.capitalize() cost us exactly that.
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
        check("%s does not call str.%s(), absent on this firmware"
              % (name, method), ".%s(" % method not in text)

check("titlecase replaces str.capitalize", service.titlecase("alice") == "Alice")
check("titlecase survives an empty name", service.titlecase("") == "")


# ===========================================================================
# Service: receiving
# ===========================================================================

svc = fresh_service()
BROKER.deliver(service.TOPIC_MSG, "Eten over 10 minuten")
svc._pump()

equal("first message stored", service.last_message, "Eten over 10 minuten")
equal("sequence starts at one", service.last_message_seq, 1)
check("message time recorded", service.last_message_time is not None)
equal("one notification posted", len(mpos.NotificationManager.posted), 1)
equal("app pulled to the foreground", mpos.AppManager.started,
      ["be.weyn.dinerbadge"])
equal("all five LEDs lit on arrival", LightsManager.lit(), 5)
check("there is an unacknowledged message", service.has_unacked())

posted = mpos.NotificationManager.posted[0]
equal("notification carries the text", posted.text, "Eten over 10 minuten")
equal("notification is high priority", posted.priority,
      mpos.Notification.PRIORITY_HIGH)
equal("notification owned by the app", posted.app_fullname, "be.weyn.dinerbadge")
check("notification icon is a non-empty string",
      isinstance(posted.icon, str) and posted.icon)
equal("tapping it opens this app", posted.intent.app_fullname,
      "be.weyn.dinerbadge")

# The obvious way to write this app is to compare the incoming text with the
# last one to avoid duplicates. That silently swallows the second "Eten over
# 10 minuten" of the evening, which is exactly the message that matters.
BROKER.deliver(service.TOPIC_MSG, "Eten over 10 minuten")
svc._pump()
equal("the same text twice is two messages", service.last_message_seq, 2)
equal("and alerts twice", len(mpos.AppManager.started), 2)

svc = fresh_service()
BROKER.deliver(service.TOPIC_MSG, "   ")
svc._pump()
equal("blank payload ignored", service.last_message_seq, 0)
equal("no notification for a blank payload",
      len(mpos.NotificationManager.posted), 0)

svc = fresh_service()
BROKER.deliver(service.TOPIC_MSG, b"\xff\xfe kapot")
svc._pump()
check("undecodable payload does not crash the service",
      service.last_message_seq == 1)

svc = fresh_service()
BROKER.deliver(service.TOPIC_MSG, " Kom eens naar beneden\n")
svc._pump()
equal("payload is trimmed", service.last_message, "Kom eens naar beneden")


# ===========================================================================
# Service: acknowledging
# ===========================================================================

svc = fresh_service()
BROKER.deliver(service.TOPIC_MSG, "Je bent de vaat vergeten")
svc._pump()
sent = service.publish_ack()

equal("ack was published", sent, True)
equal("ack went to the ack topic", BROKER.published,
      [("home/badges/alice/ack", "Je bent de vaat vergeten")])
equal("sequence marked acknowledged", service.acked_seq, 1)
check("nothing outstanding", not service.has_unacked())
equal("LEDs cleared on acknowledgement", LightsManager.lit(), 0)

service.publish_ack()
equal("acknowledging twice does not publish twice", len(BROKER.published), 1)

svc = fresh_service()
BROKER.deliver(service.TOPIC_MSG, "Kom eens")
svc._pump()
BROKER.up = False
sent = service.publish_ack()
equal("ack reports failure when the broker is gone", sent, False)
equal("but the badge still counts it as read", service.acked_seq, 1)
equal("and the connection is dropped", service.connected, False)

# A bedroom at the edge of the WiFi is exactly where a child presses the button
# and the publish fails. Losing it means Home Assistant shows red for half an
# hour for a message that was read.
equal("the ack is held, not lost", service.pending_ack, "Kom eens")
BROKER.up = True
for _ in range(70):
    Clock.advance(1)
    svc._pump()
    if service.connected:
        break
equal("reconnected", service.connected, True)
equal("and the held ack went out", BROKER.published,
      [("home/badges/alice/ack", "Kom eens")])
check("nothing left pending", service.pending_ack is None)

# It must not be sent twice.
BROKER.published[:] = []
Clock.advance(1)
svc._pump()
equal("and not again on the next tick", BROKER.published, [])


# ===========================================================================
# Service: staying connected
# ===========================================================================

BROKER.reset()
LightsManager.reset()
network.STATE["connected"] = False
Clock.now = 2_000_000.0
svc = DinerBadgeService()
svc.onCreate()
svc.onStart(None)
svc._pump()
equal("no connection attempt while WiFi is down", BROKER.connects, 0)
equal("and the app knows it is offline", service.connected, False)

network.STATE["connected"] = True
svc._pump()
equal("connects as soon as WiFi returns", BROKER.connects, 1)

# A child's badge spends real time out of range. Retrying every second there
# is a battery cost for nothing, so failures must back off.
BROKER.reset()
network.STATE["connected"] = True
BROKER.up = False
Clock.now = 3_000_000.0
svc = DinerBadgeService()
svc.onCreate()
svc.onStart(None)
svc._pump()
equal("an attempt was made", BROKER.attempts, 1)
equal("but it did not connect", service.connected, False)
retries = []
for _ in range(30):
    Clock.advance(1)
    before = BROKER.attempts
    svc._pump()
    retries.append(BROKER.attempts != before)
check("does not retry every second", retries.count(True) < 8)
check("but keeps trying", retries.count(True) >= 3)

BROKER.up = True
for _ in range(70):
    Clock.advance(1)
    svc._pump()
    if service.connected:
        break
equal("reconnects once the broker is back", service.connected, True)
equal("backoff reset after success", svc._backoff, service.RETRY_MIN)

# Keepalive: the broker drops a silent client after `keepalive` seconds.
BROKER.reset()
svc = fresh_service()
for _ in range(int(service.PING_EVERY) - 1):
    Clock.advance(1)
    svc._pump()
equal("no ping before it is due", BROKER.pings, 0)
Clock.advance(2)
svc._pump()
equal("ping sent inside the keepalive window", BROKER.pings, 1)
check("ping interval is safely inside keepalive", service.PING_EVERY < 60)

# A link that dies mid-poll must not wedge the loop.
svc = fresh_service()
BROKER.up = False
svc._pump()
equal("lost link marks the app offline", service.connected, False)
check("and schedules a retry", svc._next_try > Clock.now)

# Older umqtt.simple builds have no socket_timeout parameter.
BROKER.reset()
BROKER.supports_socket_timeout = False
network.STATE["connected"] = True
Clock.now = 4_000_000.0
svc = DinerBadgeService()
svc.onCreate()
svc.onStart(None)
svc._pump()
equal("falls back for an older umqtt.simple", service.connected, True)
BROKER.supports_socket_timeout = True

# umqtt.simple is a one-off mip install per badge. A missing module must be a
# clear message, not a crash loop.
BROKER.reset()
network.STATE["connected"] = True
Clock.now = 5_000_000.0
_saved = sys.modules.pop("umqtt.simple")
sys.modules["umqtt.simple"] = None      # import raises ImportError
svc = DinerBadgeService()
svc.onCreate()
svc.onStart(None)
svc._pump()
equal("missing umqtt is reported", service.last_error, "umqtt.simple ontbreekt")
check("and retried slowly", svc._next_try >= Clock.now + service.RETRY_MAX)
sys.modules["umqtt.simple"] = _saved

# The failure people actually hit: the broker is there and says no.
BROKER.reset()
network.STATE["connected"] = True
Clock.now = 6_000_000.0
BROKER.accept_auth = False
svc = DinerBadgeService()
svc.onCreate()
svc.onStart(None)
svc._pump()
equal("a refused login is reported in words", service.last_error,
      "login geweigerd")
equal("and it is not connected", service.connected, False)
BROKER.accept_auth = True

# onDestroy must let go of the socket.
svc = fresh_service()
svc.onDestroy()
equal("service releases the connection on destroy", service.connected, False)
equal("loop stopped", svc._running, False)


# ===========================================================================
# One loop, whatever happens
# ===========================================================================
# Two loops on one service share its MQTT client and its client id, and a
# broker evicts the older of two clients claiming the same id. They then take
# turns kicking each other off, which on the badge looked exactly like a flaky
# network: WiFi solid at -54 dBm, every connect failing with OSError(-1), and
# the loop running at twice its tick rate.

svc = fresh_service()
mpos.TaskManager.reset()
svc.onStart(None)
equal("starting an already running service adds no loop",
      len(mpos.TaskManager.tasks), 0)
svc.onStart(None)
svc.onStart(None)
equal("however often it is asked", len(mpos.TaskManager.tasks), 0)

# A fresh instance has to take over cleanly rather than run alongside.
first = fresh_service()
equal("the first one is the current service", service._service, first)
check("and it is running", first._running)
second = DinerBadgeService()
second.onCreate()
mpos.TaskManager.reset()
equal("a new instance takes over", service._service, second)
check("and the old loop is stopped", not first._running)
check("its socket is released", first._mqtt is None)
second.onStart(None)
equal("the new one runs", len(mpos.TaskManager.tasks), 1)

# The client id is stable per badge, which is what MQTT wants for session
# continuity. That is precisely why two simultaneous connections are fatal.
# Two badges briefly named the same thing is what happens while you set the
# second one up, so the id may not be derived from the name alone.
equal("client id carries the name for readability",
      service.CLIENT_ID, "badge_%s_%s" % (service.CHILD_NAME,
                                          service.DEVICE_SUFFIX))
check("and a device suffix that is not the name",
      service.DEVICE_SUFFIX and service.DEVICE_SUFFIX not in ("alice", "bob"))
service.set_child_name("bob")
check("which survives a rename", service.CLIENT_ID.endswith(service.DEVICE_SUFFIX))
service.set_child_name("alice")


# ===========================================================================
# Which badge this is
# ===========================================================================
# Both badges run an identical copy of the app and the name is picked on the
# badge, so nothing about the name may be baked in at import time.

svc = fresh_service()
equal("name comes from the config on a fresh badge", service.CHILD_NAME, "alice")

# The name is typed on a touchscreen and ends up in an MQTT topic. A capital, a
# trailing space or a slash would point the badge at a topic nobody publishes
# to, and then nothing arrives and nothing complains.
equal("already fine", service.normalize_name("bob"), "bob")
equal("capitals are folded", service.normalize_name("Alice"), "alice")
equal("surrounding space is dropped", service.normalize_name("  bob  "), "bob")
equal("inner spaces become hyphens",
      service.normalize_name("jan pieter"), "jan-pieter")
equal("topic wildcards are dropped, not translated",
      service.normalize_name("a/b+c#d"), "abcd")
equal("accents and punctuation go too", service.normalize_name("Renée!"), "rene")
equal("runs of hyphens collapse", service.normalize_name("a   b"), "a-b")
equal("nothing usable gives nothing", service.normalize_name("###"), "")
equal("neither does empty", service.normalize_name(""), "")
equal("nor None", service.normalize_name(None), "")
check("a long name is cut short", len(service.normalize_name("x" * 90)) == 24)

# set_child_name goes through the same normalisation, so no caller can sneak a
# broken topic past it.
service.set_child_name("  Bob ")
equal("normalised on the way in", service.CHILD_NAME, "bob")

service.set_child_name("bob")
equal("topics follow the name", service.TOPIC_MSG, "home/badges/bob/msg")
equal("so does the ack topic", service.TOPIC_ACK, "home/badges/bob/ack")
equal("and the client id", service.CLIENT_ID,
      "badge_bob_" + service.DEVICE_SUFFIX)

# A client stays subscribed to what it asked for, so renaming has to drop the
# connection. Without this the badge would sit there connected and deaf.
svc = fresh_service()
equal("connected before the rename", service.connected, True)
service.set_child_name("bob")
equal("renaming drops the connection", service.connected, False)
equal("and clears the client", svc._mqtt, None)
svc._pump()
equal("reconnects without waiting out a backoff", service.connected, True)
equal("subscribed to the new topic", BROKER.subscriptions[-1],
      "home/badges/bob/msg")

service.set_child_name("bob")
equal("setting the same name again changes nothing",
      service.set_child_name("bob"), False)
check("an empty name is refused", service.set_child_name("") is False)
check("so is one that normalises to nothing",
      service.set_child_name("///") is False)
equal("and both leave the old one alone", service.CHILD_NAME, "bob")

# The settings screen writes prefs; the service reads them.
svc = fresh_service()
prefs = mpos.SharedPreferences(service.PREFS_APP_ID).edit()
prefs.put_string("child_name", "bob")
prefs.put_int("led_alert", 0)
prefs.put_int("ack_timeout_min", 10)
prefs.commit()
service.load_prefs()
equal("the name from prefs wins over the config", service.CHILD_NAME, "bob")
equal("so does the LED setting", service.LED_ALERT, False)
equal("and the timeout", service.ACK_TIMEOUT_MIN, 10)

# The screen itself: pick a name, leave, and the service is pointed at it.
svc = fresh_service()
lv.DEFAULT_GROUP.objects = []
mpos.STARTED[:] = []
mpos.RESULTS_PENDING[:] = []
settings = DinerBadgeSettings()
settings.onCreate()
equal("opens on the current name", settings.name_button_label.text,
      "Deze badge: Alice")
check("the rows are reachable with the d-pad",
      len(lv.DEFAULT_GROUP.objects) >= 5)
check("one of them opens the broker screen",
      any(getattr(o, "text", None) == "Verbinding..."
          for row in lv.DEFAULT_GROUP.objects for o in row.children))

# A row too many falls off the bottom of a screen that cannot scroll, which is
# how the broker settings ended up on their own screen. Guard the arithmetic so
# the next row cannot quietly become unreachable.
import dbsettings as settings_module                       # noqa: E402
used = (16 + settings.rows * settings_module.ROW_HEIGHT
        + settings.rows * settings_module.ROW_GAP)
check("the settings rows fit in %d pixels, using %d"
      % (settings_module.SCREEN_BUDGET, used),
      used <= settings_module.SCREEN_BUDGET)

# Driving this screen by sending events proved nothing about whether a finger
# can hit it. The name is the one control anyone opens this screen for, so it is
# a full-width button, and the screen does not scroll: on a scrollable container
# LVGL turns a press that drifts a few pixels into a scroll and cancels the
# click, which reads as a dead button.
name_button = lv.DEFAULT_GROUP.objects[0]
equal("the name button is full width", name_button.size, (lv.pct(100), 44))
check("and finger-high", name_button.size[1] >= 44)
for obj in lv.DEFAULT_GROUP.objects[1:]:
    if obj.size:
        check("every other control is at least 30 high, got %r" % (obj.size,),
              obj.size[1] >= 30)

# Tapping the name hands off to the OS input screen, which owns the keyboard.
settings._edit_name()
equal("one input screen was asked for", len(mpos.RESULTS_PENDING), 1)
intent, callback = mpos.RESULTS_PENDING[-1]
equal("it is the OS input activity", intent.activity_class, mpos.InputActivity)
equal("asking for text", intent.extras["setting"]["ui"], "textarea")
equal("prefilled with the current name", intent.extras["value"], "alice")
check("with a note about matching Home Assistant",
      "Home Assistant" in intent.extras["setting"]["note"])

callback({"result_code": True, "data": {"value": "  Bob "}})
equal("a typed name is normalised and shown back",
      settings.name_button_label.text, "Deze badge: Bob")
equal("and held as a topic-safe name", settings.name, "bob")

callback({"result_code": False, "data": {"value": "carol"}})
equal("cancelling changes nothing", settings.name, "bob")
callback({"result_code": True, "data": {"value": "###"}})
equal("an unusable name is refused, keeping the last good one",
      settings.name, "bob")

settings._cycle_timeout(1)
equal("the timeout steps in fives", settings.timeout_label.text, "35 min")
for _ in range(20):
    settings._cycle_timeout(-1)
equal("and never drops below five", settings.timeout_label.text, "5 min")
settings.onPause(settings.screen if hasattr(settings, "screen") else None)
equal("leaving the screen points the badge at the new name",
      service.CHILD_NAME, "bob")
equal("and applies the timeout", service.ACK_TIMEOUT_MIN, 5)
equal("the rename dropped the connection", service.connected, False)
svc._pump()
equal("the rename resubscribed", BROKER.subscriptions[-1],
      "home/badges/bob/msg")


# ===========================================================================
# Which broker, also set on the badge
# ===========================================================================
# Nothing sensitive should have to live in a file, so the address and the
# credentials are editable on the badge and stored in the same prefs.

equal("a port survives being typed", service.normalize_port("1883"), 1883)
equal("with space around it too", service.normalize_port("  8883 "), 8883)
equal("nonsense is refused", service.normalize_port("eighteen"), 0)
equal("so is out of range", service.normalize_port("70000"), 0)
equal("and zero", service.normalize_port("0"), 0)
equal("and empty", service.normalize_port(""), 0)

svc = fresh_service()
prefs = mpos.SharedPreferences(service.PREFS_APP_ID).edit()
prefs.put_string("mqtt_host", "10.1.2.3")
prefs.put_int("mqtt_port", 8883)
prefs.put_string("mqtt_user", "someone")
prefs.put_string("mqtt_pass", "secret")
prefs.commit()
equal("prefs beat the config", service.load_prefs(), True)
equal("host", service.MQTT_BROKER, "10.1.2.3")
equal("port", service.MQTT_PORT, 8883)
equal("user", service.MQTT_USER, "someone")
equal("password", service.MQTT_PASS, "secret")
equal("a broker change drops the connection", service.connected, False)
svc._pump()
equal("and reconnects with the new credentials", service.connected, True)
check("which the client was handed",
      svc._mqtt.server == "10.1.2.3" and svc._mqtt.port == 8883
      and svc._mqtt.user == "someone" and svc._mqtt.password == "secret")

# An empty user means anonymous, and umqtt wants None rather than "".
svc = fresh_service()
prefs = mpos.SharedPreferences(service.PREFS_APP_ID).edit()
prefs.put_string("mqtt_user", "")
prefs.put_string("mqtt_pass", "")
prefs.commit()
service.load_prefs()
check("an empty user becomes None, not an empty string",
      service.MQTT_USER is None and service.MQTT_PASS is None)

# Nothing changed means nothing is dropped: reading prefs must not be a
# reconnect in disguise, or the loop would churn.
svc = fresh_service()
equal("re-reading unchanged prefs changes nothing", service.load_prefs(), False)
equal("and leaves the connection up", service.connected, True)

# The screen.
svc = fresh_service()
lv.DEFAULT_GROUP.objects = []
mpos.RESULTS_PENDING[:] = []
conn = DinerBadgeConnection()
conn.onCreate()
equal("opens on the broker in use", conn.host, _config.MQTT_BROKER)
equal("shows it", conn.labels["host"][0].text, "Broker: " + _config.MQTT_BROKER)
equal("the port", conn.labels["port"][0].text, "Poort: 1883")
equal("the user", conn.labels["user"][0].text, "Gebruiker: example-user")
# The one thing a child must not be able to read off the screen.
equal("never the password itself", conn.labels["pass"][0].text,
      "Wachtwoord: ingesteld")
check("four rows, all finger-sized",
      len(lv.DEFAULT_GROUP.objects) == 4
      and all(o.size[1] >= 30 for o in lv.DEFAULT_GROUP.objects))
check("connection status is on screen", "verbonden" in conn.status.text)

# "geen verbinding: -1" is what the badge said before this, which tells nobody
# which of the four fields to go and look at.
from umqtt.simple import MQTTException                      # noqa: E402
equal("a refused login says so",
      service.describe_error(MQTTException(5)), "login geweigerd")
equal("bad credentials too",
      service.describe_error(MQTTException(4)),
      "gebruiker of wachtwoord fout")
equal("an unknown code still names itself",
      service.describe_error(MQTTException(7)), "broker weigert (code 7)")
equal("a dead socket is not an errno",
      service.describe_error(OSError(-1)), "geen antwoord van de broker")
equal("nothing wrong, nothing said", service.describe_error(None), None)

# The screen has to keep up: someone is standing here waiting to see whether
# the address they just typed works.
service.connected = False
service.last_error = "login geweigerd"
conn._paint_status()
equal("a failure is spelled out", conn.status.text,
      "geen verbinding: login geweigerd")
service.connected = True
conn._on_frame(None, None)
check("and it recovers on the next frame", "verbonden" in conn.status.text)

conn._edit("host")
intent, callback = mpos.RESULTS_PENDING[-1]
equal("editing the host prefills it", intent.extras["value"], _config.MQTT_BROKER)
callback({"result_code": True, "data": {"value": " 10.9.9.9 "}})
equal("typed host is trimmed and shown", conn.labels["host"][0].text,
      "Broker: 10.9.9.9")

conn._edit("port")
intent, callback = mpos.RESULTS_PENDING[-1]
callback({"result_code": True, "data": {"value": "not a port"}})
equal("a nonsense port is refused", conn.port, 1883)
callback({"result_code": True, "data": {"value": "8884"}})
equal("a real one is taken", conn.port, 8884)

# Editing the password starts empty so it is not displayed, and an empty result
# keeps what is stored rather than wiping it by accident.
conn._edit("pass")
intent, callback = mpos.RESULTS_PENDING[-1]
equal("the stored password is never handed to the input screen",
      intent.extras["value"], "")
callback({"result_code": True, "data": {"value": "   "}})
equal("an empty entry keeps the old password", conn.password, "example-secret")
callback({"result_code": True, "data": {"value": "new-secret"}})
equal("a real one replaces it", conn.password, "new-secret")

conn._edit("user")
intent, callback = mpos.RESULTS_PENDING[-1]
callback({"result_code": True, "data": {"value": ""}})
equal("an empty user is allowed, that is anonymous", conn.user, "")
equal("and says so", conn.labels["user"][0].text, "Gebruiker: geen")

conn.onPause(None)
equal("leaving the screen applies the host", service.MQTT_BROKER, "10.9.9.9")
equal("the port", service.MQTT_PORT, 8884)
check("the anonymous user", service.MQTT_USER is None)
equal("and the new password", service.MQTT_PASS, "new-secret")
equal("the connection was dropped to pick them up", service.connected, False)


# ===========================================================================
# The LEDs nag, then give up
# ===========================================================================

svc = fresh_service()
BROKER.deliver(service.TOPIC_MSG, "Eten over 10 minuten")
svc._pump()
equal("lit on arrival", LightsManager.lit(), 5)
service._leds_tick()
equal("and dark on the next tick", LightsManager.lit(), 0)
service._leds_tick()
equal("back on again: it blinks", LightsManager.lit(), 5)

# Half a period per tick, so the blink is visible from a bed rather than being
# a once-a-second pulse.
check("blink period is under a second", service.TICK <= 0.5)

# Thirty minutes of flashing in a bedroom is worse than a message nobody
# answered, so the nagging stops. The message does not.
check("not expired yet", not service.alert_expired())
Clock.advance(30 * 60)
check("expired after the timeout", service.alert_expired())
service._leds_tick()
equal("LEDs give up", LightsManager.lit(), 0)
service._leds_tick()
equal("and stay dark", LightsManager.lit(), 0)
equal("but the message is still there", service.last_message,
      "Eten over 10 minuten")
check("and can still be acknowledged", service.has_unacked())
equal("acknowledging it still works", service.publish_ack(), True)

# A shorter timeout, set on the badge, is respected.
svc = fresh_service()
service.ACK_TIMEOUT_MIN = 10
BROKER.deliver(service.TOPIC_MSG, "Kom eens")
svc._pump()
Clock.advance(9 * 60)
check("still nagging at nine minutes", not service.alert_expired())
Clock.advance(2 * 60)
check("given up at eleven", service.alert_expired())

# LEDs switched off in the settings means no blinking at all.
svc = fresh_service()
service.LED_ALERT = False
BROKER.deliver(service.TOPIC_MSG, "Kom eens")
svc._pump()
equal("no LEDs when the setting is off", LightsManager.lit(), 0)
service._leds_tick()
equal("and none on the next tick either", LightsManager.lit(), 0)
check("the message still arrived", service.last_message_seq == 1)

# Acknowledging stops the blinking immediately.
svc = fresh_service()
BROKER.deliver(service.TOPIC_MSG, "Vaat")
svc._pump()
equal("blinking", LightsManager.lit(), 5)
service.publish_ack()
equal("dark the moment it is acknowledged", LightsManager.lit(), 0)
service._leds_tick()
equal("and it does not start again", LightsManager.lit(), 0)

# Shutting the service down must not leave the strip on.
svc = fresh_service()
BROKER.deliver(service.TOPIC_MSG, "Vaat")
svc._pump()
svc.onDestroy()
equal("LEDs off when the service stops", LightsManager.lit(), 0)


# ===========================================================================
# Telling the time
# ===========================================================================
# The badge keeps UTC and time.localtime() stays UTC even with the timezone
# preference on Europe/Brussels, measured on the device. Showing 14:02 when the
# kitchen clock says 16:02 makes "Eten over 10 minuten" useless, so the app
# converts through a POSIX zone and refuses to guess when it cannot.

# 2026-08-17 16:02:07 local == 14:02:07 UTC == 840290527 on MicroPython's epoch.
SUMMER_EVENING = 840290527
equal("time is shown in local time, not UTC",
      service.clock_text(SUMMER_EVENING), "16:02")
equal("no message means no time", service.clock_text(None), "")
equal("epoch zero is treated as no time", service.clock_text(0), "")

# A badge that never reached an NTP server reports the year 2000. A confident
# wrong time is worse than a blank.
equal("an unsynced clock shows nothing", service.clock_text(60), "")

mpos.time.localPTZtime.reset()
service.clock_text(SUMMER_EVENING)
equal("converted with the badge's own zone, not the app's default",
      mpos.time.localPTZtime.calls[0][1],
      mpos.time.ZONES["Europe/Brussels"])

# With the badge left on its shipped Etc/GMT, fall back to the configured zone
# rather than quietly showing UTC.
mpos.time.TimeZone.timezone_preference = "Etc/GMT"
equal("falls back to the configured zone when the badge is on Etc/GMT",
      service.posix_zone(), _config.TIMEZONE)
mpos.time.TimeZone.timezone_preference = "Europe/Brussels"
equal("otherwise follows the badge", service.posix_zone(),
      mpos.time.ZONES["Europe/Brussels"])


# ===========================================================================
# The screen
# ===========================================================================

def fresh_screen():
    svc = fresh_service()
    lv.DEFAULT_GROUP.objects = []
    mpos.ui.task_handler.cbs = []
    activity = DinerBadge()
    activity.onCreate()
    activity.onResume(activity.screen)
    return svc, activity


# Resolved against the real firmware's spellings. lv.label.LONG_MODE.WRAP is
# the only one that exists on this build; without it a long message runs off
# the side of a 320x240 screen instead of wrapping.
import dinerbadge as screen_module                       # noqa: E402
check("wrap mode resolved", screen_module.WRAP is not None)
check("disabled state resolved", screen_module.DISABLED is not None)
check("centre alignment resolved", screen_module.CENTERED is not None)
check("top-right alignment resolved", screen_module.ALIGN_TOP_RIGHT is not None)
check("notification icon resolves to a real symbol",
      service._icon() == lv.SYMBOL.BELL)

svc, app = fresh_screen()
equal("empty state says so", app.msg_label.text, "Geen berichten")
equal("no status text yet", app.status_label.text, "")
check("acknowledge button starts disabled", app.ack_btn.has_state(lv.STATE.DISABLED))
check("button is reachable with the d-pad",
      app.ack_btn in lv.DEFAULT_GROUP.objects)
equal("title is the badge's name", app.title.text, "Alice")
check("the gear is reachable with the d-pad",
      app.gear_btn in lv.DEFAULT_GROUP.objects)

# Renaming in the settings screen has to show up here without a reboot.
service.set_child_name("bob")
app._refresh()
equal("the title follows a rename", app.title.text, "Bob")
service.set_child_name("alice")
app._refresh()
equal("and back", app.title.text, "Alice")
# Both renames dropped the MQTT connection, which is the point of them. Let the
# loop pick it back up before the screen tests send anything.
svc._pump()
equal("reconnected after the renames", service.connected, True)

equal("no time before the first message", app.time_label.text, "")

BROKER.deliver(service.TOPIC_MSG, "Eten over 10 minuten")
svc._pump()
service.last_message_time = SUMMER_EVENING     # pin it, the clock moves
app._shown_seq = -1
app._refresh()
equal("message on screen", app.msg_label.text, "Eten over 10 minuten")
equal("send time on screen", app.time_label.text, "gestuurd om 16:02")
equal("flagged as new", app.status_label.text, "Nieuw bericht!")
check("button enabled", not app.ack_btn.has_state(lv.STATE.DISABLED))

app.ack_btn.click()
equal("tapping publishes the ack", BROKER.published,
      [("home/badges/alice/ack", "Eten over 10 minuten")])
equal("screen confirms", app.status_label.text, "Bevestigd")
check("button disabled again", app.ack_btn.has_state(lv.STATE.DISABLED))

app.ack_btn.click()
equal("a second tap changes nothing", len(BROKER.published), 1)

# Same text again: the child must be alerted a second time and the button must
# come back, which is the screen-side half of the sequence-not-text rule.
BROKER.deliver(service.TOPIC_MSG, "Eten over 10 minuten")
svc._pump()
app._refresh()
equal("repeated message flagged as new again", app.status_label.text,
      "Nieuw bericht!")
check("and acknowledgeable again",
      not app.ack_btn.has_state(lv.STATE.DISABLED))

# An ack that never left the badge must not show a green tick: nobody in the
# kitchen is going to see it.
svc, app = fresh_screen()
BROKER.deliver(service.TOPIC_MSG, "Kom eens")
svc._pump()
app._refresh()
BROKER.up = False
app.ack_btn.click()
equal("failed ack is reported honestly", app.status_label.text,
      "Bevestigd, nog niet verzonden")

# And says so no longer than it has to: once the link is back and the held ack
# goes out, the screen catches up on its own.
BROKER.up = True
for _ in range(70):
    Clock.advance(1)
    svc._pump()
    if service.connected:
        break
app._refresh()
equal("the screen catches up by itself", app.status_label.text, "Bevestigd")

# Connection state is visible, so a child can tell a dead badge from a quiet
# evening.
svc, app = fresh_screen()
app._refresh()
equal("connected badge says so", app.link.text, "verbonden")
service.connected = False
app._refresh()
equal("disconnected badge says so", app.link.text, "geen verbinding")

# Reopening the app must not re-alert an already acknowledged message.
svc, app = fresh_screen()
BROKER.deliver(service.TOPIC_MSG, "Vaat")
svc._pump()
app._refresh()
app.ack_btn.click()
app.onPause(app.screen)
app.onResume(app.screen)
equal("acked message still shown on re-entry", app.msg_label.text, "Vaat")
equal("and still marked confirmed", app.status_label.text, "Bevestigd")
check("button stays disabled", app.ack_btn.has_state(lv.STATE.DISABLED))

# Frame callbacks are removed by identity on the real firmware. A bound method
# read twice is two objects, so a leak here is invisible until the badge slows
# down after a few app switches.
svc, app = fresh_screen()
equal("one frame callback while visible", len(mpos.ui.task_handler.cbs), 1)
app.onPause(app.screen)
equal("callback removed on pause", len(mpos.ui.task_handler.cbs), 0)
app.onResume(app.screen)
app.onPause(app.screen)
equal("and again after a second round", len(mpos.ui.task_handler.cbs), 0)


# ===========================================================================

service.time = _real_time
mpos.TaskManager.reset()

print()
if FAILURES:
    print("%d of %d checks failed" % (len(FAILURES), CHECKS["n"]))
    for failure in FAILURES:
        print("  -", failure)
    sys.exit(1)
print("%d checks passed" % CHECKS["n"])
