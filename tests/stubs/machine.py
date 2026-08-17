"""Stub of MicroPython's machine module.

Only unique_id is used, for the MQTT client id. Fixed value so the tests see
the same suffix every run.
"""

# Documentation MAC (00:00:5E:00:53:xx, RFC 7042). Fixed so the tests see
# the same client id suffix every run, and not anyone's actual hardware.
_UNIQUE_ID = b"\x00\x00\x5e\x00\x53\x2a"


def unique_id():
    return _UNIQUE_ID


def reset():
    raise AssertionError("a test must never reboot the badge")
