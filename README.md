# fri3d-apps

Apps for the [Fri3d Camp](https://fri3d.be) badge, which runs
[MicroPythonOS](https://micropythonos.com) on an ESP32-S3.

Everything here is developed and tested against the **Fri3d 2026 badge**
(hardware id `fri3d_2026`, 320x240 touchscreen, MicroPython 1.27).

## Apps

### Pomodoro — `be.fri3d.pomodoro`

A focus timer on your badge. Work, break, work, break, and a longer break every
fourth round.

Built for a badge sitting on a desk, which shapes most of the design.

- **A countdown you can read from across the room.** Seven-segment digits drawn
  with LVGL rectangles, filling most of the screen. The largest font compiled
  into this firmware is `montserrat_28`, far too small at desk distance, so the
  digits are drawn rather than typeset.
- **LEDs that run out like sand.** All five lit at the start of a phase, one
  fewer as each fifth passes, and the last one breathing so you feel the end
  approaching. You read it out of the corner of your eye without looking away
  from what you are doing.
- **Red means focus, green means break.** That is also the signal to anyone
  walking up to your desk about whether they are interrupting.
- **A paused timer is visibly paused**, one breathing amber LED, rather than
  indistinguishable from switched off.
- **Three distinct chimes.** Rising when you are freed, falling when you are
  called back, and its own tone for the end of a long break, so you know what
  happened without looking.
- **Configurable durations**, plus LED brightness and chime volume, because a
  device at arm's length needs different levels than one on a lanyard. Settings
  survive a reboot.
- **A daily counter.** How many pomodoros you finished today, reset at midnight.
- **The S button starts and pauses**, regardless of where the focus is, so you
  can reach over and hit it without looking away from your work.
- **Touch and keys.** On-screen buttons, and the same buttons reachable with the
  badge's d-pad because they sit in the default LVGL focus group.
- **Auto-start**, off by default, to chain phases without touching the badge.

| Control | What it does |
| --- | --- |
| **S button** | Start or pause, wherever the focus is |
| Start / Pause | Run or hold the current phase |
| Reset | Back to the full length of the current phase |
| Skip | Jump to the next phase without an alert |
| Gear | Durations, rounds, sound, LEDs, auto-start |

The phase colour carries through the title, the digits, the progress bar and
the LEDs: red for focus, green for a short break, blue for a long one.

Known limitation: the timer only runs while the app is in the foreground.
Switch to another app and it stops. Moving it into a MicroPythonOS Service is
the next piece of work.

### Berichtjes — `be.weyn.dinerbadge`

Two badges in two bedrooms. Home Assistant sends "Eten over 10 minuten" from a
dashboard button, both badges chime and light up, and one tap sends back a
confirmation. If nobody confirms within three minutes, Home Assistant says so on
your phone.

- **A background service, not a screen.** The MQTT connection lives in a
  `boot_completed` Service, so a message arrives while the child is playing a
  game. The service posts a notification, lights the LEDs and pulls the screen
  to the front.
- **The same message twice is two messages.** Comparing incoming text with the
  last one is the obvious way to avoid duplicates and it swallows exactly the
  message you care about, so messages carry a sequence number instead.
- **The name is typed on the badge.** Both badges run an identical copy of the
  app. Behind the gear button you type which one this is, on the OS keyboard,
  and the service resubscribes to that badge's topic on the spot. No editing a
  file and reinstalling for the second badge, and no list to extend when a third
  one shows up. What you type is folded to something a topic accepts, so a
  stray capital or space cannot point the badge at a topic nobody publishes to.
- **LEDs blink until someone answers**, then stop after half an hour. A light
  flashing in a bedroom all night is worse than a message nobody answered, so
  the nagging gives up while the message stays on screen and stays
  acknowledgeable. Both the blinking and the timeout are set on the badge.
- **Shows when it was sent.** "Eten over 10 minuten" only means something if
  you know when those ten minutes started. The badge's clock is UTC even with
  the timezone set, so the time is converted properly, and a badge that never
  reached an NTP server shows no time rather than a wrong one.
- **Honest about the link.** The screen shows "geen verbinding" when the service
  is not connected, and an acknowledgement that failed to publish says so
  instead of showing a green tick.
- **Backs off out of range.** A failed connection retries after 2 seconds, then
  4, up to a minute, rather than hammering the radio every second in a bedroom
  with no WiFi.

Home Assistant publishes to `home/badges/<name>/msg` and the badge answers on
`home/badges/<name>/ack`. On the dashboard each badge gets a status that goes red
when you send and green when the child answers, and back to grey after half an
hour. All of it, as YAML you can paste, is in
[docs/berichtjes-homeassistant/](docs/berichtjes-homeassistant/).

#### Setting up a badge

`umqtt.simple` turns out to be in the firmware already, so there is nothing to
install. Create the per-badge config, which is gitignored because it holds the
broker password:

    cp be.weyn.dinerbadge/dinerbadge_config.example.py \
       be.weyn.dinerbadge/dinerbadge_config.py
    # set the broker address and the broker credentials
    ./badge.sh reinstall be.weyn.dinerbadge
    ./badge.sh reset          # the service starts at boot, so reboot once

The same copy goes on every badge. Which badge is which is typed on the badge
itself, behind the gear button, and has to match a topic Home Assistant
publishes to.

The Home Assistant side is in
[docs/berichtjes-homeassistant/](docs/berichtjes-homeassistant/): the script that
publishes, the sensors that timestamp the acknowledgements, the reminder
automations and a dashboard card, with a README on where each piece goes.

## Installing an app

**With the [Fri3d-IDE](https://fri3dcamp.github.io/Fri3d-IDE/)**, which is what
most people use. Build the package first:

    ./tools/pack_mpk.sh be.fri3d.pomodoro

That writes `dist/be.fri3d.pomodoro_0.1.0.mpk`. In the IDE, connect the badge
and choose *Install MPK*.

**Over USB with mpremote**, which is faster while developing. With no app named
it installs every app in the repo, since nothing here is more default than
anything else:

    ./badge.sh install                      # all of them
    ./badge.sh install be.weyn.dinerbadge   # just one

**From BadgeHub**, once published: search for the app in the badge's App Store.

## Working on an app

`badge.sh` wraps `mpremote`. Install it once with `pipx install mpremote` or
`pip3 install --user mpremote`.

    ./badge.sh probe            # screen, fonts, inputs, LEDs, audio, build
    ./badge.sh apps             # the app folders in this repo
    ./badge.sh list             # installed and built-in apps
    ./badge.sh install [app..]  # copy to /apps and refresh the launcher
    ./badge.sh reinstall [app..] # remove from the badge first, then copy
    ./badge.sh uninstall <app>  # remove one app
    ./badge.sh wipe             # remove every user-installed app
    ./badge.sh diag [app..]     # why it will not load, with real tracebacks
    ./badge.sh refresh          # rescan /apps
    ./badge.sh reset            # reboot
    ./badge.sh run <file.py>    # run a local script on the badge
    ./badge.sh repl             # MicroPython REPL, ctrl-] to quit

A serial port takes one client at a time, so close the Fri3d-IDE tab before
running these.

`./badge.sh diag` is the one worth knowing about. It lists the installed files,
parses the manifest, reports which `mpos` frameworks and LVGL symbols actually
exist on your firmware, then imports and constructs each activity and prints the
traceback for whatever breaks first. Most load failures are a documented import
that does not exist on this build, and that is what surfaces them.

### Tests without a badge

The timer logic runs on desktop Python against stubs for `lvgl` and `mpos`:

    python3 tests/test_pomodoro.py
    python3 tests/test_dinerbadge.py

67 checks covering the phase cycle, pause and resume timing, the day rollover,
clamping in the settings screen, LED cleanup on exit, that the LED hourglass
only ever empties, that a paused timer shows amber, and that chimes are routed
to the buzzer rather than the headset. The stubs deliberately mirror the quirks
of the real firmware, so the fallback paths are what gets exercised.

### Letting an agent drive the badge

`tools/mcp/` is an MCP server that exposes the badge over USB, so a coding agent
can install, run and debug on real hardware instead of asking you to paste
terminal output back to it. Run `./tools/mcp/setup.sh` and see
[tools/mcp/README.md](tools/mcp/README.md).

## This firmware is not quite the documented one

The MicroPythonOS documentation describes a build that differs from the one
shipped on the Fri3d 2026 badge. Four differences bit us, all the same shape: a
documented import or symbol simply is not there.

1. `from mpos import LightsManager` raises. It lives in `mpos.lights`.
2. `import mpos.config` raises. `SharedPreferences` is exported from `mpos`.
3. `lv.ANIM` does not exist. Resolve LVGL constants across several spellings.
4. The default audio output is the headset, so a chime you expect from the
   buzzer goes to the headphone jack instead.

[`docs/micropythonos-notes.md`](docs/micropythonos-notes.md) has the measured
hardware facts and the working API notes. Check `dir()` on the device before
trusting a documented import path.

## Layout

    be.fri3d.pomodoro/     an app, in a folder named after its app id
    be.weyn.dinerbadge/    idem; its dinerbadge_config.py is untracked
    badge.sh               mpremote wrapper
    tools/                 scripts that run on the badge, plus the packager
    tools/mcp/             MCP server exposing the badge over USB
    tests/                 lvgl and mpos stubs, offline tests
    docs/                  notes on MicroPythonOS and this badge,
                           plus the Home Assistant side of Berichtjes
    dist/                  built .mpk files, not tracked

Most badge apps live in their own repository, one app each. This one keeps the
apps together because `badge.sh`, the stubs and the hardware notes are shared,
and duplicating them across repositories costs more than it saves. Each app is a
self-contained folder named after its app id, so any of them can be lifted into
its own repository later without touching the code.

## Licence

MIT. See [LICENSE](LICENSE).
