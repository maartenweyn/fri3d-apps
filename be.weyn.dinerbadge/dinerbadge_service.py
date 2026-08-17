"""Background MQTT receiver for the Berichtjes app.

Runs as a MicroPythonOS Service on `boot_completed`, so it keeps listening no
matter which app is on screen. On a message it posts a Notification (the system
plays the notification chime on the buzzer), blinks the LEDs until someone
acknowledges, and pulls the Berichtjes activity to the foreground.

It also reports the badge's own health, battery and WiFi signal, and announces
those to Home Assistant through MQTT discovery, so the sensors appear without
anybody editing YAML for them.

The activity reads this module's globals directly. Service and activity live in
the same MicroPython process, so a plain `import` is the whole IPC story.

Which badge this is, and which broker to talk to, come from SharedPreferences,
set on the badge itself in the settings screens, so every badge runs an
identical copy of the app and nothing sensitive has to live in a file. The
config file only supplies starting values for a badge nobody has set up yet.

Nothing here creates LVGL objects: a Service has no screen.
"""

import json
import time

# --- mpos imports, defensively ---------------------------------------------
# This firmware does not export everything the docs promise, and the shape of
# an import is the first thing to break. Resolve each name across the places
# it is known to live and fail loudly with a name we can grep for.

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
    raise ImportError("dinerbadge: no %s in mpos or %s" % (name, paths))


Service = _mpos("Service", "mpos.app.service")
Notification = _mpos("Notification", "mpos.notification", "mpos.ui.notification")
NotificationManager = _mpos("NotificationManager", "mpos.notification",
                            "mpos.ui.notification")
Intent = _mpos("Intent", "mpos.content.intent")
AppManager = _mpos("AppManager", "mpos.content.app_manager")
TaskManager = _mpos("TaskManager", "mpos.task_manager")
SharedPreferences = _mpos("SharedPreferences", "mpos.config")

APP_FULLNAME = "be.weyn.dinerbadge"
PREFS_APP_ID = APP_FULLNAME

# --- configuration ---------------------------------------------------------
# dinerbadge_config.py is gitignored and holds the per-installation values,
# broker address and credentials included. These defaults only exist so a badge
# without a config file still boots; they are not expected to work.
CHILD_NAME = "badge"
MQTT_BROKER = "homeassistant.local"
MQTT_PORT = 1883
MQTT_USER = None
MQTT_PASS = None
LED_ALERT = True
ACK_TIMEOUT_MIN = 30
TIMEZONE = "CET-1CEST,M3.5.0,M10.5.0/3"
# Where Home Assistant listens for discovery. "homeassistant" is the default and
# almost nobody changes it; the ones who did know they did.
DISCOVERY_PREFIX = "homeassistant"
CONFIG_OK = False

try:
    import dinerbadge_config as _cfg
    CHILD_NAME = getattr(_cfg, "CHILD_NAME", CHILD_NAME)
    MQTT_BROKER = getattr(_cfg, "MQTT_BROKER", MQTT_BROKER)
    MQTT_PORT = getattr(_cfg, "MQTT_PORT", MQTT_PORT)
    MQTT_USER = getattr(_cfg, "MQTT_USER", None)
    MQTT_PASS = getattr(_cfg, "MQTT_PASS", None)
    LED_ALERT = getattr(_cfg, "LED_ALERT", True)
    ACK_TIMEOUT_MIN = getattr(_cfg, "ACK_TIMEOUT_MIN", ACK_TIMEOUT_MIN)
    TIMEZONE = getattr(_cfg, "TIMEZONE", TIMEZONE)
    DISCOVERY_PREFIX = getattr(_cfg, "DISCOVERY_PREFIX", DISCOVERY_PREFIX)
    CONFIG_OK = True
except ImportError:
    print("dinerbadge: no dinerbadge_config.py, using defaults")

TOPIC_MSG = ""
TOPIC_ACK = ""
TOPIC_STATE = ""         # retained JSON: battery, voltage, signal strength
TOPIC_STATUS = ""        # retained online/offline, also the MQTT last will
CLIENT_ID = ""

