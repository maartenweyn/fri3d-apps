"""Settings screen for the Fri3d badge Pomodoro app.

Kept in its own module so the timer stays readable. Values are written to
SharedPreferences when the screen is left, and the timer re-reads them in
onResume().
"""

import lvgl as lv

from mpos import Activity

try:
    from mpos import SharedPreferences
except Exception:
    from mpos.config import SharedPreferences

APP_ID = "tech.weyn.pomodoro"

DEFAULTS = {
    "work_min": 25,
    "short_min": 5,
    "long_min": 15,
    "rounds": 4,
    "sound": 1,
    "leds": 1,
    "autostart": 0,
    "brightness": 10,   # percent; the badge sits an arm's length away
    "volume": 60,
}

# key, label, minimum, maximum, step
NUMBERS = (
    ("work_min", "Focus", 1, 90, 1),
    ("short_min", "Short break", 1, 30, 1),
    ("long_min", "Long break", 1, 60, 1),
    ("rounds", "Rounds to long", 2, 8, 1),
    ("brightness", "LED brightness", 1, 100, 5),
    ("volume", "Chime volume", 0, 100, 10),
)

SWITCHES = (
    ("sound", "Sound"),
    ("leds", "LEDs"),
    ("autostart", "Auto-start next"),
)


LEGACY_APP_ID = "be.fri3d.pomodoro"


def migrate_prefs():
    """Take over what was stored under the old app id, once.

    Preferences hang off the app id, so renaming the app to tech.weyn.pomodoro
    would silently reset everyone's durations, switches and today's count. This
    runs on import rather than in onCreate, because both the timer and this
    settings screen read preferences and either of them can be first.

    A default of -1 tells "not stored" from "stored as zero". Sound off is a
    zero worth keeping.
    """
    try:
        prefs = SharedPreferences(APP_ID)
        if prefs.get_int("work_min", 0):
            return False
        old = SharedPreferences(LEGACY_APP_ID)
        editor = None
        taken = []
        for key in DEFAULTS:
            value = old.get_int(key, -1)
            if value < 0:
                continue
            if editor is None:
                editor = prefs.edit()
            editor.put_int(key, value)
            taken.append(key)
        for key in ("done_today", "round"):
            value = old.get_int(key, -1)
            if value < 0:
                continue
            if editor is None:
                editor = prefs.edit()
            editor.put_int(key, value)
            taken.append(key)
        day = old.get_string("day", "")
        if day:
            if editor is None:
                editor = prefs.edit()
            editor.put_string("day", day)
            taken.append("day")
        if editor is None:
            return False
        editor.commit()
        print("pomodoro: settings carried over from %s:" % LEGACY_APP_ID,
              ", ".join(taken))
        return True
    except Exception as e:
        print("pomodoro: could not carry over the old settings:", e)
        return False


migrate_prefs()


class PomodoroSettings(Activity):

    def __init__(self):
        super().__init__()
        self.values = {}
        self.value_labels = {}
        self.switches = {}

    def onCreate(self):
        prefs = SharedPreferences(APP_ID)
        for key, default in DEFAULTS.items():
            try:
                self.values[key] = prefs.get_int(key, default)
            except Exception:
                self.values[key] = default

        screen = lv.obj()
        screen.set_style_pad_all(6, 0)
        screen.set_style_pad_row(4, 0)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        # More rows than fit on 320x240, so this list scrolls.

        title = lv.label(screen)
        title.set_text("Pomodoro settings")

        for key, text, low, high, step in NUMBERS:
            self._number_row(screen, key, text, low, high, step)
        for key, text in SWITCHES:
            self._switch_row(screen, key, text)

        hint = lv.label(screen)
        hint.set_text("Go back to save")

        self.setContentView(screen)

    def onPause(self, screen):
        self._save()
        super().onPause(screen)

    # ---------------------------------------------------------------- rows

    def _row(self, parent):
        row = lv.obj(parent)
        row.set_size(lv.pct(100), lv.SIZE_CONTENT)
        row.set_style_border_width(0, 0)
        row.set_style_bg_opa(lv.OPA.TRANSP, 0)
        row.set_style_pad_all(2, 0)
        row.set_style_pad_column(6, 0)
        row.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        row.set_flex_flow(lv.FLEX_FLOW.ROW)
        row.set_flex_align(lv.FLEX_ALIGN.START,
                           lv.FLEX_ALIGN.CENTER,
                           lv.FLEX_ALIGN.CENTER)
        return row

    def _small_button(self, parent, text, callback):
        btn = lv.button(parent)
        btn.set_style_pad_hor(10, 0)
        btn.set_style_pad_ver(4, 0)
        label = lv.label(btn)
        label.set_text(text)
        label.center()
        btn.add_event_cb(lambda event, cb=callback: cb(), lv.EVENT.CLICKED, None)
        self._focusable(btn)
        return btn

    def _focusable(self, obj):
        try:
            group = lv.group_get_default()
            if group:
                group.add_obj(obj)
        except Exception:
            pass

    def _number_row(self, parent, key, text, low, high, step=1):
        row = self._row(parent)

        name = lv.label(row)
        name.set_text(text)
        try:
            name.set_flex_grow(1)
        except Exception:
            pass

        self._small_button(row, "-", lambda k=key, lo=low, hi=high, st=step: self._bump(k, -st, lo, hi))

        value = lv.label(row)
        value.set_text(str(self.values[key]))
        self.value_labels[key] = value

        self._small_button(row, "+", lambda k=key, lo=low, hi=high, st=step: self._bump(k, st, lo, hi))

    def _switch_row(self, parent, key, text):
        row = self._row(parent)

        name = lv.label(row)
        name.set_text(text)
        try:
            name.set_flex_grow(1)
        except Exception:
            pass

        sw = lv.switch(row)
        if self.values[key]:
            sw.add_state(lv.STATE.CHECKED)
        sw.add_event_cb(lambda event, k=key, s=sw: self._toggle(k, s),
                        lv.EVENT.VALUE_CHANGED, None)
        self._focusable(sw)
        self.switches[key] = sw

    # -------------------------------------------------------------- handlers

    def _bump(self, key, delta, low, high):
        value = self.values[key] + delta
        if value < low:
            value = low
        if value > high:
            value = high
        self.values[key] = value
        label = self.value_labels.get(key)
        if label is not None:
            label.set_text(str(value))

    def _toggle(self, key, switch):
        self.values[key] = 1 if switch.has_state(lv.STATE.CHECKED) else 0

    def _save(self):
        try:
            editor = SharedPreferences(APP_ID).edit()
            for key in DEFAULTS:
                editor.put_int(key, self.values[key])
            editor.commit()
        except Exception as exc:
            print("pomodoro settings: could not save:", exc)
