# MicroPythonOS notes

Working notes distilled from https://docs.micropythonos.com and
https://fri3dcamp.github.io/badge_2026/. Kept here so we do not have to look
the same things up every session.

## App layout

An installed app is one folder under `/apps/` named after its app id:

    tech.weyn.pomodoro/
    ├── MANIFEST.JSON
    ├── icon_64x64.png
    └── pomodoro.py

Each subdirectory costs about 8 KiB in LittleFS, so keep the layout flat.
Package names used as Python modules must not contain dots.

`MANIFEST.JSON` needs `name`, `publisher`, `fullname`, `version`,
`categories` (a list), and an `activities` array. An activity that should
appear in the launcher declares
`"intent_filters": [{"action": "main", "category": "launcher"}]`.
Apps may also declare `services` with `{"action": "boot_completed"}` to run
at startup without a UI.

## Filesystem

- `/apps` user-installed apps, removed on uninstall
- `/builtin` read-only, compiled into the firmware, holds the built-in apps
- `/prefs` per-app SharedPreferences
- `/cache` per-app scratch, may be deleted to reclaim space
- `/data` app-independent content
- `/lib` the `mpos` and `ui` frameworks
- `/sdcard` optional micro SD mount

## Activity lifecycle

Android-inspired: `onCreate` → `onStart(screen)` → `onResume(screen)` →
`onPause(screen)` → `onStop(screen)` → `onDestroy(screen)`, plus
`onBackPressed(screen)` (return True to consume and call `finish()` later).

- build the UI in `onCreate` and end with `setContentView(screen)`
- always call `super().onResume(screen)` / `super().onPause(screen)`
- register callbacks in `onResume`, unregister in `onPause`
- navigate with `startActivity(Intent(activity_class=X))`, get results with
  `startActivityForResult(intent, cb)` plus `setResult(...)` and `finish()`

## Frameworks (import from `mpos` directly)

- `SharedPreferences` — instance based, via `mpos.config.SharedPreferences(app_id)`.
  Read with `get_string/get_int/get_dict/get_list`, write with
  `prefs.edit().put_int(k, v).commit()` (or `apply()`).
- `LightsManager` — NeoPixel RGB LEDs. `is_available()`, `get_led_count()`,
  `set_led(i, r, g, b)`, `set_all(r, g, b)`, `clear()`, and `write()` to push.
  Buffered: nothing shows until `write()`. Clear them in `onPause`.
- `AudioManager` — `rtttl_player(rtttl, stream_type=...)` for buzzer tones,
  `player(file_path=...)` for WAV. Stream priority ALARM > NOTIFICATION > MUSIC.
  Fri3d 2026 badge: I2S out, ADC mic, buzzer. No I2S mic.
- `InputManager` — `has_pointer()`, `has_indev_type(lv.INDEV_TYPE.KEYPAD)`,
  `pointer_xy()`, and navigation gating via `set_back_screen_disabled(True, cb=...)`
  and `set_drawer_open_disabled(True, cb=...)`.
- `TaskManager` — `create_task(coro)`, `sleep(seconds)`. Asyncio runs on the
  LVGL thread, so UI updates from coroutines are safe.
- `AppManager` — `start_app(app_id)`, install/uninstall of `.mpk` packages.
- Per-frame work: `mpos.ui.task_handler.add_event_cb(fn, 1)` in `onResume`
  and `remove_event_cb(fn)` in `onPause`. The callback takes `(a, b)`.

## Hardware buttons

Add widgets to the default LVGL group and the badge keys drive them:

    group = lv.group_get_default()
    if group:
        group.add_obj(button)

For raw keys, attach `lv.EVENT.KEY` to a container, as the QuasiNametag app
does. `mpos.ui.focus_direction` helps with directional focus movement.

## Deployment

    mpremote mkdir :/apps
    mpremote fs cp -r tech.weyn.pomodoro/ :/apps/
    mpremote run tools/probe.py
    mpremote repl

Or use `./badge.sh` in this repo.

## Fri3d 2026 badge, measured 2026-08-17

From `./badge.sh probe` on the actual device:

- MicroPython 1.27.0, `ESP32_GENERIC_S3-SPIRAM_OCT`, hardware id `fri3d_2026`
- screen 320 x 240, touch (CST816S) **and** a keypad indev (Fri3d2026Expander),
  so widgets in the default focus group are driven by both
- largest font compiled in is `font_montserrat_28`; also 8/10/12/14/16/18/20/24
  and `font_unscii_8/16`. Do not reach for 32 or 48, they are not there.
- ~5.8 MB free RAM, ~2.1 MiB free of a 7 MiB filesystem
- root also holds `retro-go`, `roms` and `romart` next to the MicroPythonOS dirs
- built-in apps: about, appstore, file_manager, howto, launcher, osupdate,
  settings (+ audio, hotspot, webserver, wifi)

Two things the general docs get wrong for this build:

1. **`from mpos import LightsManager` raises ImportError.** `LightsManager` is
   not in the `mpos` exports on this firmware. Use `mpos.lights` instead and
   fall back across both shapes.
2. **`import mpos.config` raises ImportError.** The docs show
   `mpos.config.SharedPreferences(app_id)`, but on this firmware there is no
   `mpos.config` module: `SharedPreferences` is exported from `mpos` itself.
   Import it as `from mpos import SharedPreferences`.
