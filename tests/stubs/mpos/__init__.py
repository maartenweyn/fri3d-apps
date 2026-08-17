class Activity:
    def __init__(self):
        self._fg = False
        self._intent = None
        self._view = None

    def setContentView(self, screen):
        self._view = screen

    def onResume(self, screen):
        self._fg = True

    def onPause(self, screen):
        self._fg = False

    def has_foreground(self):
        return self._fg

    def startActivity(self, intent):
        STARTED.append(intent)

    def finish(self):
        pass


STARTED = []


class Intent:
    def __init__(self, activity_class=None, action=None, data=None):
        self.activity_class = activity_class
        self.action = action
        self.data = data
        self.extras = {}


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


class _Player:
    def __init__(self, rtttl):
        self.rtttl = rtttl

    def start(self):
        AudioManager.played.append(self.rtttl)


class AudioManager:
    STREAM_ALARM = 2
    STREAM_NOTIFICATION = 1
    STREAM_MUSIC = 0
    played = []

    @classmethod
    def rtttl_player(cls, rtttl, stream_type=None):
        return _Player(rtttl)
