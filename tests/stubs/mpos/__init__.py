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

    def startActivityForResult(self, intent, callback):
        STARTED.append(intent)
        RESULTS_PENDING.append((intent, callback))

    def finish(self):
        pass


STARTED = []
RESULTS_PENDING = []      # (intent, callback) awaiting a result


class Service:
    """Stub of mpos.app.service.Service, re-exported from mpos."""

    def __init__(self):
        self.appFullName = None

    def onCreate(self):
        pass

    def onStart(self, intent=None):
        pass

    def onDestroy(self):
        pass


class Intent:
    def __init__(self, activity_class=None, action=None, data=None,
                 app_fullname=None):
        self.activity_class = activity_class
        self.action = action
        self.data = data
        self.app_fullname = app_fullname
        self.extras = {}

    def putExtra(self, key, value):
        self.extras[key] = value
        return self


class InputActivity:
    """Stand-in for the OS single-value input screen.

    The real one owns the on-screen keyboard and hands back
    {"result_code": bool, "data": {"value": str, ...}}. Tests drive that
    contract directly through RESULTS_PENDING.
    """
    pass


class Notification:
    PRIORITY_MIN = -1
    PRIORITY_LOW = 0
    PRIORITY_DEFAULT = 1
    PRIORITY_HIGH = 2
    PRIORITY_MAX = 3

    def __init__(self, notification_id=None, icon=None, title=None, text=None,
                 priority=PRIORITY_DEFAULT, intent=None, auto_cancel=True,
                 app_fullname=None):
        assert notification_id, "a notification needs a stable id"
        # Only string icons survive a reboot, and this firmware is picky about
        # which lv.SYMBOL names exist at all.
        assert isinstance(icon, str) and icon, "icon must be a non-empty string"
        self.notification_id = notification_id
        self.icon = icon
        self.title = title
        self.text = text
        self.priority = priority
        self.intent = intent
        self.auto_cancel = auto_cancel
        self.app_fullname = app_fullname


class NotificationManager:
    posted = []
    cancelled = []

    @classmethod
    def reset(cls):
        cls.posted = []
        cls.cancelled = []

    @classmethod
    def notify(cls, notification):
        cls.posted.append(notification)

    @classmethod
    def cancel(cls, notification_id):
        cls.cancelled.append(notification_id)


class AppManager:
    started = []

    @classmethod
    def reset(cls):
        cls.started = []

    @classmethod
    def start_app(cls, app_fullname):
        cls.started.append(app_fullname)

    @classmethod
    def refresh_apps(cls):
        pass


class TaskManager:
    """Records coroutines instead of running them.

    The badge runs asyncio on the LVGL thread; the tests drive the service's
    loop body by hand so a hung socket in a test cannot hang the suite.
    """

    tasks = []

    @classmethod
    def reset(cls):
        for task in cls.tasks:
            close = getattr(task, "close", None)
            if close is not None:
                close()
        cls.tasks = []

    @classmethod
    def create_task(cls, coro):
        cls.tasks.append(coro)
        return coro

    @classmethod
    async def sleep(cls, seconds):
        return None

    @classmethod
    def good_stack_size(cls):
        return 8192


class BatteryManager:
    """Stub of the ADC behind the battery, driven by the tests.

    `present = False` is the badge on USB with no cell in it, and
    `percentage = None` is the reading the real one returns before the ADC has
    settled. Both have to leave the service publishing rather than crashing.
    """

    present = True
    percentage = 87.4
    voltage = 3.916

    @classmethod
    def reset(cls):
        cls.present = True
        cls.percentage = 87.4
        cls.voltage = 3.916

    @classmethod
    def has_battery(cls):
        return cls.present

    @classmethod
    def get_battery_percentage(cls):
        return cls.percentage

    @classmethod
    def read_battery_voltage(cls):
        return cls.voltage


class _Version:
    release = "0.16.1"
    api_level = 0


class BuildInfo:
    version = _Version


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
    volumes = []
    outputs = [_Output("Headset Output", "i2s"), _Output("Badge Buzzer", "buzzer")]

    Output = _Output

    @classmethod
    def get_outputs(cls):
        return cls.outputs

    @classmethod
    def get_default_output(cls):
        return cls.outputs[0]

    @classmethod
    def rtttl_player(cls, rtttl, stream_type=None, output=None, volume=None):
        cls.routed.append(output)
        cls.volumes.append(volume)
        return _Player(rtttl)


class _IOExpander:
    """The CH32X035 behind the screen brightness.

    lcd_brightness is 0..100 and writable; 0 is off. This is the only way that
    works on this firmware: the LVGL route through main_display.get_backlight()
    returns -1.
    """

    lcd_brightness = 100
    # The small debug LED on the same chip. Ships at 50, so it is always on,
    # including all night on a badge that is charging.
    debug_led = 50

    @classmethod
    def reset(cls):
        cls.lcd_brightness = 100
        cls.debug_led = 50


io_expander = _IOExpander


# The Fri3d 2026 firmware exports SharedPreferences from mpos itself.
from mpos.config import SharedPreferences  # noqa: E402