3. **The default audio output is the headset, not the buzzer.** Registered
   outputs are `Headset+Communicator`, `Badge Buzzer` (kind `buzzer`),
   `Headset` and `Communicator`; inputs are a headset ADC mic and a
   communicator I2S mic. Pick the buzzer explicitly:

       buzzer = next(o for o in AudioManager.get_outputs()
                     if getattr(o, "kind", None) == "buzzer")
       AudioManager.rtttl_player(tune, stream_type=AudioManager.STREAM_ALARM,
                                 output=buzzer).start()

## More divergences, measured 2026-08-17 while building Berichtjes

The firmware moved since the notes above were written, and three more documented
paths turned out to be spelled differently. Same lesson: `dir()` first.

5. **`from mpos import LightsManager` now works.** It is in the `mpos` exports on
   this build, alongside `Service`, `NotificationManager`, `Notification`,
   `Intent`, `AppManager` and `TaskManager`. `mpos.lights` still exists too, so
   code that resolves across both keeps working. `mpos.config` is still missing.

6. **The label wrap constant is `lv.label.LONG_MODE.WRAP`.** Neither
   `lv.LABEL_LONG` nor `lv.LABEL_LONG_WRAP` exists. Get this wrong and
   `set_long_mode` is silently skipped, so a long message runs off the side of
   the screen instead of wrapping. `LONG_MODE` offers CLIP, DOTS, SCROLL,
   SCROLL_CIRCULAR and WRAP; WRAP is 0. `lv.TEXT_ALIGN` exists,
   `lv.TEXT_ALIGN_CENTER` does not.

7. **`umqtt.simple` is already installed**, no `mip.install` needed, but its
   `MQTTClient` takes **no `socket_timeout` argument**. Passing it raises
   TypeError, so try the modern signature and fall back to the old one.

8. **`time.localtime()` returns UTC even with the timezone preference set.**
   Setting Europe/Brussels in the Settings app changes
   `mpos.time.TimeZone.timezone_preference` but not what `time.localtime()`
   answers, so a naive read is an hour or two behind the wall clock. The
   conversion that works:

       import mpos.time as mt
       pref = mt.TimeZone.timezone_preference          # an attribute, not a method
       posix = mt.TimeZone.timezone_to_posix_time_zone(pref)
       parts = mt.localPTZtime.tztime(time.time(), posix)

   `tztime` takes MicroPython's 2000-based epoch and the POSIX string, handles
   DST, and returns a nine-tuple whose last element is the DST flag.
   `mpos.time.localPTZtime` is a submodule reached through `mpos.time`, not
   importable as `mpos.time.localPTZtime` directly.

## Sixteen string methods MicroPython does not have

`dir(str)` on this build lacks all of these, every one of which desktop Python
answers happily:

    capitalize   casefold     expandtabs   format_map
    isdecimal    isidentifier isprintable  ljust
    maketrans    removeprefix removesuffix rjust
    swapcase     title        translate    zfill

`center`, `encode`, `partition` and `rpartition` are present.

This is a class of bug offline tests cannot catch, because the stubs run on real
CPython where the method exists. `str.capitalize()` in Berichtjes passed 78
desktop checks and then raised `AttributeError` in `onCreate` on the badge.
`tests/test_messages.py` now greps the app source for these sixteen names, so
the next one fails on a desktop.

## Badge inputs, measured

`mpos.board` exposes exactly one submodule, named after the hardware id, with
the board wiring. On the Fri3d 2026:

- `btn_start` is `Pin(0)`, the button silkscreened S. It reads 1 at rest and 0
  while held, so poll for a falling edge and debounce.
- `expander` is the CH32X035 over I2C at address 80. `expander.digital` is a
  12-tuple of booleans and `expander.analog` a 5-tuple; the S button is not
  among them, it is a direct GPIO.
- `keypad_read_cb` feeds an LVGL keypad indev, alongside the CST816S touch
  indev. `lv.KEY` on this build offers UP 17, DOWN 18, RIGHT 19, LEFT 20,
  ENTER 10, ESC 27, HOME 2, END 3, NEXT 9, PREV 11, BACKSPACE 8, DEL 127.
- The board module is frozen into the firmware, so there is no source file on
  flash to read. Inspect it with `dir()` over the REPL instead.

## Two traps when testing against a live badge

`time.ticks_ms()` wraps at 2**30 and `ticks_diff(a, b)` returns a signed value
inside half a period. `ticks_diff(0, now)` is therefore *positive* once the
badge has been up for about nine days, or immediately after a wrap. Never
compare a tick value against a zero sentinel: use `None` and measure elapsed
time forwards. Desktop tests only catch this if their shims are modular too.

Two things make REPL experiments lie:

- Imports are cached in `sys.modules`, and the badge is not rebooted between
  `mpremote exec` calls. After reinstalling an app, `sys.modules.pop("yourapp")`
  or you are testing the previous version.
- `Activity.setContentView()` hands the activity to the framework, which starts
  ticking it. Statements in the REPL are interleaved with the asyncio loop, so
  an object you are poking at mutates underneath you. Call whatever unregisters
  your frame callback before measuring anything.
