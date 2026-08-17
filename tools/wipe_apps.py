# Removes every user-installed app from /apps on the badge.
# Built-in apps live in the read-only /builtin and are untouched.
# Run with:  mpremote run tools/wipe_apps.py
import os

APPS = "/apps"


def rmtree(path):
    try:
        mode = os.stat(path)[0]
    except OSError:
        return
    if mode & 0x4000:  # directory
        for entry in os.listdir(path):
            rmtree(path + "/" + entry)
        os.rmdir(path)
    else:
        os.remove(path)


try:
    entries = sorted(os.listdir(APPS))
except OSError:
    entries = []
    print("No %s directory on this device." % APPS)

print("Found %d installed app(s) in %s" % (len(entries), APPS))
for name in entries:
    print("  removing", name)
    try:
        rmtree(APPS + "/" + name)
    except Exception as exc:
        print("    FAILED:", exc)

try:
    print("Remaining in %s: %s" % (APPS, os.listdir(APPS)))
except OSError:
    print("%s is gone; it will be recreated on install." % APPS)

try:
    import gc
    gc.collect()
    print("Free memory: %d bytes" % gc.mem_free())
except Exception:
    pass
