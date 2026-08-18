# Diagnose why an app will not load: checks the files, the manifest, the
# frameworks it expects, and then actually imports and constructs each
# activity, printing the full traceback for whatever breaks first.
#
#   ./badge.sh diag [app-id]
import json
import os
import sys

try:
    APP_ID
except NameError:
    APP_ID = "tech.weyn.pomodoro"

APP_DIR = "/apps/" + APP_ID


def section(title):
    print()
    print("=== %s ===" % title)


section("files in " + APP_DIR)
try:
    names = sorted(os.listdir(APP_DIR))
except OSError as exc:
    print("  cannot list %s: %s" % (APP_DIR, exc))
    print("  is the app installed?  ./badge.sh install")
    raise SystemExit
for name in names:
    try:
        size = os.stat(APP_DIR + "/" + name)[6]
    except OSError:
        size = -1
    print("  %-22s %6d bytes" % (name, size))

section("manifest")
activities = []
try:
    with open(APP_DIR + "/MANIFEST.JSON") as handle:
        manifest = json.load(handle)
    print("  parses ok:", manifest.get("fullname"), manifest.get("version"))
    activities = manifest.get("activities", [])
    if not activities:
        print("  WARNING: no activities declared")
except Exception as exc:
    print("  MANIFEST.JSON is broken:")
    sys.print_exception(exc)

section("environment")
import mpos
for name in ("Activity", "Intent", "SharedPreferences", "AudioManager",
             "AppManager", "LightsManager", "TaskManager"):
    print("  mpos.%-18s %s" % (name + ":", hasattr(mpos, name)))
for name in ("mpos.ui", "mpos.lights", "mpos.config", "mpos.shared_preferences"):
    try:
        __import__(name)
        print("  %-24s importable" % name)
    except Exception as exc:
        print("  %-24s MISSING (%s)" % (name, exc))
try:
    import mpos.ui
    print("  mpos.ui.task_handler:", mpos.ui.task_handler)
except Exception as exc:
    print("  mpos.ui.task_handler MISSING:", exc)

section("lvgl symbols this app uses")
import lvgl as lv

CONSTANTS = (
    ("ANIM", "OFF"), ("EVENT", "CLICKED"), ("EVENT", "VALUE_CHANGED"),
    ("EVENT", "KEY"), ("FLEX_FLOW", "COLUMN"), ("FLEX_FLOW", "ROW"),
    ("FLEX_ALIGN", "CENTER"), ("FLEX_ALIGN", "START"),
    ("FLEX_ALIGN", "SPACE_EVENLY"), ("SCROLLBAR_MODE", "OFF"),
    ("OPA", "TRANSP"), ("PART", "INDICATOR"), ("STATE", "CHECKED"),
    ("SYMBOL", "SETTINGS"),
)
missing = []
for group, name in CONSTANTS:
    holder = getattr(lv, group, None)
    found = holder is not None and getattr(holder, name, None) is not None
    if not found:
        flat = getattr(lv, group + "_" + name, None)
        if flat is not None:
            print("  lv.%s.%s -> only as lv.%s_%s" % (group, name, group, name))
            continue
        missing.append("lv.%s.%s" % (group, name))
        print("  lv.%s.%s MISSING" % (group, name))
for name in ("SIZE_CONTENT", "pct", "color_hex", "group_get_default",
             "obj", "label", "button", "bar", "switch", "screen_active"):
    if getattr(lv, name, None) is None:
        missing.append("lv." + name)
        print("  lv.%s MISSING" % name)
print("  %d of %d symbols missing" % (len(missing), len(CONSTANTS) + 10))
if missing:
    print("  ->", missing)

WIDGET_METHODS = (
    ("bar", ("set_range", "set_value")),
    ("label", ("set_text", "set_style_text_font", "set_style_text_color")),
    ("obj", ("set_flex_flow", "set_flex_align", "set_style_pad_column",
             "set_scrollbar_mode", "set_flex_grow")),
    ("switch", ("add_state", "has_state")),
)
for factory, methods in WIDGET_METHODS:
    try:
        widget = getattr(lv, factory)()
    except Exception as exc:
        print("  lv.%s() failed: %s" % (factory, exc))
        continue
    absent = [m for m in methods if not hasattr(widget, m)]
    if absent:
        print("  lv.%s is missing %s" % (factory, absent))

section("importing the activities")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

for activity in activities:
    entry = activity.get("entrypoint", "")
    classname = activity.get("classname")
    modname = entry[:-3] if entry.endswith(".py") else entry
    print("  %s -> %s" % (entry, classname))

    try:
        module = __import__(modname)
    except Exception as exc:
        print("    IMPORT FAILED")
        sys.print_exception(exc)
        continue
    print("    imported")

    klass = getattr(module, classname, None)
    if klass is None:
        print("    class %r not found in %s" % (classname, modname))
        continue

    try:
        instance = klass()
    except Exception as exc:
        print("    CONSTRUCTOR FAILED")
        sys.print_exception(exc)
        continue
    print("    constructed")

    try:
        instance.onCreate()
    except Exception as exc:
        print("    onCreate FAILED")
        sys.print_exception(exc)
        continue
    print("    onCreate ok")

section("what the launcher sees")
try:
    from mpos import AppManager
    AppManager.refresh_apps()
    print(" ", sorted(app.fullname for app in AppManager.get_app_list()))
except Exception as exc:
    sys.print_exception(exc)
