"""Stub of mpos.lights, matching the Fri3d 2026 build.

LightsManager is not exported from mpos on that firmware; it lives here.
"""

LED_COUNT = 5


class LightsManager:
    leds = [(0, 0, 0)] * LED_COUNT
    log = []

    @classmethod
    def reset(cls):
        cls.leds = [(0, 0, 0)] * LED_COUNT
        cls.log = []

    @classmethod
    def is_available(cls):
        return True

    @classmethod
    def get_led_count(cls):
        return LED_COUNT

    @classmethod
    def set_led(cls, index, r, g, b):
        assert 0 <= index < LED_COUNT, index
        for channel in (r, g, b):
            assert isinstance(channel, int) and 0 <= channel <= 255, (index, r, g, b)
        cls.leds[index] = (r, g, b)

    @classmethod
    def set_all(cls, r, g, b):
        for index in range(LED_COUNT):
            cls.set_led(index, r, g, b)

    @classmethod
    def clear(cls):
        cls.set_all(0, 0, 0)

    @classmethod
    def write(cls):
        cls.log.append(list(cls.leds))

    @classmethod
    def lit(cls):
        """How many LEDs are currently emitting anything."""
        return sum(1 for led in cls.leds if max(led) > 0)
