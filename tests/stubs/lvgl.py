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
        self.pos = None
        self.flags = set()
        # Waar het object zich in zijn ouder uitlijnt, als het geen vaste
        # positie kreeg. Bijgehouden en niet weggeslikt, want anders staat een
        # scherm dat met align() gebouwd is in elke natekening op elkaar.
        self.alignment = None
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

    def set_pos(self, x, y):
        self.pos = (x, y)

    # Flags are tracked rather than swallowed: "the button is hidden" is a claim
    # a test should be able to make, and a stub that answered every add_flag with
    # None would let a screen that never hides anything pass.
    def add_flag(self, flag):
        self.flags.add(flag)

    def remove_flag(self, flag):
        self.flags.discard(flag)

    def clear_flag(self, flag):
        self.flags.discard(flag)

    def has_flag(self, flag):
        return flag in self.flags

    def align(self, alignment, x_ofs=0, y_ofs=0):
        self.alignment = (alignment, x_ofs, y_ofs)

    def set_text(self, t):
        self.text = t

    def set_style_text_color(self, color, part):
        self.styles["text_color"] = color

    # Deze drie worden bijgehouden en niet weggeslikt: ze zijn het enige bewijs
    # dat een getekend pictogram brandt of dooft, en dat een label het
    # lettertype kreeg dat de tekening bedoelde.
    def set_style_bg_opa(self, opa, part):
        self.styles["bg_opa"] = opa

    def set_style_bg_color(self, color, part):
        self.styles["bg_color"] = color

    def set_style_text_font(self, font, part):
        self.styles["text_font"] = font

    def set_style_radius(self, radius, part):
        self.styles["radius"] = radius

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
            DEFAULT_GROUP.remove_obj(child)
        self.children = []

    def delete(self):
        """Real LVGL frees the object, which also takes it out of its group.
        A stub that forgot the group would let a test pass while the device
        keeps a dead reference in the focus chain."""
        if self.parent is not None and self in self.parent.children:
            self.parent.children.remove(self)
        self.parent = None
        DEFAULT_GROUP.remove_obj(self)


# De laag boven het actieve scherm. Op het toestel hangt hier de statusbalk in,
# en het klokscherm van de Badge-app komt daar bovenop. Eén vast object, want
# lv.layer_top() geeft op het toestel elke keer dezelfde laag terug.
LAYER_TOP = None


def layer_top():
    global LAYER_TOP
    if LAYER_TOP is None:
        LAYER_TOP = Obj()
    return LAYER_TOP


def obj(parent=None):
    return Obj(parent)


class _ObjFlags:
    """The names the Fri3d 2026 build hangs off lv.obj.FLAG."""
    HIDDEN = 1
    CLICKABLE = 2
    CLICK_FOCUSABLE = 4
    PRESS_LOCK = 8
    SCROLLABLE = 16
    SCROLL_ELASTIC = 32
    SCROLL_MOMENTUM = 64
    SCROLL_CHAIN_HOR = 128
    SCROLL_CHAIN_VER = 256


obj.FLAG = _ObjFlags


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
        self.focused = None

    def add_obj(self, o):
        self.objects.append(o)

    def remove_obj(self, o):
        if o in self.objects:
            self.objects.remove(o)
        if self.focused is o:
            self.focused = None

    def get_focused(self):
        return self.focused


DEFAULT_GROUP = _Group()


def group_get_default():
    return DEFAULT_GROUP


def group_focus_obj(o):
    DEFAULT_GROUP.focused = o


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
ALIGN = _Enum(TOP_MID=0, BOTTOM_MID=1, CENTER=2, TOP_LEFT=3,
              TOP_RIGHT=4, BOTTOM_LEFT=5, BOTTOM_RIGHT=6,
              LEFT_MID=7, RIGHT_MID=8)
font_montserrat_28 = object()
font_montserrat_24 = object()
font_montserrat_20 = object()
font_montserrat_18 = object()
font_montserrat_16 = object()
