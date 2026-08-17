"""Stub of mpos.ui.

remove_event_cb matches by identity, the way MicroPython behaves: a bound
method read off an instance is a fresh object each time, so removing
`self.update_frame` does not necessarily remove what `add_event_cb` was given.
Matching loosely here would hide exactly that class of bug.
"""


class _TaskHandler:
    def __init__(self):
        self.cbs = []

    def add_event_cb(self, fn, prio):
        self.cbs.append(fn)

    def remove_event_cb(self, fn):
        for index, registered in enumerate(self.cbs):
            if registered is fn:
                del self.cbs[index]
                return
        raise ValueError("callback was never registered under this identity")


task_handler = _TaskHandler()


class _MainDisplay:
    """Stand-in for mpos.ui.main_display.

    get_inactive_time() is milliseconds since the last touch or key. The real
    get_backlight() returns -1 on this firmware, which is why the brightness
    goes through the I2C expander instead; the stub returns -1 too so nobody is
    tempted to use it.
    """

    inactive_ms = 0
    activity_triggers = 0

    @classmethod
    def reset(cls):
        cls.inactive_ms = 0
        cls.activity_triggers = 0

    @classmethod
    def get_inactive_time(cls):
        return cls.inactive_ms

    @classmethod
    def trigger_activity(cls):
        cls.activity_triggers += 1
        cls.inactive_ms = 0

    @classmethod
    def get_backlight(cls):
        return -1


main_display = _MainDisplay
