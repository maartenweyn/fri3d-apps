"""Configuration for the Berichtjes app.

Copy this file to `dinerbadge_config.py` and edit it. That copy is gitignored.

Only two settings live here now, both about messages. The name of the badge, the
broker address and the MQTT password moved to the Badge app
(`be.weyn.badge/badge_config.example.py`), because they describe the badge and
not this app. One badge, one connection, one place to set it up.

Both values below are also editable on the badge itself, behind the gear button,
and what is set there wins. These are only the starting point for a badge that
has never been set up.
"""

# Blink the five onboard LEDs while a message is unacknowledged, and how long to
# keep it up. The blinking stops after this many minutes; the message stays on
# screen and stays acknowledgeable. A light flashing in a bedroom all night is
# worse than a message nobody answered.
LED_ALERT = True
ACK_TIMEOUT_MIN = 30