# Backoff between connection attempts, seconds. A child's badge spends plenty
# of time out of WiFi range, and retrying every second there costs battery for
# nothing.
RETRY_MIN = 2
RETRY_MAX = 60
PING_EVERY = 20          # keepalive is 60s; ping well inside that
SOCKET_TIMEOUT = 5       # never let a dead broker block the LVGL thread
TICK = 0.5               # loop period, also the LED blink half-period

# How often the badge reports its battery. A lanyard badge discharges over
# hours; reading it every few seconds would only add radio traffic and noise on
# a graph. The ADC behind it is cached for 30 seconds anyway.
STATE_EVERY = 300

# --- shared state, read by the activity ------------------------------------
last_message = None
last_message_seq = 0     # increments per message, so the same text twice is
                         # still two messages. Never compare texts for this.
last_message_time = None
acked_seq = 0
connected = False
last_error = None
leds_lit = False         # what the LEDs are doing, so the tests can see it
pending_ack = None       # an acknowledgement the link was not up for
battery_pct = None       # last reading, as published
battery_volt = None
wifi_rssi = None

_service = None


def titlecase(name):
    """Uppercase the first letter.

    Sixteen CPython string methods are missing on this firmware, the one that
    reads naturally here among them. Do it by hand.
    """
    return name[:1].upper() + name[1:]


# --- which badge this is ---------------------------------------------------

NAME_OK = "abcdefghijklmnopqrstuvwxyz0123456789-_"


def normalize_name(text):
    """Make a typed name safe to put in an MQTT topic, or return "".

    The name is typed on a touchscreen by a child, and it has to match a topic
    Home Assistant publishes to. A capital, a trailing space or a slash would
    point the badge at a topic nobody publishes to, and then nothing arrives
    and nothing complains. Fold what can be folded, drop what cannot.
    """
    if not text:
        return ""
    out = []
    for ch in text.strip().lower():
        if ch in NAME_OK:
            out.append(ch)
        elif ch in " \t.":
            out.append("-")
        # anything else, including / + # which mean something to a broker, is
        # dropped rather than translated into a surprise.
    name = "".join(out).strip("-")
    while "--" in name:
        name = name.replace("--", "-")
    return name[:24]


def describe_error(error):
    """Say what went wrong in words, not in an errno.

    The connection screen shows this while someone is typing an address in, and
    "geen verbinding: -1" tells them nothing about which of the four fields to
    look at. CONNACK 5 in particular means the broker knows who you claim to be
    and does not accept it, which is a different problem from a wrong address.
    """
    if error is None:
        return None
    code = None
    args = getattr(error, "args", ())
    if args and isinstance(args[0], int):
        code = args[0]
    name = type(error).__name__
    if name == "MQTTException":
        if code == 5:
            return "login geweigerd"
        if code == 4:
            return "gebruiker of wachtwoord fout"
        if code == 3:
            return "broker niet beschikbaar"
        return "broker weigert (code %s)" % code
    if isinstance(error, OSError) or name in ("OSError", "ETIMEDOUT"):
        return "geen antwoord van de broker"
    text = str(error)
    return text or name


def normalize_port(text):
    """A port number, or 0 if that is not what was typed."""
    try:
        port = int(str(text).strip())
    except (ValueError, TypeError):
        return 0
    return port if 1 <= port <= 65535 else 0


def device_suffix():
    """Six hex digits that are this badge and no other.

    The client id used to be badge_<name>, and two badges briefly named the
    same thing is not a hypothetical: it is what happens while you are setting
    the second one up. A broker evicts the older of two clients claiming one id,
    so the two take turns kicking each other off, forever, and it looks exactly
    like a flaky network. Derived from the MAC, so it survives a rename and a
    reflash.
    """
    try:
        import machine
        import ubinascii
        return ubinascii.hexlify(machine.unique_id()).decode()[-6:]
    except Exception:
        try:
            import network
            import ubinascii
            mac = network.WLAN(network.STA_IF).config("mac")
            return ubinascii.hexlify(mac).decode()[-6:]
        except Exception:
            return "unknown"


DEVICE_SUFFIX = device_suffix()


