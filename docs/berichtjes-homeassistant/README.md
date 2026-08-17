# Berichtjes: setting it up

Everything needed to get a badge chiming from a Home Assistant button, and the
dashboard turning green when someone answers.

About twenty minutes, most of it pasting YAML. Do the broker first, then the
badge, then Home Assistant: each step is testable on its own, which is worth a
lot when something does not work.

## What you need

- A Fri3d 2026 badge with the Berichtjes app installed. See the
  [repository README](../../README.md) for installing an app.
- Home Assistant.
- An MQTT broker both can reach, normally the Mosquitto add-on, and the
  [MQTT integration](https://www.home-assistant.io/integrations/mqtt/) set up in
  Home Assistant.

One badge is enough. The examples use two, `alice` and `bob`, because the second
one is where the interesting mistakes live.

## 1. Give the badges a broker login

Do not reuse your own account. In the Mosquitto add-on configuration, add:

```yaml
logins:
  - username: badge
    password: something-long
```

Restart the add-on. One login for all your badges is fine; they are told apart
by their client id, not by their user.

A broker that refuses anonymous clients answers `CONNACK 5`, and so does a user
that does not exist, so this is the first thing to check when a badge says
`geen verbinding`. The badge spells it out as `login geweigerd` under the gear
button, in Verbinding.

## 2. Set up each badge

Everything is typed on the badge itself, behind the gear button at the bottom
left. No file to edit, so every badge runs an identical copy of the app.

- **Deze badge** — the name. It goes straight into the MQTT topic, so the badge
  lowercases it and strips anything a topic cannot carry. Give each badge its
  own name and write down what you chose; Home Assistant needs the same.
- **Verbinding** — broker address, port, user, password. Use Home Assistant's IP
  rather than a `.local` name; mDNS is unreliable on an ESP32. The password is
  never shown, and leaving the field empty keeps the one already stored.

Settings are saved when you leave the screen, so go back rather than rebooting.
Verbinding shows the live connection state while you are standing there, which
is the point of it: type an address, go back, come in again, and it either says
`verbonden met ...` or tells you why not.

    home/badges/<name>/msg      Home Assistant publishes, the badge listens
    home/badges/<name>/ack      the badge publishes when the button is tapped

## 3. Paste the Home Assistant side

| File | Goes into |
| --- | --- |
| `01-configuration.yaml` | `configuration.yaml` |
| `02-scripts.yaml` | `scripts.yaml` |
| `03-mqtt.yaml` | your MQTT config, normally `mqtt.yaml` |
| `04-status-sensors.yaml` | your template config, normally `sensor_template.yaml` |
| `05-lovelace-card.yaml` | pasted into a dashboard, not into a config file |

Each file starts with a comment saying where it goes and what to watch for.

Rename `alice` and `bob` to the names you typed on the badges, everywhere they
appear. That is the only edit most people need.

**YAML does not allow a duplicate top-level key.** If your configuration already
has `input_datetime:`, `input_text:` or `sensor:`, add the children from these
examples to the key you already have rather than creating a second one. Check
before pasting; this is the mistake that costs an evening.

**Where automations live differs between setups.** These examples do not use any,
but if you add one: `automation: !include_dir_merge_list automations/` means a
root `automations.yaml` is not read at all, and your automation belongs in a file
in that directory.

Then validate under Developer tools, Check configuration, or `ha core check` on
the host, and reload all YAML. Adding `input_datetime` or `input_text` entries
needs a full restart on some versions.

The dashboard card needs
[button-card](https://github.com/custom-cards/button-card) from HACS, which is
what gives a real red and green. Without it, replace the three status cards with
plain `entities` rows showing the status sensors: you lose the colour and keep
the information.

## 4. Test it before wiring up buttons

Developer tools, Actions, run `script.send_badge_message` with `target: alice`
and any text. Within a second the badge should chime, blink, come to the
foreground and show the message with the time it was sent.
`sensor.badge_alice_status` should read `waiting`. Tap **Ontvangen** and it
should read `confirmed`, with the other badges untouched at `neutral`.

If the message never arrives, publish to the topic directly from Developer
tools, Actions, `mqtt.publish` with topic `home/badges/alice/msg`. That separates
"the script is wrong" from "the badge is not listening".

## How the status works

Each badge gets a template sensor with three states. Sending stamps the badge's
`input_datetime`, so the sensor reads `waiting`. The badge publishes to the ack
topic when the button is tapped, which stamps the ack sensor, so it reads
`confirmed`. Half an hour later both fall back to `neutral`.

There is deliberately no automation and no notification. A template containing
`now()` is re-rendered every minute, so the fall back happens by itself, with no
timer to survive a restart and nothing arriving on your phone at dinner time.

**Keep the timeout in step.** The 1800 seconds in `04-status-sensors.yaml` and
the timeout on the badge are separate settings for the same idea. Different
values mean a badge still blinking at a dashboard that has gone grey.

## When it does not work

**`geen verbinding` on the badge.** Open the gear button, then Verbinding: it
says why. `login geweigerd` is a wrong or missing broker user.
`geen antwoord van de broker` is a wrong address, a wrong port, or a broker that
is not running.

**The connection drops every few seconds, but the WiFi is fine.** Almost always
two clients using the same MQTT client id: a broker evicts the older of the two,
so they take turns kicking each other off, forever, and it looks exactly like a
flaky network. This app derives the id from the badge's MAC for that reason, so
if you see this, look for something else on your network using a fixed client
id. Check the badge's own view first: signal strength and connection failures
are different layers, and treating one as the other wastes an evening.

**Messages arrive but the dashboard stays grey.** The status sensors are
template sensors; reload templates or restart. `sensor.badge_<name>_status`
should exist under Developer tools, States.

**The dashboard goes red and never green.** The badge acknowledges to
`home/badges/<name>/ack` and Home Assistant listens on exactly that. A mismatch
between the name typed on the badge and the name in your YAML gives precisely
this: messages arrive, answers vanish.

**Nothing arrives after a rename.** The badge resubscribes on the spot, but Home
Assistant is still publishing to the old topic. Update the YAML too.
