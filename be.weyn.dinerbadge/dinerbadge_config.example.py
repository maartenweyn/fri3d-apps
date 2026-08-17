"""Configuration for the Berichtjes app.

Copy this file to `dinerbadge_config.py` and edit it. That copy is gitignored,
because it holds the broker address and the MQTT password in plain text, and
neither belongs in a repository.

The same copy goes on every badge in the house. Which badge is which is typed
on the badge itself, in the settings screen behind the gear button, and stored
in SharedPreferences. The values here are only the starting point for a badge
that has never been set up.
"""

# What a badge is called before anyone types a name in the settings screen. It
# has to match a topic Home Assistant publishes to: home/badges/<name>/msg.
# See docs/berichtjes-homeassistant/README.md.
CHILD_NAME = "alice"

# Starting values for the broker, for a badge nobody has set up yet. All four
# are also editable on the badge, behind the gear button under "Verbinding...",
# and what is set there wins. Leaving them like this is fine: it means every
# badge is configured on the badge, and no password is ever written to a file.
#
# Use Home Assistant's IP rather than a .local name; mDNS is unreliable on an
# ESP32. The Mosquitto add-on does not accept anonymous clients by default, so
# give the badges their own login: a `logins:` entry in the add-on
# configuration, or a Home Assistant user for them.
MQTT_BROKER = ""
MQTT_PORT = 1883
MQTT_USER = None
MQTT_PASS = None

# Blink the five onboard LEDs while a message is unacknowledged, and how long
# to keep it up. The blinking stops after this many minutes; the message stays
# on screen and stays acknowledgeable. A light flashing in a bedroom all night
# is worse than a message nobody answered. Both are adjustable on the badge.
LED_ALERT = True
ACK_TIMEOUT_MIN = 30

# POSIX timezone for showing the time a message was sent. The badge keeps its
# clock in UTC and time.localtime() stays UTC even once the timezone is set in
# Settings, so the conversion happens here. This is only a fallback: whatever
# the badge itself is set to wins. The string carries the DST rules, so it
# stays right across the autumn change. Central European time shown here.
TIMEZONE = "CET-1CEST,M3.5.0,M10.5.0/3"
