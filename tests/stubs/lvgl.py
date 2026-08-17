"""Very small LVGL stand-in: records calls, validates attribute access."""


class _Enum:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class Obj:
    def __init__(self, parent=None):
        self.parent = parent
        self.children = []
        self.text = None
        self.cbs = []
        self.state = set()
        self.styles = {}
        self.size = None
        if parent is not None:
            parent.children.append(self)

    def __getattr__(self, name):
        # any set_*/add_*/get_* call is accepted and recorded
        if name.startswith(("set_", "add_", "get_", "remove_", "clear_", "has_", "center", "align", "update")):
            def _f(*a, **k):
                return None
            return _f
        raise AttributeError(name)

    def set_size(self, w, h):
        self.size = (w, h)

    def set_text(self, t):
        self.text = t

    def set_style_text_color(self, color, part):
        self.styles["text_color"] = color

    def add_event_cb(self, cb, code, ud):
        self.cbs.append((cb, code))

    def add_state(self, s):
        self.state.add(s)

    def remove_state(self, s):
        self.state.discard(s)

    def has_state(self, s):
        return s in self.state

    def click(self):
        for cb, code in self.cbs:
            if code == EVENT.CLICKED:
                cb(None)

    def clean(self):
        """Real LVGL deletes every child. A stub that only forgot them would
        let a screen that rebuilds a list keep counting the old rows."""
        for child in self.children:
            child.parent = None
        self.children = []

    def delete(self):
        if self.parent is not None and self in self.parent.children:
            self.parent.children.remove(self)
        self.parent = None


def obj(parent=None):
    return Obj(parent)


def label(parent=None):
    return Obj(parent)


def button(parent=None):
    return Obj(parent)


def bar(parent=None):
    return Obj(parent)


def switch(parent=None):
    return Obj(parent)


class _Screen:
    def get_width(self):
        return 320

    def get_height(self):
        return 240


def screen_active():
    return _Screen()


class _Timer:
    def __init__(self, cb, period):
        self.cb = cb
        self.period = period
        self.deleted = False
        TIMERS.append(self)

    def delete(self):
        self.deleted = True

    def fire(self):
        self.cb(self)


TIMERS = []


def timer_create(cb, period, user_data=None):
    return _Timer(cb, period)


def pct(v):
    return v


def color_hex(v):
    return v


class _Group:
    def __init__(self):
        self.objects = []

    def add_obj(self, o):
        self.objects.append(o)


DEFAULT_GROUP = _Group()


def group_get_default():
    return DEFAULT_GROUP


EVENT = _Enum(CLICKED="clicked", VALUE_CHANGED="value_changed", KEY="key")
FLEX_FLOW = _Enum(COLUMN=0, ROW=1)
FLEX_ALIGN = _Enum(SPACE_EVENLY=0, CENTER=1, START=2)
SCROLLBAR_MODE = _Enum(OFF=0, ON=1, ACTIVE=2, AUTO=3)
# The Fri3d 2026 build has no lv.ANIM; it exposes the flat name instead.
ANIM_OFF = 0
ANIM_ON = 1
OPA = _Enum(TRANSP=0)
PART = _Enum(INDICATOR=1)
STATE = _Enum(CHECKED="checked", DISABLED="disabled")
# Measured on the Fri3d 2026 build: neither lv.LABEL_LONG nor
# lv.LABEL_LONG_WRAP exists. The enum hangs off lv.label, which is a class
# there and a function here, so the constant is attached to the function.
class _LongMode:
    CLIP = 3
    DOTS = 2
    SCROLL = 1
    SCROLL_CIRCULAR = 4
    WRAP = 0


label.LONG_MODE = _LongMode
TEXT_ALIGN = _Enum(CENTER=2, LEFT=0, RIGHT=1)
SYMBOL = _Enum(SETTINGS="", BELL="", OK="✓")
SIZE_CONTENT = 0x7FFF
ALIGN = _Enum(TOP_MID=0, BOTTOM_MID=1, CENTER=2, TOP_LEFT=3, TOP_RIGHT=4)
font_montserrat_28 = object()
font_montserrat_24 = object()
font_montserrat_20 = object()
font_montserrat_18 = object()
font_montserrat_16 = object()
