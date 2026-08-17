# MicroPythonOS notes

Working notes distilled from https://docs.micropythonos.com and
https://fri3dcamp.github.io/badge_2026/. Kept here so we do not have to look
the same things up every session.

## App layout

An installed app is one folder under `/apps/` named after its app id:

    be.fri3d.pomodoro/
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
    mpremote fs cp -r be.fri3d.pomodoro/ :/apps/
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
2. **The default audio output is the headset, not the buzzer.** Registered
   outputs are `Headset+Communicator`, `Badge Buzzer` (kind `buzzer`),
   `Headset` and `Communicator`; inputs are a headset ADC mic and a
   communicator I2S mic. Pick the buzzer explicitly:

       buzzer = next(o for o in AudioManager.get_outputs()
                     if getattr(o, "kind", None) == "buzzer")
       AudioManager.rtttl_player(tune, stream_type=AudioManager.STREAM_ALARM,
                                 output=buzzer).start()
