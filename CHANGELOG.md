# Changelog

## Berichtjes

### 0.4.0

The badge reports its own battery, and says so to Home Assistant itself.

Charge, voltage and WiFi signal go out every five minutes as one retained JSON
message on `home/badges/<name>/state`. The badge also publishes MQTT discovery
for the three sensors, so they appear under Settings, Devices as a Fri3d 2026
badge with no YAML written for them.

Discovery is keyed on the MAC rather than the name. Keying it on the name would
strand the old entity on every rename and start a new one from zero, which is
exactly the mistake the client id already taught us. Renaming a badge now
rewrites the existing config, clears the retained state left behind on the old
topic, and keeps the history.

Availability is a real last will, registered before connecting: a badge that
runs flat or walks out of range is marked unavailable by the broker rather than
showing yesterday's battery percentage forever. A clean shutdown publishes
`offline` itself, since the broker does not send a will for one.

Every telemetry field is optional. A badge on USB with no cell in it still
reports its signal strength, an ADC that raises does not stop a message from
arriving, and a badge that can measure nothing publishes nothing rather than an
empty object.

345 offline checks, including a fake ADC that is missing, broken, or fine.
Verified against the real Home Assistant: the three sensors appeared by
themselves, reading 100%, 4.20 V and -54 dBm.

Also: the README and the setup guide now have screenshots.

### 0.3.1

Fixed a connection that fell over every few seconds, which looked exactly like
a flaky network and was not one.

The MQTT client id was `badge_<name>`. Two badges briefly carrying the same
name is not hypothetical: it is what happens while you set the second one up.
A broker evicts the older of two clients claiming one id, so the two took turns
kicking each other off, forever. Measured on the badge: WiFi solid at -54 dBm
with an unchanged lease, and 45 failed connects in 75 seconds, every one of them
`OSError(-1)`. The id now carries six hex digits of the MAC, so it is unique per
device and survives both a rename and a reflash, while keeping the name in there
for whoever reads the broker log. Afterwards: zero failures in 90 seconds.

`onStart` is also idempotent now and a new service instance retires the old one.
The same badge was running two loops against one client, which is the same fight
in miniature: the loop ticked at 3.5 times a second where one loop gives 2.

An acknowledgement that cannot be published is held and sent when the link
returns, rather than lost. A bedroom at the edge of the WiFi is exactly where a
child presses the button and the publish fails, and losing it meant Home
Assistant showed red for half an hour for a message that had been read. The
screen says "Bevestigd, nog niet verzonden" until it goes out, then changes to
"Bevestigd" by itself.

331 offline checks. Verified end to end against the real broker and Home
Assistant: a dashboard call reaches the badge, the badge shows it with the send
time, one tap puts the acknowledgement back, and `sensor.badge_<naam>_status`
goes from `wacht` to `bevestigd` while the other badge stays `neutraal`.

### 0.3.0

Nothing sensitive has to live in a file any more. The broker address, port, user
and password are set on the badge, behind the gear button under
"Verbinding...", and stored in SharedPreferences alongside the name. A fresh
badge can be set up entirely on the badge, and `dinerbadge_config.py` is down to
starting values for a badge nobody has touched yet, which may be empty.

The password is never shown. Editing it starts from an empty field and an empty
result keeps what is stored, so a child reading over a shoulder learns nothing
and the value cannot be wiped by accident.

Its own screen rather than four more rows, because the settings screen cannot
scroll and four rows is what fits: 16 for the title plus four rows of 44 and
their gaps leaves 8 pixels spare of 224. A fifth row would have fallen off the
bottom and been unreachable, so a test now guards that arithmetic.

The connection screen shows what the service is actually doing, and keeps
showing it: someone standing there has just typed an address and is waiting to
see whether it took. It also says what went wrong in words. "geen verbinding:
-1" was the old text, which tells nobody which of the four fields to look at;
CONNACK 5 now reads "login geweigerd", because a broker that knows who you claim
to be and refuses is a different problem from a wrong address.

