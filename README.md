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
- **Touch and keys.** On-screen buttons, and the same buttons reachable with the
  badge's d-pad because they sit in the default LVGL focus group.
- **Auto-start**, off by default, to chain phases without touching the badge.

| Control | What it does |
| --- | --- |
| Start / Pause | Run or hold the current phase |
| Reset | Back to the full length of the current phase |
| Skip | Jump to the next phase without an alert |
| Gear | Durations, rounds, sound, LEDs, auto-start |

The phase colour carries through the title, the digits, the progress bar and
the LEDs: red for focus, green for a short break, blue for a long one.

Known limitation: the timer only runs while the app is in the foreground.
Switch to another app and it stops. Moving it into a MicroPythonOS Service is
the next piece of work.

## Installing an app

**With the [Fri3d-IDE](https://fri3dcamp.github.io/Fri3d-IDE/)**, which is what
most people use. Build the package first:

    ./tools/pack_mpk.sh be.fri3d.pomodoro

That writes `dist/be.fri3d.pomodoro_0.1.0.mpk`. In the IDE, connect the badge
and choose *Install MPK*.

**Over USB with mpremote**, which is faster while developing:

    ./badge.sh install

**From BadgeHub**, once published: search for the app in the badge's App Store.

## Working on an app

`badge.sh` wraps `mpremote`. Install it once with `pipx install mpremote` or
`pip3 install --user mpremote`.

    ./badge.sh probe            # screen, fonts, inputs, LEDs, audio, build
    ./badge.sh list             # installed and built-in apps
    ./badge.sh install [app]    # copy to /apps and refresh the launcher
    ./badge.sh reinstall [app]  # remove from the badge first, then copy
    ./badge.sh uninstall <app>  # remove one app
    ./badge.sh wipe             # remove every user-installed app
    ./badge.sh diag [app]       # why it will not load, with real tracebacks
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

44 checks covering the phase cycle, pause and resume timing, the day rollover,
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
    badge.sh               mpremote wrapper
    tools/                 scripts that run on the badge, plus the packager
    tools/mcp/             MCP server exposing the badge over USB
    tests/                 lvgl and mpos stubs, offline tests
    docs/                  notes on MicroPythonOS and this badge
    dist/                  built .mpk files, not tracked

Most badge apps live in their own repository, one app each. This one keeps the
apps together because `badge.sh`, the stubs and the hardware notes are shared,
and duplicating them across repositories costs more than it saves. Each app is a
self-contained folder named after its app id, so any of them can be lifted into
its own repository later without touching the code.

## Licence

MIT. See [LICENSE](LICENSE).
