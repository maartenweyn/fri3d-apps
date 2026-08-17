# Reports what this badge offers, so apps can be written against real hardware.
# Run with:  mpremote run tools/probe.py
import os
import sys


def show(label, fn):
    try:
        print("%-22s %s" % (label + ":", fn()))
    except Exception as exc:
        print("%-22s <unavailable: %s>" % (label + ":", exc))


print("=== system ===")
show("platform", lambda: sys.platform)
show("implementation", lambda: sys.implementation)
show("uname", lambda: os.uname())
show("root", lambda: sorted(os.listdir("/")))
show("/apps", lambda: sorted(os.listdir("/apps")))
show("/builtin/apps", lambda: sorted(os.listdir("/builtin/apps")))

try:
    import gc
    gc.collect()
    print("%-22s %d bytes" % ("free memory:", gc.mem_free()))
except Exception:
    pass

try:
    stat = os.statvfs("/")
    print("%-22s %d KiB free of %d KiB" % ("filesystem:",
                                           stat[0] * stat[4] // 1024,
                                           stat[0] * stat[2] // 1024))
except Exception:
    pass

print()
print("=== display / input ===")
try:
    import lvgl as lv
    scr = lv.screen_active()
    print("%-22s %d x %d" % ("screen:", scr.get_width(), scr.get_height()))
    fonts = [n for n in dir(lv) if n.startswith("font_")]
    print("%-22s %s" % ("fonts:", sorted(fonts)))
except Exception as exc:
    print("lvgl unavailable:", exc)

try:
    from mpos import InputManager
    import lvgl as lv
    print("%-22s %s" % ("pointer/touch:", InputManager.has_pointer()))
    for name in ("KEYPAD", "POINTER", "BUTTON", "ENCODER"):
        t = getattr(lv.INDEV_TYPE, name, None)
        if t is not None:
            print("%-22s %s" % ("indev " + name + ":", InputManager.has_indev_type(t)))
    print("%-22s %s" % ("indevs:", InputManager.list_indevs()))
except Exception as exc:
    print("InputManager unavailable:", exc)

print()
print("=== leds / audio ===")
try:
    from mpos import LightsManager
    print("%-22s %s" % ("leds available:", LightsManager.is_available()))
    print("%-22s %s" % ("led count:", LightsManager.get_led_count()))
except Exception as exc:
    print("LightsManager unavailable:", exc)

try:
    from mpos import AudioManager
    print("%-22s %s" % ("audio outputs:", AudioManager.get_outputs()))
    print("%-22s %s" % ("audio inputs:", AudioManager.get_inputs()))
    print("%-22s %s" % ("default output:", AudioManager.get_default_output()))
    print("%-22s %s" % ("volume:", AudioManager.get_volume()))
except Exception as exc:
    print("AudioManager unavailable:", exc)

print()
print("=== build ===")
try:
    from mpos import BuildInfo
    print("%-22s %s" % ("build:", BuildInfo.__dict__))
except Exception as exc:
    print("BuildInfo unavailable:", exc)

try:
    from mpos import DeviceInfo
    print("%-22s %s" % ("device:", DeviceInfo.get_hardware_id()))
except Exception as exc:
    print("DeviceInfo unavailable:", exc)

print()
print("=== mpos exports ===")
try:
    import mpos
    print(sorted(n for n in dir(mpos) if not n.startswith("_")))
except Exception as exc:
    print("mpos unavailable:", exc)
