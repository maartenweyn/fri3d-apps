"""Stub of mpos.time, matching the Fri3d 2026 build.

Two things measured on the device that this mirrors:

- `time.localtime()` returns UTC even when the timezone preference is set to
  Europe/Brussels, so the OS clock cannot be read naively.
- `TimeZone.timezone_preference` is a plain attribute here, not a method, and
  `localPTZtime.tztime(epoch, posix)` is what actually applies the offset.

The epoch is MicroPython's, counting from 2000-01-01.
"""

EPOCH_OFFSET = 946684800          # 2000-01-01 in Unix seconds

ZONES = {
    "Europe/Brussels": "CET-1CEST,M3.5.0,M10.5.0/3",
    "Etc/GMT": "GMT0",
}

# Test-controlled: what the badge is set to.
STATE = {"preference": "Europe/Brussels"}


class TimeZone:
    @classmethod
    def get_timezones(cls):
        return sorted(ZONES)

    @classmethod
    def timezone_to_posix_time_zone(cls, name):
        return ZONES.get(name)

    @classmethod
    def time_is_set(cls):
        return True


def _preference():
    return STATE["preference"]


# On the device this is an attribute holding a string, not a method. Emulate
# that with a class attribute so the app's callable() check is exercised for
# real rather than assumed.
TimeZone.timezone_preference = STATE["preference"]


def epoch_seconds():
    import time
    return int(time.time())


class localPTZtime:
    """Only tztime is used. Offsets are fixed, which is enough: the tests
    check that the app converts at all, and which zone it converted with."""

    OFFSETS = {"CET-1CEST,M3.5.0,M10.5.0/3": 7200, "GMT0": 0}
    calls = []

    @classmethod
    def reset(cls):
        cls.calls = []

    @classmethod
    def tztime(cls, epoch, posix):
        import time as _time
        cls.calls.append((epoch, posix))
        if posix not in cls.OFFSETS:
            raise ValueError("unknown posix zone %r" % posix)
        shifted = int(epoch) + EPOCH_OFFSET + cls.OFFSETS[posix]
        parts = _time.gmtime(shifted)
        return (parts.tm_year, parts.tm_mon, parts.tm_mday, parts.tm_hour,
                parts.tm_min, parts.tm_sec, parts.tm_wday, parts.tm_yday, 1)
