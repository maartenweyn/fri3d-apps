"""Offline tests for the Pomodoro app.

Runs on a normal desktop Python against the stubs in tests/stubs/, so the
timer logic can be checked without a badge attached.

    python3 tests/test_pomodoro.py
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.join(ROOT, "be.fri3d.pomodoro"))

# --- MicroPython time shims -------------------------------------------------
CLOCK = {"ms": 1_000_000}
time.ticks_ms = lambda: CLOCK["ms"]
time.ticks_diff = lambda a, b: a - b
time.ticks_add = lambda a, b: a + b
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
def check(cond, msg):
    if not cond:
        fails.append(msg)
    print(("  ok  " if cond else "  FAIL") + "  " + msg)

print("=== defaults + first render ===")
app = pomodoro.Pomodoro()
app.onCreate()
app.onResume(app._view)
check(app.phase == pomodoro.WORK, "starts in the focus phase")
check(app.time_label.text == "25:00", "shows 25:00, got %r" % app.time_label.text)
check(app.start_lbl.text == "Start", "start button reads Start")
check("Round 1/4" in app.status_label.text, "status shows round 1/4: %r" % app.status_label.text)

print("=== start, tick, pause, resume ===")
app._toggle()
check(app.running and app.start_lbl.text == "Pause", "toggle starts the timer")
advance(app, 61_000)
check(app.time_label.text == "23:59", "61 s elapsed -> 23:59, got %r" % app.time_label.text)
app._toggle()
check(not app.running, "second toggle pauses")
before = app.remaining_ms
advance(app, 30_000)
check(app.remaining_ms == before, "clock frozen while paused")
app._toggle()
advance(app, 60_000)
check(app.time_label.text == "22:59", "resumes from where it stopped, got %r" % app.time_label.text)

print("=== full cycle: work -> short -> ... -> long ===")
cfg._STORE.clear()
LightsManager.log.clear(); AudioManager.played.clear()
mpos.config.SharedPreferences("be.fri3d.pomodoro").edit().put_int("work_min", 1)\
    .put_int("short_min", 1).put_int("long_min", 1).put_int("rounds", 4)\
    .put_int("sound", 1).put_int("leds", 1).put_int("autostart", 1).commit()
app = pomodoro.Pomodoro()
app.onCreate(); app.onResume(app._view)
check(app.time_label.text == "01:00", "picks up configured 1 minute, got %r" % app.time_label.text)
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
check(len(LightsManager.log) > 8, "LEDs were driven (%d writes)" % len(LightsManager.log))
check(pomodoro.LightsManager is LightsManager, "LightsManager resolved via mpos.lights")
check(AudioManager.routed and all(o is not None and o.kind == "buzzer" for o in AudioManager.routed),
      "chimes routed to the buzzer, not the headset: %s" % (AudioManager.routed,))
check(cfg._STORE["be.fri3d.pomodoro"]["done_today"] == 4, "counter persisted")

print("=== autostart off leaves the next phase paused ===")
cfg._STORE.clear()
mpos.config.SharedPreferences("be.fri3d.pomodoro").edit().put_int("work_min", 1)\
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
mpos.config.SharedPreferences("be.fri3d.pomodoro").edit()\
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
check(cfg._STORE["be.fri3d.pomodoro"]["work_min"] == 1, "settings persisted on leaving")

print("=== settings feed back into the timer ===")
app = pomodoro.Pomodoro(); app.onCreate(); app.onResume(app._view)
check(app.time_label.text == "01:00", "timer picks up the new 1 minute, got %r" % app.time_label.text)
app.onPause(app._view)
check(LightsManager.log[-1] == (0, 0, 0), "LEDs cleared on leaving the app")
check(app.update_frame not in pomodoro.mpos.ui.task_handler.cbs, "frame callback unregistered on pause")

print()
print("%d check(s) failed" % len(fails))
for f in fails:
    print("  -", f)
sys.exit(1 if fails else 0)
