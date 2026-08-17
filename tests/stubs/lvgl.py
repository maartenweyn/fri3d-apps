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
        if parent is not None:
            parent.children.append(self)

    def __getattr__(self, name):
        # any set_*/add_*/get_* call is accepted and recorded
        if name.startswith(("set_", "add_", "get_", "remove_", "clear_", "has_", "center", "align", "update")):
            def _f(*a, **k):
                return None
            return _f
        raise AttributeError(name)

    def set_text(self, t):
        self.text = t

    def add_event_cb(self, cb, code, ud):
        self.cbs.append((cb, code))

    def add_state(self, s):
        self.state.add(s)

    def has_state(self, s):
        return s in self.state

    def click(self):
        for cb, code in self.cbs:
            if code == EVENT.CLICKED:
                cb(None)


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


def pct(v):
    return v


def color_hex(v):
    return v


class _Group:
    def add_obj(self, o):
        pass


def group_get_default():
    return _Group()


EVENT = _Enum(CLICKED="clicked", VALUE_CHANGED="value_changed", KEY="key")
FLEX_FLOW = _Enum(COLUMN=0, ROW=1)
FLEX_ALIGN = _Enum(SPACE_EVENLY=0, CENTER=1, START=2)
SCROLLBAR_MODE = _Enum(OFF=0)
# The Fri3d 2026 build has no lv.ANIM; it exposes the flat name instead.
ANIM_OFF = 0
ANIM_ON = 1
OPA = _Enum(TRANSP=0)
PART = _Enum(INDICATOR=1)
STATE = _Enum(CHECKED="checked")
SYMBOL = _Enum(SETTINGS="")
SIZE_CONTENT = 0x7FFF
font_montserrat_28 = object()
