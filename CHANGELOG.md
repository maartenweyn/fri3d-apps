# Changelog

## Pomodoro

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
