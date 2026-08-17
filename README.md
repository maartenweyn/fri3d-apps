# fri3d-apps

Apps for the Fri3d Camp badge, which runs MicroPythonOS on an ESP32-S3.

## Apps

- `be.fri3d.pomodoro/` — Pomodoro focus timer. Configurable focus and break
  lengths, LED and buzzer alerts at each phase change, and a counter of the
  sessions finished today.

## Working with the badge

Everything goes through `mpremote` over USB. Install it once:

    pipx install mpremote        # or: pip3 install --user mpremote

Then use the helper script:

    ./badge.sh probe            # report screen size, LEDs, audio, inputs
    ./badge.sh list             # list installed and built-in apps
    ./badge.sh wipe             # remove ALL user-installed apps from /apps
    ./badge.sh install          # copy be.fri3d.pomodoro to the badge
    ./badge.sh reinstall        # remove it from the badge first, then copy
    ./badge.sh uninstall <id>   # remove one app
    ./badge.sh refresh          # rescan /apps so the launcher sees new apps
    ./badge.sh reset            # reboot the badge
    ./badge.sh run <file.py>    # run a local script on the badge
    ./badge.sh repl             # MicroPython REPL, ctrl-] to quit

Close the Fri3d-IDE browser tab before running these: a serial port can only
be opened by one program at a time.

`wipe` only clears `/apps`. Built-in apps live in the read-only `/builtin`
and can only be changed by rebuilding the firmware.

`install` and `reinstall` refresh the launcher themselves. If a new app still
does not show up, `./badge.sh reset` reboots the badge, and app discovery also
runs at boot. To skip the launcher entirely, start the app from the REPL:

    from mpos import AppManager
    AppManager.start_app('be.fri3d.pomodoro')

## Layout

    be.fri3d.pomodoro/     the app as it is installed into /apps
    tools/                 scripts that run on the badge
    docs/                  notes on the MicroPythonOS API
    badge.sh               mpremote wrapper

## Tests

The timer logic runs on a normal desktop Python against stubs for `lvgl`
and `mpos`, so it can be checked without a badge attached:

    python3 tests/test_pomodoro.py
