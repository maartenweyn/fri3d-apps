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
