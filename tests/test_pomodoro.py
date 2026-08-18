"""Offline tests for the Pomodoro app.

Runs on a normal desktop Python against the stubs in tests/stubs/, so the
timer logic can be checked without a badge attached.

    python3 tests/test_pomodoro.py
"""

import os
import sys
import time

sys.dont_write_bytecode = True   # never drop __pycache__ into the app folder

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.join(ROOT, "tech.weyn.pomodoro"))

# --- MicroPython time shims -------------------------------------------------
# ticks_* are modular, not plain integers. ticks_diff returns a signed value
# inside half a period, so comparing against a zero sentinel gives a positive
# answer once the device has been up for a while. Start the clock past the
# halfway point so tests see the same arithmetic a real badge does.
TICKS_PERIOD = 1 << 30
TICKS_HALF = TICKS_PERIOD >> 1
# Overridable so the suite can be run on both sides of the tick wrap:
#   POMODORO_TEST_CLOCK=1000 python3 tests/test_pomodoro.py
CLOCK = {"ms": int(os.environ.get("POMODORO_TEST_CLOCK", 900_000_000))}


def _ticks_ms():
    return CLOCK["ms"] & (TICKS_PERIOD - 1)


def _ticks_diff(a, b):
    delta = (a - b) & (TICKS_PERIOD - 1)
    return delta - TICKS_PERIOD if delta >= TICKS_HALF else delta


def _ticks_add(a, b):
    return (a + b) & (TICKS_PERIOD - 1)


time.ticks_ms = _ticks_ms
time.ticks_diff = _ticks_diff
time.ticks_add = _ticks_add
time.sleep_ms = lambda ms: None

import mpos
from mpos import AudioManager
from mpos.lights import LightsManager
import mpos.config as cfg
import posettings, pomodoro