def set_child_name(name):
    """Point this badge at a name, and rebuild everything derived from it.

    The topics carry the name, so changing it has to drop the MQTT connection:
    a client stays subscribed to what it asked for, and nothing would arrive on
    the new topic until it resubscribes.
    """
    global CHILD_NAME, TOPIC_MSG, TOPIC_ACK, TOPIC_STATE, TOPIC_STATUS
    global CLIENT_ID
    name = normalize_name(name)
    if not name:
        return False
    changed = name != CHILD_NAME
    CHILD_NAME = name
    TOPIC_MSG = "home/badges/%s/msg" % name
    TOPIC_ACK = "home/badges/%s/ack" % name
    TOPIC_STATE = "home/badges/%s/state" % name
    TOPIC_STATUS = "home/badges/%s/status" % name
    # The name is in there for whoever reads the broker log; the suffix is
    # what makes it unique.
    CLIENT_ID = "badge_%s_%s" % (name, DEVICE_SUFFIX)
    if changed and _service is not None:
        _service.resubscribe()
    return changed


def load_prefs():
    """Read the values the settings screens write, and apply them.

    Anything the connection depends on has to drop that connection: a client
    stays subscribed to what it asked for and keeps talking to the host it
    dialled, so changing either without reconnecting leaves the badge sitting
    there looking fine and hearing nothing.
    """
    global LED_ALERT, ACK_TIMEOUT_MIN
    global MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS
    name = CHILD_NAME
    before = (MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS)
    try:
        prefs = SharedPreferences(PREFS_APP_ID)
        name = prefs.get_string("child_name", CHILD_NAME) or CHILD_NAME
        LED_ALERT = bool(prefs.get_int("led_alert", 1 if LED_ALERT else 0))
        ACK_TIMEOUT_MIN = prefs.get_int("ack_timeout_min", ACK_TIMEOUT_MIN)

        MQTT_BROKER = prefs.get_string("mqtt_host", MQTT_BROKER) or MQTT_BROKER
        MQTT_PORT = normalize_port(prefs.get_int("mqtt_port", MQTT_PORT)) \
            or MQTT_PORT
        # An empty string is how "anonymous" is stored; umqtt wants None.
        MQTT_USER = prefs.get_string("mqtt_user", MQTT_USER or "") or None
        MQTT_PASS = prefs.get_string("mqtt_pass", MQTT_PASS or "") or None
    except Exception as e:
        print("dinerbadge: could not read prefs:", e)

    renamed = set_child_name(name)
    if not renamed and before != (MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS):
        print("dinerbadge: broker changed to %s:%s" % (MQTT_BROKER, MQTT_PORT))
        if _service is not None:
            _service.resubscribe()
        return True
    return renamed


set_child_name(CHILD_NAME)


def posix_zone():
    """The POSIX timezone string to convert with.

    Prefer whatever the badge is set to, so the Settings app stays the one
    place to change it, and fall back to the configured value. The preference
    is a plain attribute on this firmware but a method on others.
    """
    try:
        import mpos.time
        pref = mpos.time.TimeZone.timezone_preference
        if callable(pref):
            pref = pref()
        if pref and pref != "Etc/GMT":
            zone = mpos.time.TimeZone.timezone_to_posix_time_zone(pref)
            if zone:
                return zone
    except Exception:
        pass
    return TIMEZONE


def clock_text(epoch):
    """The time as a kitchen clock shows it, or "" if it cannot be trusted.

    The badge keeps its clock in UTC and `time.localtime()` returns UTC even
    with the timezone preference set to Europe/Brussels, so a naive read is two
    hours behind in summer. A wrong time under "Eten over 10 minuten" is worse
    than no time at all: convert through the POSIX zone, and give up rather
    than guess.
    """
    if not epoch:
        return ""
    parts = None
    try:
        import mpos.time
        parts = mpos.time.localPTZtime.tztime(epoch, posix_zone())
    except Exception:
        try:
            import time as _time
            parts = _time.localtime(epoch)
        except Exception:
            return ""
    if parts is None or len(parts) < 5:
        return ""
    if parts[0] < 2024:          # clock never synced, do not invent a time
        return ""
    return "%02d:%02d" % (parts[3], parts[4])


