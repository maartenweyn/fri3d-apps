"""Stub of mpos.lights, matching the Fri3d 2026 build."""


class LightsManager:
    log = []
    _buf = None

    @classmethod
    def is_available(cls):
        return True

    @classmethod
    def get_led_count(cls):
        return 5

    @classmethod
    def set_all(cls, r, g, b):
        assert all(0 <= c <= 255 for c in (r, g, b)), (r, g, b)
        cls._buf = (r, g, b)

    @classmethod
    def set_led(cls, i, r, g, b):
        cls._buf = (r, g, b)

    @classmethod
    def clear(cls):
        cls._buf = (0, 0, 0)

    @classmethod
    def write(cls):
        cls.log.append(cls._buf)
