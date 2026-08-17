# Changelog

## Pomodoro

### 0.1.0

First release. Focus and break phases with configurable durations, LED and
buzzer alerts at every phase change, a counter of the sessions finished today,
and control by both touch and the badge keys.

Adapted to the Fri3d 2026 firmware, which differs from the MicroPythonOS
documentation in several places: `LightsManager` lives in `mpos.lights`,
`SharedPreferences` is exported from `mpos` rather than `mpos.config`,
`lv.ANIM` does not exist, and the default audio output is the headset rather
than the badge buzzer. See `docs/micropythonos-notes.md`.