314 offline checks. Verified on hardware: both screens fit with room to spare,
the password shows as "ingesteld", and the status line went from "geen antwoord
van de broker" to "verbonden met <broker>" on its own while the screen
stayed open.

### 0.2.0

The name is no longer baked into a file per badge. Both badges run an identical
copy of the app and you type which one this is behind the gear button, on the
OS keyboard through `InputActivity`, stored in SharedPreferences. Typed rather
than chosen from a list, so a third badge needs no code change. What you type is
lowercased and stripped of anything a topic cannot carry: a stray capital or a
trailing space would point the badge at a topic nobody publishes to, and then
nothing arrives and nothing complains. Changing it drops the MQTT
connection and resubscribes on the spot: a client stays subscribed to what it
asked for, so without that the badge would sit there connected and deaf.

The settings screen was then unusable with a finger, which driving it by sending
events had not revealed. The name was a 60 by 24 chip at the right edge of a
scrollable container, and on a scrollable container LVGL turns a press that
drifts a few pixels into a scroll and cancels the click, so the button read as
dead. The rows measure 168 pixels on a 240 high screen, so there was nothing to
scroll in the first place: scrolling is off now, the name is a full-width 44 high
button reading "Deze badge: <name>", the stepper and the switch are
finger-sized, and the gear on the main screen grew to 56 by 50.

The LEDs blink while a message is unacknowledged instead of sitting on, and give
up after half an hour. A light flashing in a bedroom all night is worse than a
message nobody answered, so the nagging stops while the message stays on screen
and stays acknowledgeable. Both the blinking and the timeout are set on the
badge.

The Home Assistant side dropped the phone notification. Each badge now has a
status sensor with three states that the dashboard colours grey, red and green:
red the moment something is sent, green when the child answers, grey again after
half an hour. Sending to both turns both rows red and they go green
independently. It is a template sensor rather than an automation because a
template containing `now()` is re-rendered every minute, so the fall back to
neutral happens by itself, with no timer to survive a restart.

225 offline checks. Verified on hardware: the blink alternates on every one of
fourteen measured transitions, stops on the timeout with the message still
showing, and a rename reaches the new topic without a reboot.

### 0.1.0

First release. Home Assistant sends a short message to a badge over MQTT, the
badge chimes, lights up and shows it, and the child taps once to confirm.

- A `boot_completed` Service holds the MQTT connection, so messages arrive
  whatever app is on screen. On a message it posts a Notification, lights the
  LEDs amber and calls `AppManager.start_app()` to pull the screen forward.
- Messages are identified by a sequence number rather than by their text.
  Comparing texts would have swallowed the second "Eten over 10 minuten" of the
  evening, which is the one that matters.
- Connection failures back off from 2 to 60 seconds instead of retrying every
  second, and the badge pings every 20 seconds so a quiet client is not dropped
  by the broker's 60 second keepalive.
- The screen says "geen verbinding" when the service is not connected, and an
  acknowledgement that could not be published reads "Bevestigd, niet verzonden"
  rather than showing a green tick nobody in the kitchen will see.
- The screen shows when the message was sent, because "Eten over 10 minuten" is
  only useful if you know when those ten minutes started. The badge keeps its
  clock in UTC and `time.localtime()` stays UTC even with the timezone
  preference set to Europe/Brussels, so the time is converted through the
  POSIX zone the badge is set to. An unsynced clock shows no time at all
  rather than a confident wrong one.
- Per-badge settings live in `dinerbadge_config.py`, which is gitignored because
  it holds the MQTT password. Copy `dinerbadge_config.example.py` and set
  `CHILD_NAME`.

149 offline checks in `tests/test_dinerbadge.py`, against a fake broker that
drops the link the way a real one does, covering the sequence rule, the backoff,
the keepalive, both umqtt.simple signatures, a missing umqtt.simple, and the
screen's states.

Verified on hardware, which found two things the desktop suite could not:

- `str.capitalize()` does not exist in MicroPython. Sixteen CPython string
  methods are missing on this build and the stubs run on real CPython, so the
  call passed every desktop check and raised `AttributeError` in `onCreate` on
  the badge. The suite now greps the app source for all sixteen names.
