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
