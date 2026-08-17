# Home Assistant side of Berichtjes

These are the pieces Home Assistant needs so a dashboard button ends up on a
badge, and so you can see at a glance whether anyone answered.

The examples use two badges named `alice` and `bob`. Rename them to whatever you
type in each badge's settings screen; the name on the badge and the name in the
topic have to match exactly. The badge lowercases what you type and strips what
cannot go in a topic, so type it in lowercase here too.

    home/badges/<name>/msg      Home Assistant publishes, the badge listens
    home/badges/<name>/ack      the badge publishes when the button is tapped

## Files, in the order to apply them

| File | Goes into |
| --- | --- |
| `01-configuration.yaml` | `configuration.yaml` |
| `02-scripts.yaml` | `scripts.yaml` |
| `03-mqtt.yaml` | your MQTT config, normally `mqtt.yaml` |
| `04-status-sensors.yaml` | your template config, normally `sensor_template.yaml` |
| `05-lovelace-card.yaml` | pasted into a dashboard, not into a config file |

Each file starts with a comment saying where it goes and what to watch out for.

**YAML does not allow a duplicate top-level key.** If your configuration already
has `input_datetime:`, `input_text:` or `sensor:`, add the children from these
examples to the key you already have rather than creating a second one. Check
before pasting; this is the mistake that costs an evening.

## How the status works

Each badge gets a template sensor with three states: neutral, waiting,
confirmed. Sending sets the badge's `input_datetime`, so the sensor goes to
waiting. The badge publishes to the ack topic when the child taps the button,
which timestamps the ack sensor, so the status goes to confirmed. Half an hour
later both fall back to neutral.

The dashboard colours on that: grey, red, green. Sending to both turns both rows
red, and each turns green on its own as that child answers.

There is deliberately no automation and no notification. A template containing
`now()` is re-rendered by Home Assistant every minute, so the fall back to
neutral happens by itself, with no timer to survive a restart and nothing
arriving on your phone at dinner time.

**Keep the timeout in step.** The 1800 seconds in `04-status-sensors.yaml` and
`ACK_TIMEOUT_MIN` in the badge's config are separate settings for the same idea.
Different values mean a badge still blinking at a dashboard that has gone grey.

## What to change

1. The two names, `alice` and `bob`, everywhere they appear.
2. The half hour, in both places, if that is too soon or too late.

The card needs `custom:button-card` from HACS, which is what gives a real red
and green. Without it, replace the three status cards with plain `entities` rows
showing the status sensors; you lose the colour and keep the information.

## After editing

Validate with Developer tools, Check configuration, or `ha core check` on the
host. Then Reload all YAML configuration, or restart if you added
`input_datetime` or `input_text` entries, which need a restart on some versions.

Test it before wiring up buttons: Developer tools, Actions, run
`script.send_badge_message` with `target: alice` and any text. The badge should
chime, blink and show the message within a second, its status should go red, and
tapping Ontvangen should turn it green.

## The broker

The badges connect to the same MQTT broker as Home Assistant, normally the
Mosquitto add-on on port 1883. Give the badges their own login rather than
reusing yours: add a `logins:` entry in the add-on configuration, or create a
Home Assistant user for them, and restart the add-on. A broker that refuses
anonymous clients answers `CONNACK 5`, which is also what you get for a user
that does not exist, so if a badge says "geen verbinding" that is the first
thing to check.

Broker address and credentials go in `dinerbadge_config.py` on the badge, which
is gitignored. Nothing in this repository should ever hold them.