# --- telemetry -------------------------------------------------------------

def os_release():
    """The MicroPythonOS version, for the device page in Home Assistant."""
    try:
        import mpos
        return str(mpos.BuildInfo.version.release)
    except Exception:
        return None


def battery_reading():
    """Battery, voltage and signal strength, as far as this badge can tell.

    Every field is optional and missing is not an error: a badge running off
    USB with no cell in it, or a firmware without the ADC wired up, should still
    report the signal strength it does know rather than nothing at all.
    """
    state = {}
    try:
        import mpos
        manager = mpos.BatteryManager
        if manager.has_battery():
            percentage = manager.get_battery_percentage()
            if percentage is not None:
                state["battery"] = int(round(percentage))
            volt = manager.read_battery_voltage()
            if volt:
                state["voltage"] = round(volt, 2)
    except Exception as e:
        print("dinerbadge: no battery reading:", e)
    try:
        import network
        state["rssi"] = network.WLAN(network.STA_IF).status("rssi")
    except Exception:
        pass
    return state


# key, name in Home Assistant, device class, unit, decimals
TELEMETRY = (
    ("battery", "Battery", "battery", "%", 0),
    ("voltage", "Battery voltage", "voltage", "V", 2),
    ("rssi", "WiFi signal", "signal_strength", "dBm", 0),
)


def discovery_payloads():
    """The MQTT discovery messages that make Home Assistant create the sensors.

    Keyed on the badge's MAC, not on its name, so renaming a badge updates the
    entities that already exist rather than leaving a second set of dead ones
    behind. Home Assistant keeps the history that way too.

    The short keys are not an accident: this is the abbreviated form of the
    discovery schema, and these payloads go over a radio in a bedroom.
    """
    device = {
        "ids": ["fri3d_badge_%s" % DEVICE_SUFFIX],
        "name": "Badge %s" % titlecase(CHILD_NAME),
        "mf": "Fri3d Camp",
        "mdl": "Fri3d 2026 badge",
    }
    release = os_release()
    if release:
        device["sw"] = release

    out = []
    for key, name, device_class, unit, decimals in TELEMETRY:
        out.append((
            "%s/sensor/badge_%s/%s/config" % (DISCOVERY_PREFIX, DEVICE_SUFFIX,
                                              key),
            {
                "name": name,
                "uniq_id": "fri3d_badge_%s_%s" % (DEVICE_SUFFIX, key),
                "obj_id": "badge_%s_%s" % (CHILD_NAME, key),
                "stat_t": TOPIC_STATE,
                "avty_t": TOPIC_STATUS,
                "val_tpl": "{{ value_json.%s }}" % key,
                "dev_cla": device_class,
                "stat_cla": "measurement",
                "unit_of_meas": unit,
                "sug_dsp_prc": decimals,
                "ent_cat": "diagnostic",
                "dev": device,
            },
        ))
    return out


def has_unacked():
    return last_message_seq > acked_seq


def alert_expired():
    """True once the LEDs have nagged for long enough.

    The message stays on screen and stays acknowledgeable; only the blinking
    gives up, because a bedroom with a light flashing all night is worse than
    a message nobody answered.
    """
    if not has_unacked() or not last_message_time:
        return False
    return (time.time() - last_message_time) >= ACK_TIMEOUT_MIN * 60


def publish_ack(seq=None):
    """Called by the activity when the child taps 'Ontvangen'.

    Marks the message acknowledged locally even when the publish fails, so the
    button does not lie to the child about what it did.
    """
    global acked_seq
    if seq is None:
        seq = last_message_seq
    if seq <= 0 or seq <= acked_seq:
        # Already acknowledged. Publishing again would restart Home Assistant's
        # waiting clock for a message nobody just read.
        return False
    global pending_ack
    acked_seq = seq
    _leds_off()
    text = last_message or "ack"
    if _service is not None and _service.publish_ack(text):
        pending_ack = None
        return True
    # A bedroom at the edge of the WiFi is exactly where a child presses the
    # button and the publish fails. Hold on to it: Home Assistant would
    # otherwise show red for half an hour for a message that was read.
    pending_ack = text
    return False


