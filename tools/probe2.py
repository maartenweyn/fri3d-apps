# Follow-up probe: how do LEDs and the buzzer actually present themselves
# on this build?  Run with:  mpremote run tools/probe2.py
import mpos

print("=== leds ===")
try:
    import mpos.lights as lights
    print("mpos.lights members:", sorted(n for n in dir(lights) if not n.startswith("_")))
    obj = getattr(lights, "LightsManager", None)
    print("mpos.lights.LightsManager:", obj)
    target = obj if obj is not None else lights
    for name in ("is_available", "get_led_count", "set_all", "set_led", "clear", "write",
                 "set_notification_color"):
        print("  %-22s %s" % (name + ":", hasattr(target, name)))
    try:
        print("  is_available() ->", target.is_available())
        print("  get_led_count() ->", target.get_led_count())
    except Exception as exc:
        print("  call failed:", exc)
except Exception as exc:
    print("mpos.lights unavailable:", exc)

print()
print("mpos.board members:", end=" ")
try:
    import mpos.board as board
    print(sorted(n for n in dir(board) if not n.startswith("_")))
except Exception as exc:
    print("<unavailable:", exc, ">")

print()
print("=== audio outputs ===")
from mpos import AudioManager
for out in AudioManager.get_outputs():
    print(" ", repr(out))
    for attr in ("name", "kind", "channels", "buzzer_pin"):
        print("      %-14s %s" % (attr + ":", getattr(out, attr, "<none>")))

print()
print("=== buzzer test ===")
buzzer = None
for out in AudioManager.get_outputs():
    if getattr(out, "kind", None) == "buzzer" or "kind=buzzer" in repr(out):
        buzzer = out
        break
print("buzzer descriptor:", buzzer)
tune = "brk:d=4,o=5,b=160:8g,8c6,8e6,4g6"
try:
    player = AudioManager.rtttl_player(tune, stream_type=AudioManager.STREAM_ALARM, output=buzzer)
    player.start()
    print("started rtttl on the buzzer -- you should hear four notes")
except Exception as exc:
    print("output= rejected (%s), retrying without it" % exc)
    try:
        AudioManager.rtttl_player(tune, stream_type=AudioManager.STREAM_ALARM).start()
        print("started rtttl on the default output")
    except Exception as exc2:
        print("rtttl failed entirely:", exc2)

import time
time.sleep(3)

print()
print("=== display metrics ===")
try:
    from mpos import DisplayMetrics
    print("members:", sorted(n for n in dir(DisplayMetrics) if not n.startswith("_")))
except Exception as exc:
    print("DisplayMetrics unavailable:", exc)
