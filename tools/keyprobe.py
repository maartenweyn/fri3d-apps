# What do the badge's physical buttons send?
#
# Dumps the input plumbing statically, so nothing has to be pressed at the
# right moment: the registered input devices, the IO expander that reads the
# buttons, and the LVGL key codes they could be mapped onto.
#
#   ./badge.sh run tools/keyprobe.py
import sys

import lvgl as lv


def section(title):
    print()
    print("=== %s ===" % title)


section("lv.KEY members")
key = getattr(lv, "KEY", None)
if key is None:
    print("  lv.KEY missing; flat names:",
          sorted(n for n in dir(lv) if n.startswith("KEY")))
else:
    for name in sorted(n for n in dir(key) if not n.startswith("_")):
        value = getattr(key, name)
        printable = chr(value) if isinstance(value, int) and 32 <= value < 127 else ""
        print("  %-12s %-6s %s" % (name, value, printable))

section("registered input devices")
try:
    from mpos import InputManager
    for indev in InputManager.list_indevs():
        print(" ", repr(indev))
        for attr in ("get_type", "get_key", "get_group"):
            fn = getattr(indev, attr, None)
            if fn:
                try:
                    print("      %-12s %s" % (attr + "():", fn()))
                except Exception as exc:
                    print("      %-12s <%s>" % (attr + "():", exc))
except Exception as exc:
    print("  InputManager unavailable:", exc)

section("io expander")
try:
    import mpos.io_expander as expander
    print("  module members:",
          sorted(n for n in dir(expander) if not n.startswith("_")))
    for name in sorted(n for n in dir(expander) if not n.startswith("_")):
        value = getattr(expander, name)
        if isinstance(value, (int, str, tuple, dict)):
            print("    %-24s %r" % (name, value))
except Exception as exc:
    print("  mpos.io_expander unavailable:", exc)

section("board")
try:
    import mpos.board as board
    print("  module members:",
          sorted(n for n in dir(board) if not n.startswith("_")))
    for name in sorted(n for n in dir(board) if not n.startswith("_")):
        if "button" in name.lower() or "key" in name.lower() or "btn" in name.lower():
            print("    %-24s %r" % (name, getattr(board, name)))
except Exception as exc:
    print("  mpos.board unavailable:", exc)

section("anything button-shaped in mpos")
try:
    import mpos
    names = [n for n in dir(mpos)
             if any(word in n.lower() for word in ("button", "key", "input", "expander"))]
    print(" ", sorted(names))
except Exception as exc:
    print("  mpos unavailable:", exc)

section("live capture")
print("  Press the badge buttons now. Codes appear as they arrive.")
print("  This listens on the active screen for 20 seconds.")
try:
    import time

    screen = lv.screen_active()
    seen = {}

    def on_key(event):
        try:
            code = event.get_key()
        except Exception:
            try:
                code = lv.indev_active().get_key()
            except Exception:
                code = None
        if code is None:
            return
        seen[code] = seen.get(code, 0) + 1
        printable = chr(code) if isinstance(code, int) and 32 <= code < 127 else ""
        print("  key %-6s hex %-6s %s" % (code, hex(code) if isinstance(code, int) else "", printable))

    screen.add_event_cb(on_key, lv.EVENT.KEY, None)
    deadline = time.ticks_add(time.ticks_ms(), 20000)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        time.sleep_ms(100)
    print("  distinct codes seen:", sorted(seen))
except Exception as exc:
    print("  live capture failed:", exc)
    sys.print_exception(exc)
