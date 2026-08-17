"""Stub of the Fri3d 2026 board wiring: just the bits the app touches."""


class _Pin:
    """GPIO0, the S button. Reads 1 at rest and 0 while held."""

    def __init__(self):
        self.level = 1

    def value(self):
        return self.level

    def press(self):
        self.level = 0

    def release(self):
        self.level = 1


btn_start = _Pin()
