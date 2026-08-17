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


class _Player:
    def __init__(self, rtttl):
        self.rtttl = rtttl

    def start(self):
        AudioManager.played.append(self.rtttl)


class _Output:
    def __init__(self, name, kind):
        self.name = name
        self.kind = kind

    def __repr__(self):
        return "<AudioOutput %s kind=%s>" % (self.name, self.kind)


class AudioManager:
    STREAM_ALARM = 2
    STREAM_NOTIFICATION = 1
    STREAM_MUSIC = 0
    played = []
    routed = []
    outputs = [_Output("Headset Output", "i2s"), _Output("Badge Buzzer", "buzzer")]

    Output = _Output

    @classmethod
    def get_outputs(cls):
        return cls.outputs

    @classmethod
    def get_default_output(cls):
        return cls.outputs[0]

    @classmethod
    def rtttl_player(cls, rtttl, stream_type=None, output=None):
        cls.routed.append(output)
        return _Player(rtttl)


# The Fri3d 2026 firmware exports SharedPreferences from mpos itself.
from mpos.config import SharedPreferences  # noqa: E402