# --- LEDs ------------------------------------------------------------------
# mpos.lights on this firmware. All of this is best-effort: no LEDs must never
# break a message.

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
        return                     # do not rewrite the strip every tick
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
    """Blink while a message is waiting, dark otherwise."""
    if not LED_ALERT or not has_unacked() or alert_expired():
        _leds_off()
        return
    _leds_write(not leds_lit)


def _icon():
    """A notification icon that exists on this build."""
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


class DinerBadgeService(Service):

    def __init__(self):
        super().__init__()
        self._mqtt = None
        self._running = False
        self._next_try = 0
        self._backoff = RETRY_MIN
        self._last_ping = 0
        self._next_state = 0
        self._live_name = None    # the name we last published under

    def onCreate(self):
        global _service
        # A second instance would run its own loop against the same broker with
        # the same client id, and the broker evicts the older of two clients
        # that claim the same id. The two then take turns kicking each other off
        # forever, which looks exactly like a flaky network. Retire the old one.
        previous = _service
        if previous is not None and previous is not self:
            print("dinerbadge: retiring the previous service instance")
            try:
                previous.onDestroy()
            except Exception as e:
                print("dinerbadge: could not stop the previous service:", e)
        _service = self
        load_prefs()
        print("dinerbadge: service created for", CHILD_NAME,
              "topic", TOPIC_MSG)

    def onStart(self, intent=None):
        if self._running:
            # Being started twice is not hypothetical: anything that launches
            # the app can start its manifest-declared services again, and the
            # second loop shares this instance's client while racing it.
            print("dinerbadge: already running, not starting a second loop")
            return
        self._running = True
        TaskManager.create_task(self._run())

    def onDestroy(self):
        self._running = False
        # A clean disconnect does not fire the last will, so the badge would
        # stay "online" in Home Assistant until the next reboot. Say so here.
        self._publish(TOPIC_STATUS, "offline")
        self._close()
        _leds_off()

    def resubscribe(self):
        """Drop the connection so the loop reconnects on the new topic."""
        print("dinerbadge: name changed, resubscribing as", CHILD_NAME)
        self._retire_topics()
        self._close()
        self._backoff = RETRY_MIN
        self._next_try = 0

    # --- main loop ---------------------------------------------------------

    async def _run(self):
        while self._running:
            try:
                self._pump()
            except Exception as e:            # never let the loop die
                print("dinerbadge: loop error:", e)
                self._close()
            try:
                _leds_tick()
            except Exception:
                pass
            await TaskManager.sleep(TICK)

    def _pump(self):
        now = time.time()
        if self._mqtt is None:
            if now >= self._next_try and self._wifi_up():
                self._connect(now)
            return
        try:
            self._mqtt.check_msg()
            if now - self._last_ping >= PING_EVERY:
                self._mqtt.ping()
                self._last_ping = now
            if now >= self._next_state:
                self._publish_state(now)
        except Exception as e:
            print("dinerbadge: connection lost:", e)
            self._fail(e, now)

    def _wifi_up(self):
        try:
            import network
            wlan = network.WLAN(network.STA_IF)
            return bool(wlan.active() and wlan.isconnected())
        except Exception:
            return False

    def _connect(self, now):
        global connected, last_error
        try:
            from umqtt.simple import MQTTClient
        except ImportError as e:
            # One-off per badge if the firmware lacks it: mip.install("umqtt.simple")
            last_error = "umqtt.simple ontbreekt"
            print("dinerbadge:", last_error, e)
            self._next_try = now + RETRY_MAX
            return
        try:
            try:
                client = MQTTClient(
                    CLIENT_ID, MQTT_BROKER, port=MQTT_PORT,
                    user=MQTT_USER, password=MQTT_PASS, keepalive=60,
                    socket_timeout=SOCKET_TIMEOUT,
                )
            except TypeError:
                # The umqtt.simple in this firmware has no socket_timeout.
                client = MQTTClient(
                    CLIENT_ID, MQTT_BROKER, port=MQTT_PORT,
                    user=MQTT_USER, password=MQTT_PASS, keepalive=60,
                )
            client.set_callback(self._on_message)
            # Registered with the broker before connecting, so a badge that
            # walks out of range or runs flat is marked offline by the broker
            # rather than sitting there showing its last battery reading
            # forever.
            try:
                client.set_last_will(TOPIC_STATUS, "offline", retain=True)
            except Exception as e:
                print("dinerbadge: no last will:", e)
            client.connect()
            client.subscribe(TOPIC_MSG)
            self._mqtt = client
            self._backoff = RETRY_MIN
            self._last_ping = now
            connected = True
            last_error = None
            print("dinerbadge: subscribed to", TOPIC_MSG)
            self._flush_ack()
            self._announce(now)
        except Exception as e:
            self._fail(e, now)

    def _fail(self, error, now):
        global connected, last_error
        self._close()
        last_error = describe_error(error)
        self._next_try = now + self._backoff
        self._backoff = min(self._backoff * 2, RETRY_MAX)

    def _close(self):
        global connected
        connected = False
        if self._mqtt is not None:
            try:
                self._mqtt.disconnect()
            except Exception:
                pass
            self._mqtt = None

    # --- incoming ----------------------------------------------------------

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
        print("dinerbadge: message", last_message_seq, repr(text))

        _leds_tick()

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
            print("dinerbadge: notify failed:", e)

        # Pull the app to the front even if the child was playing a game.
        try:
            AppManager.start_app(APP_FULLNAME)
        except Exception as e:
            print("dinerbadge: start_app failed:", e)

    # --- outgoing ----------------------------------------------------------

    def _publish(self, topic, payload, retain=True):
        """One retained publish, with a dict turned into JSON on the way out."""
        if self._mqtt is None or not topic:
            return False
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        try:
            self._mqtt.publish(topic, payload, retain=retain)
            return True
        except Exception as e:
            print("dinerbadge: publish to %s failed:" % topic, e)
            self._fail(e, time.time())
            return False

    def _announce(self, now):
        """Say what this badge is, and that it is here.

        All of it retained, so a Home Assistant that restarts tomorrow morning
        gets the sensors and their last values from the broker without the badge
        having to be awake for it. Republished on every reconnect, which is also
        how a renamed badge points its existing entities at the new topic.
        """
        self._live_name = CHILD_NAME
        if not self._publish(TOPIC_STATUS, "online"):
            return
        for topic, config in discovery_payloads():
            if not self._publish(topic, config):
                return
        self._publish_state(now)

    def _publish_state(self, now):
        global battery_pct, battery_volt, wifi_rssi
        self._next_state = now + STATE_EVERY
        state = battery_reading()
        battery_pct = state.get("battery")
        battery_volt = state.get("voltage")
        wifi_rssi = state.get("rssi")
        if not state:
            return False           # nothing measurable; do not publish {}
        state["name"] = CHILD_NAME
        return self._publish(TOPIC_STATE, state)

    def _retire_topics(self):
        """Clear what we published under the name we are leaving behind.

        Retained messages outlive the client that sent them. Without this, a
        badge renamed from alice to bob leaves a retained battery reading on
        alice's topic that nothing will ever update and nothing will ever clear.
        An empty payload is how MQTT deletes one.
        """
        old = self._live_name
        self._live_name = None
        if not old or old == CHILD_NAME or self._mqtt is None:
            return
        print("dinerbadge: clearing the retained state of", old)
        for suffix in ("state", "status"):
            try:
                self._mqtt.publish("home/badges/%s/%s" % (old, suffix), "",
                                   retain=True)
            except Exception as e:
                print("dinerbadge: could not clear %s:" % suffix, e)
                return

    def _flush_ack(self):
        """Send what the last outage swallowed, now that there is a link."""
        global pending_ack
        if pending_ack is None:
            return
        text = pending_ack
        if self.publish_ack(text):
            pending_ack = None
            print("dinerbadge: held-back ack sent")

    def publish_ack(self, text):
        if self._mqtt is None:
            print("dinerbadge: ack not sent, no connection")
            return False
        try:
            self._mqtt.publish(TOPIC_ACK, text)
            print("dinerbadge: ack published")
            return True
        except Exception as e:
            print("dinerbadge: ack publish failed:", e)
            self._fail(e, time.time())
            return False