def advance(app, ms, step=100):
    for _ in range(ms // step):
        CLOCK["ms"] += step
        app.update_frame(None, None)

fails = []
checks = {"n": 0}
def check(cond, msg):
    checks["n"] += 1
    if not cond:
        fails.append(msg)
    print(("  ok  " if cond else "  FAIL") + "  " + msg)

print("=== defaults + first render ===")
app = pomodoro.Pomodoro()
app.onCreate()
app.onResume(app._view)
check(app.phase == pomodoro.WORK, "starts in the focus phase")
check(app.time_text == "25:00", "shows 25:00, got %r" % app.time_text)
check(app.start_lbl.text == "Start", "start button reads Start")
check("Round 1/4" in app.status_label.text, "status shows round 1/4: %r" % app.status_label.text)

print("=== start, tick, pause, resume ===")
app._toggle()
check(app.running and app.start_lbl.text == "Pause", "toggle starts the timer")
advance(app, 61_000)
check(app.time_text == "23:59", "61 s elapsed -> 23:59, got %r" % app.time_text)
app._toggle()
check(not app.running, "second toggle pauses")
before = app.remaining_ms
advance(app, 30_000)
check(app.remaining_ms == before, "clock frozen while paused")
app._toggle()
advance(app, 60_000)
check(app.time_text == "22:59", "resumes from where it stopped, got %r" % app.time_text)

print("=== full cycle: work -> short -> ... -> long ===")
cfg._STORE.clear()
LightsManager.log.clear(); AudioManager.played.clear()
mpos.config.SharedPreferences("tech.weyn.pomodoro").edit().put_int("work_min", 1)\
    .put_int("short_min", 1).put_int("long_min", 1).put_int("rounds", 4)\
    .put_int("sound", 1).put_int("leds", 1).put_int("autostart", 1).commit()
app = pomodoro.Pomodoro()
app.onCreate(); app.onResume(app._view)
check(app.time_text == "01:00", "picks up configured 1 minute, got %r" % app.time_text)
app._toggle()
seen = []
for _ in range(8):
    advance(app, 61_000)
    seen.append(app.phase)
expected = [pomodoro.SHORT, pomodoro.WORK, pomodoro.SHORT, pomodoro.WORK,
            pomodoro.SHORT, pomodoro.WORK, pomodoro.LONG, pomodoro.WORK]
check(seen == expected, "phase order %s" % (seen,))
check(app.done_today == 4, "four pomodoros counted, got %d" % app.done_today)
check(len(AudioManager.played) == 8, "a chime at every transition, got %d" % len(AudioManager.played))
check(len(set(AudioManager.played)) == 3, "three distinct chimes, got %d" % len(set(AudioManager.played)))
check(AudioManager.played[6] == pomodoro.CHIME_END_WORK
      and AudioManager.played[7] == pomodoro.CHIME_END_LONG,
      "the long break ends with its own chime")
check(all(v == 60 for v in AudioManager.volumes), "chime volume passed through: %s" % set(AudioManager.volumes))
check(len(LightsManager.log) > 8, "LEDs were driven (%d writes)" % len(LightsManager.log))
check(pomodoro.LightsManager is LightsManager, "LightsManager resolved via mpos.lights")
check(AudioManager.routed and all(o is not None and o.kind == "buzzer" for o in AudioManager.routed),
      "chimes routed to the buzzer, not the headset: %s" % (AudioManager.routed,))
check(cfg._STORE["tech.weyn.pomodoro"]["done_today"] == 4, "counter persisted")

print("=== autostart off leaves the next phase paused ===")
cfg._STORE.clear()
mpos.config.SharedPreferences("tech.weyn.pomodoro").edit().put_int("work_min", 1)\
    .put_int("autostart", 0).commit()
app = pomodoro.Pomodoro(); app.onCreate(); app.onResume(app._view)
app._toggle(); advance(app, 61_000)
check(app.phase == pomodoro.SHORT and not app.running, "stops at the break when autostart is off")

print("=== skip and reset ===")
app._skip()
check(app.phase == pomodoro.WORK, "skip advances without a chime")
app._toggle(); advance(app, 20_000); app._reset()
check(not app.running and app.remaining_ms == app._phase_ms(), "reset restores the full phase")

print("=== day rollover ===")
cfg._STORE.clear()
mpos.config.SharedPreferences("tech.weyn.pomodoro").edit()\
    .put_string("day", "1999-01-01").put_int("done_today", 7).commit()
app = pomodoro.Pomodoro(); app.onCreate()
check(app.done_today == 0, "counter resets on a new day, got %d" % app.done_today)

print("=== settings screen ===")
cfg._STORE.clear()
s = posettings.PomodoroSettings()
s.onCreate()
check(s.values["work_min"] == 25, "settings load defaults")
s._bump("work_min", 1, 1, 90); s._bump("work_min", 1, 1, 90)
check(s.values["work_min"] == 27 and s.value_labels["work_min"].text == "27", "plus button updates value and label")
for _ in range(200):
    s._bump("work_min", -1, 1, 90)
check(s.values["work_min"] == 1, "clamped at the minimum")
for _ in range(200):
    s._bump("rounds", 1, 2, 8)
check(s.values["rounds"] == 8, "clamped at the maximum")
sw = s.switches["sound"]
sw.state.clear()
s._toggle("sound", sw)
check(s.values["sound"] == 0, "switch off writes 0")
s.onPause(None)
check(cfg._STORE["tech.weyn.pomodoro"]["work_min"] == 1, "settings persisted on leaving")

print("=== settings feed back into the timer ===")
app = pomodoro.Pomodoro(); app.onCreate(); app.onResume(app._view)
check(app.time_text == "01:00", "timer picks up the new 1 minute, got %r" % app.time_text)
app.onPause(app._view)
check(LightsManager.leds == [(0, 0, 0)] * 5, "LEDs cleared on leaving the app")
check(all(cb is not app._frame_cb for cb in pomodoro.mpos.ui.task_handler.cbs),
      "frame callback really unregistered on pause, by identity")

print("=== LEDs behave like an hourglass ===")
cfg._STORE.clear()
LightsManager.reset()
mpos.config.SharedPreferences("tech.weyn.pomodoro").edit().put_int("work_min", 5)\
    .put_int("leds", 1).put_int("brightness", 20).put_int("autostart", 0).commit()
app = pomodoro.Pomodoro(); app.onCreate(); app.onResume(app._view)
app._toggle()
counts = []
for _ in range(5):
    advance(app, 60_000)
    counts.append(LightsManager.lit())
check(counts == sorted(counts, reverse=True) and counts[0] >= counts[-1],
      "lit LEDs only ever decrease: %s" % (counts,))
check(counts[0] >= 4 and counts[-1] == 1,
      "starts nearly full and ends with one lit: %s" % (counts,))
check(max(max(led) for led in LightsManager.leds) <= 255 * 20 // 100 + 1,
      "brightness setting caps the output: %s" % (LightsManager.leds,))
check(all(led[0] > 4 * max(led[1], led[2]) for led in LightsManager.leds if max(led)),
      "focus phase reads as red: %s" % (LightsManager.leds,))

print("=== paused looks different from off ===")
cfg._STORE.clear()
LightsManager.reset()
mpos.config.SharedPreferences("tech.weyn.pomodoro").edit().put_int("work_min", 5)\
    .put_int("leds", 1).put_int("brightness", 40).commit()
app = pomodoro.Pomodoro(); app.onCreate(); app.onResume(app._view)
app._toggle(); advance(app, 60_000); app._toggle()
advance(app, 1_000)
lit = [led for led in LightsManager.leds if max(led) > 0]
check(len(lit) == 1, "exactly one LED marks a paused timer: %s" % (LightsManager.leds,))
check(lit and lit[0][0] > 0 and lit[0][1] > 0 and lit[0][2] == 0,
      "and it is amber, not a phase colour: %s" % (lit,))
app.onPause(app._view)
check(LightsManager.leds == [(0, 0, 0)] * 5, "all LEDs off when leaving the app")

print("=== brightness of zero-ish still produces valid colours ===")
cfg._STORE.clear()
LightsManager.reset()
mpos.config.SharedPreferences("tech.weyn.pomodoro").edit().put_int("work_min", 5)\
    .put_int("leds", 1).put_int("brightness", 1).commit()
app = pomodoro.Pomodoro(); app.onCreate(); app.onResume(app._view)
app._toggle(); advance(app, 5_000)
check(True, "no assertion tripped in the LED stub at brightness 1")

print("=== the clock renders as digits ===")
check(app.time_text.count(":") == 1 and len(app.time_text) == 5,
      "time text is MM:SS, got %r" % app.time_text)
segs = app.clock.digits[0].parts
check(len(segs) == 7, "each digit has seven segments, got %d" % len(segs))
app.clock.set_time("08:15", 0xFFFFFF, True)
check(app.clock.digits[0].value == "0" and app.clock.digits[3].value == "5",
      "digits map to the right characters")

print("=== one LED per fifth of the configured phase, not per five minutes ===")
def lit_after(minutes_total, minutes_elapsed):
    cfg._STORE.clear()
    LightsManager.reset()
    mpos.config.SharedPreferences("tech.weyn.pomodoro").edit()\
        .put_int("work_min", minutes_total).put_int("leds", 1)\
        .put_int("brightness", 40).put_int("autostart", 0).commit()
    a = pomodoro.Pomodoro(); a.onCreate(); a.onResume(a._view)
    a._toggle()
    advance(a, minutes_elapsed * 60_000)
    return LightsManager.lit()

check(lit_after(5, 1) == 4, "5 min phase, 1 min gone -> 4 lit, got %d" % lit_after(5, 1))
check(lit_after(50, 10) == 4, "50 min phase, 10 min gone -> 4 lit, got %d" % lit_after(50, 10))
check(lit_after(50, 5) == 5, "50 min phase, 5 min gone -> still 5 lit, got %d" % lit_after(50, 5))
check(lit_after(90, 18) == 4, "90 min phase, 18 min gone -> 4 lit, got %d" % lit_after(90, 18))

print("=== editing the settings does not animate the LEDs ===")
pomodoro.mpos.ui.task_handler.cbs.clear()   # earlier sections left theirs behind
cfg._STORE.clear()
LightsManager.reset()
mpos.config.SharedPreferences("tech.weyn.pomodoro").edit().put_int("work_min", 25)\
    .put_int("leds", 1).put_int("brightness", 40).commit()
app = pomodoro.Pomodoro(); app.onCreate(); app.onResume(app._view)
app._toggle(); advance(app, 60_000)
check(LightsManager.lit() > 0, "LEDs are on while running")
app._open_settings()
check(LightsManager.leds == [(0, 0, 0)] * 5, "LEDs go dark on entering the settings")
check(pomodoro.mpos.ui.task_handler.cbs == [], "and nothing keeps ticking behind the settings screen")
before = list(LightsManager.leds)
for _ in range(50):
    CLOCK["ms"] += 100
check(LightsManager.leds == before, "and they stay dark while time passes")

print("=== shortening a running phase does not overflow the strip ===")
mpos.config.SharedPreferences("tech.weyn.pomodoro").edit().put_int("work_min", 5).commit()
app.onResume(app._view)
advance(app, 1_000)
check(len(LightsManager.leds) == 5, "still five LEDs")
check(LightsManager.lit() <= 5, "never more lit than exist, got %d" % LightsManager.lit())
check(app.remaining_ms <= 5 * 60_000,
      "the clock is capped to the new phase length: %d ms" % app.remaining_ms)
check(app.running, "and the timer is still running")

print("=== lengthening a running phase keeps the clock ===")
cfg._STORE.clear()
mpos.config.SharedPreferences("tech.weyn.pomodoro").edit().put_int("work_min", 10).commit()
app = pomodoro.Pomodoro(); app.onCreate(); app.onResume(app._view)
app._toggle(); advance(app, 120_000)
left = app.remaining_ms
mpos.config.SharedPreferences("tech.weyn.pomodoro").edit().put_int("work_min", 40).commit()
app.onResume(app._view)
check(abs(app.remaining_ms - left) < 2000,
      "a longer phase leaves the running countdown alone: %d vs %d" % (app.remaining_ms, left))

print("=== the S button starts and pauses ===")
from mpos.board import fri3d_2026 as board
pomodoro.mpos.ui.task_handler.cbs.clear()
cfg._STORE.clear()
LightsManager.reset()
board.btn_start.release()
mpos.config.SharedPreferences("tech.weyn.pomodoro").edit().put_int("work_min", 25)\
    .put_int("leds", 0).commit()
app = pomodoro.Pomodoro(); app.onCreate(); app.onResume(app._view)
check(app._start_pin is board.btn_start, "the app found the badge's S button")
check(not app.running, "starts paused")

def tap(hold_frames=3, gap_frames=10):
    board.btn_start.press()
    for _ in range(hold_frames):
        CLOCK["ms"] += 30
        app.update_frame(None, None)
    board.btn_start.release()
    for _ in range(gap_frames):
        CLOCK["ms"] += 30
        app.update_frame(None, None)

tap()
check(app.running, "one press starts it")
tap()
check(not app.running, "the next press pauses it")
tap()
check(app.running, "and the one after that resumes")

print("=== holding it does not stutter ===")
board.btn_start.press()
states = []
for _ in range(60):
    CLOCK["ms"] += 30
    app.update_frame(None, None)
    states.append(app.running)
board.btn_start.release()
check(len(set(states)) == 1, "holding the button toggles once, not repeatedly: %d changes"
      % (len(set(states)) - 1))

print("=== a bouncing contact is not two presses ===")
CLOCK["ms"] += 5000
app.update_frame(None, None)
before = app.running
board.btn_start.press();  CLOCK["ms"] += 10; app.update_frame(None, None)
board.btn_start.release(); CLOCK["ms"] += 10; app.update_frame(None, None)
board.btn_start.press();  CLOCK["ms"] += 10; app.update_frame(None, None)
board.btn_start.release(); CLOCK["ms"] += 10; app.update_frame(None, None)
check(app.running != before and app.running == (not before),
      "a bounce within the debounce window counts once")

print("=== a missing button never breaks the app ===")
app._start_pin = None
CLOCK["ms"] += 1000
app.update_frame(None, None)
check(True, "polling a board without the button is harmless")


class _AngryPin:
    def value(self):
        raise OSError("i2c gone")


app._start_pin = _AngryPin()
app.update_frame(None, None)
check(app._start_pin is None, "a pin that starts failing is dropped, not retried forever")
app.onPause(app._view)

# --- settings carried over from the old app id ------------------------------
# The app used to be be.fri3d.pomodoro, a domain that is not ours. Preferences
# hang off the app id, so without carrying them over everybody is back on
# 25 minutes with the LEDs on after the rename.
import mpos.config
import posettings

mpos.config._STORE.clear()
old = mpos.config.SharedPreferences("be.fri3d.pomodoro").edit()
old.put_int("work_min", 40)
old.put_int("sound", 0)        # off is a deliberate zero, not a missing value
old.put_int("done_today", 3)
old.put_string("day", "2026-08-18")
old.commit()

check(posettings.migrate_prefs() is True, "old settings are carried over")
fresh_prefs = mpos.config.SharedPreferences("tech.weyn.pomodoro")
check(fresh_prefs.get_int("work_min", 0) == 40, "the focus length came along")
check(fresh_prefs.get_int("sound", 1) == 0, "sound off survives, zero is a choice")
check(fresh_prefs.get_int("done_today", 0) == 3, "today's count came along")
check(fresh_prefs.get_string("day", "") == "2026-08-18", "and the day it counts for")
check(posettings.migrate_prefs() is False, "a second time takes nothing over")
mpos.config._STORE.clear()
check(posettings.migrate_prefs() is False, "nothing to carry over is not an error")

print()
print("%d checks, %d mislukt" % (checks["n"], len(fails)))
for f in fails:
    print("  -", f)
sys.exit(1 if fails else 0)