- The label wrap constant is `lv.label.LONG_MODE.WRAP`. Neither `lv.LABEL_LONG`
  nor `lv.LABEL_LONG_WRAP` exists, so the defensive lookup was resolving to
  None and quietly skipping `set_long_mode`, which would have run a long message
  off the side of the screen.

Also measured: `umqtt.simple` is already in the firmware but its `MQTTClient`
takes no `socket_timeout`, so the TypeError fallback is the path that actually
runs. See `docs/micropythonos-notes.md`.

Full round trip confirmed against the real Mosquitto broker: a publish to
`home/badges/<name>/msg` reaches the badge, pulls the app forward and reads
"gestuurd om 16:04", and one tap puts the message text back on
`home/badges/<name>/ack`.

## Pomodoro

### 0.3.1

Fixed the LEDs flashing at random and showing the wrong phase colour on a
badge that had been running for a while.

`time.ticks_ms()` is modular, not a plain counter, and `ticks_diff` returns a
signed value within half a period. Comparing against a zero sentinel therefore
flips sign once the device has been up past that halfway point, which made the
phase-change flash trigger on its own. Three places did this: the flash
deadline, the LED update throttle and the button debounce. All three now use
`None` and measure elapsed time forwards.

The test stubs implement the same modular arithmetic and the suite runs at four
clock positions, including just under the wrap, so this class of bug fails on a
desktop instead of only on hardware.

### 0.3.0

The badge's S button starts and pauses the timer. It works wherever the focus
happens to be, which is the point: it is the one control you can hit without
looking at the screen.

On the Fri3d 2026 the button is GPIO0, exposed by the board module as
`btn_start` and reading 0 while held. The app polls it in the frame callback
with a 300 ms debounce, goes through `mpos.board` rather than claiming
`machine.Pin(0)` so the pin stays shared with the firmware, and quietly stops
polling if reading it ever fails.

### 0.2.1

- The LEDs go dark while the settings are open, instead of animating through
  the change, which looked like a fault.
- Fixed the frame callback outliving the activity. In MicroPython, reading
  `self.update_frame` produces a new bound method every time, so unregistering
  it removed nothing and the LEDs kept animating behind the settings screen.
  The activity now holds one callback object for its lifetime.
- Each LED covers one fifth of the configured phase, rounded up, so a five
  minute focus and a ninety minute one both start with the full strip. Before,
  the lit count was rounded down, which dropped an LED as soon as the phase
  started.
- Shortening a phase while it runs caps the countdown to the new length.
  Previously the remaining time could exceed the phase, which asked for more
  LEDs than the badge has.

### 0.2.0

Reworked for a badge that sits on a desk rather than hanging on a lanyard.

- The countdown is drawn as seven-segment digits filling most of the screen,
  readable from across the room. This also sidesteps the largest built-in font
  being `montserrat_28`, which was too small to read at desk distance.
- The five LEDs now run out like sand: all lit at the start of a phase, one
  fewer as each fifth passes, and the last one breathes so the end is felt
  coming. Red for focus and green for a break, which doubles as a signal to
  anyone approaching the desk.
- A paused timer shows a single breathing amber LED, so paused no longer looks
  the same as switched off.
- LED brightness is configurable and defaults to 10 percent, because five RGB
  LEDs at arm's length are unpleasant at full power.
- Three distinct chimes instead of two: end of focus rises, end of a short
  break falls, and the end of a long break has its own. All shortened, with a
  configurable volume.
- The phase-change flash is two seconds rather than four.

### 0.1.0

First release. Focus and break phases with configurable durations, LED and
buzzer alerts at every phase change, a counter of the sessions finished today,
and control by both touch and the badge keys.

Adapted to the Fri3d 2026 firmware, which differs from the MicroPythonOS
documentation in several places: `LightsManager` lives in `mpos.lights`,
`SharedPreferences` is exported from `mpos` rather than `mpos.config`,
`lv.ANIM` does not exist, and the default audio output is the headset rather
than the badge buzzer. See `docs/micropythonos-notes.md`.
