"""Settings screen for Berichtjes.

Only what is about messages. The name of the badge, the broker and the login used
to be here; they moved to the Badge app, because they are properties of the
badge and not of this app. The button in the middle opens that app rather than
duplicating its screens here: two places to type one broker address is how two
badges end up pointing at different ones.

Two things about the layout are deliberate, both learned by trying to tap it
with a finger rather than by sending events to it. The rows do not scroll: the
content fits, and on a scrollable container LVGL turns a press that drifts a few
pixels into a scroll and cancels the click, which reads as a dead button. And
the controls are full width, because a control you cannot hit is a control that
does not exist.

Values are written to SharedPreferences when the screen is left, and the service
applies them immediately.
"""

import lvgl as lv

from mpos import Activity

import dinerbadge_service as service

try:
    from mpos import SharedPreferences
except Exception:
    from mpos.config import SharedPreferences

try:
    from mpos import AppManager
except Exception:                                    # pragma: no cover
    AppManager = None

COL_DIM = 0x8890A0
COL_WARN = 0xCC5555

# The screen is 240 high and 8 of padding goes top and bottom, so 224 is the
# budget. A title of 16 plus three rows and their gaps leaves room to spare.
# Adding a fifth row does not fit: the container deliberately cannot scroll, so
# anything past the bottom is simply unreachable. Split the screen instead.
ROW_HEIGHT = 44
ROW_GAP = 6
SCREEN_BUDGET = 224


class DinerBadgeSettings(Activity):

    def __init__(self):
        super().__init__()
        self.led_alert = True
        self.timeout_min = 30
        self.timeout_label = None
        self.switch = None
        self.hint = None
        self.rows = 0            # against the screen budget above

    # --- lifecycle ---------------------------------------------------------

    def onCreate(self):
        self.led_alert = bool(service.LED_ALERT)
        self.timeout_min = int(service.ACK_TIMEOUT_MIN)

        screen = lv.obj()
        screen.set_style_pad_all(8, 0)
        screen.set_style_pad_row(ROW_GAP, 0)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        # Measured: the rows leave room on a 240 high screen, so there is
        # nothing to scroll, and a container that cannot scroll cannot swallow
        # a tap by deciding it was a drag.
        self._no_scroll(screen)

        title = lv.label(screen)
        title.set_text("Instellingen")
        title.set_style_text_color(lv.color_hex(COL_DIM), 0)

        # The name of this badge and the broker live in the Badge app. This
        # opens it rather than repeating its screens here.
        self._wide_button(screen, "Badge en verbinding...", self._open_badge)

        self.switch = self._switch_row(screen, "LEDs knipperen")
        self.timeout_label = self._stepper_row(
            screen, "Stop na", "%d min" % self.timeout_min, self._cycle_timeout)

        # Says so when the app this one leans on is not there, because then
        # nothing arrives and nothing else on this screen explains why.
        self.hint = lv.label(screen)
        self.hint.set_style_text_color(lv.color_hex(COL_WARN), 0)
        self._paint_hint()

        self.setContentView(screen)

    def onResume(self, screen):
        super().onResume(screen)
        self._paint_hint()

    def onPause(self, screen):
        self._save()
        super().onPause(screen)

    def _paint_hint(self):
        if self.hint is None:
            return
        reason = service.bridge_missing_reason()
        self.hint.set_text(reason or "")

    # --- the badge app -----------------------------------------------------

    def _open_badge(self):
        """Hand off to the app that owns the badge's name and connection."""
        if AppManager is None:
            print("dinerbadge settings: no AppManager, cannot open the Badge app")
            return
        try:
            AppManager.start_app(service.BRIDGE_APP)
        except Exception as e:
            print("dinerbadge settings: could not open the Badge app:", e)

    # --- rows --------------------------------------------------------------

    def _no_scroll(self, obj):
        try:
            obj.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        except Exception:
            pass
        for spelling in ("SCROLLABLE", "SCROLL_ELASTIC", "SCROLL_MOMENTUM",
                         "SCROLL_CHAIN_HOR", "SCROLL_CHAIN_VER"):
            flag = getattr(getattr(lv.obj, "FLAG", None), spelling, None)
            if flag is None:
                flag = getattr(lv, "OBJ_FLAG_" + spelling, None)
            if flag is not None:
                try:
                    obj.remove_flag(flag)
                except Exception:
                    try:
                        obj.clear_flag(flag)
                    except Exception:
                        pass

    def _row(self, parent, height=None):
        row = lv.obj(parent)
        row.set_size(lv.pct(100), height or lv.SIZE_CONTENT)
        row.set_style_border_width(0, 0)
        row.set_style_bg_opa(lv.OPA.TRANSP, 0)
        row.set_style_pad_all(2, 0)
        row.set_style_pad_column(8, 0)
        self._no_scroll(row)
        row.set_flex_flow(lv.FLEX_FLOW.ROW)
        row.set_flex_align(lv.FLEX_ALIGN.START,
                           lv.FLEX_ALIGN.CENTER,
                           lv.FLEX_ALIGN.CENTER)
        return row

    def _focusable(self, obj):
        try:
            group = lv.group_get_default()
            if group:
                group.add_obj(obj)
        except Exception:
            pass

    def _wide_button(self, parent, text, callback):
        """A full-width, finger-sized button. Hard to miss on purpose."""
        self.rows += 1
        btn = lv.button(parent)
        btn.set_size(lv.pct(100), ROW_HEIGHT)
        btn.add_event_cb(lambda event, cb=callback: cb(), lv.EVENT.CLICKED, None)
        label = lv.label(btn)
        label.set_text(text)
        label.center()
        self._focusable(btn)
        return label

    def _step_button(self, parent, text, callback):
        btn = lv.button(parent)
        btn.set_size(48, 40)
        btn.add_event_cb(lambda event, cb=callback: cb(), lv.EVENT.CLICKED, None)
        label = lv.label(btn)
        label.set_text(text)
        label.center()
        self._focusable(btn)
        return btn

    def _stepper_row(self, parent, text, value, cycle):
        self.rows += 1
        row = self._row(parent, ROW_HEIGHT)
        name = lv.label(row)
        name.set_text(text)
        try:
            name.set_flex_grow(1)
        except Exception:
            pass
        self._step_button(row, "-", lambda c=cycle: c(-1))
        value_label = lv.label(row)
        value_label.set_text(value)
        self._step_button(row, "+", lambda c=cycle: c(1))
        return value_label

    def _switch_row(self, parent, text):
        self.rows += 1
        row = self._row(parent, ROW_HEIGHT)
        name = lv.label(row)
        name.set_text(text)
        try:
            name.set_flex_grow(1)
        except Exception:
            pass
        sw = lv.switch(row)
        try:
            sw.set_size(56, 30)
        except Exception:
            pass
        if self.led_alert:
            sw.add_state(lv.STATE.CHECKED)
        sw.add_event_cb(lambda event, s=sw: self._toggle(s),
                        lv.EVENT.VALUE_CHANGED, None)
        self._focusable(sw)
        return sw

    # --- handlers ----------------------------------------------------------

    def _cycle_timeout(self, delta):
        # Five to sixty minutes, in fives. Below five the blinking stops before
        # a child upstairs has noticed it.
        self.timeout_min = min(60, max(5, self.timeout_min + delta * 5))
        if self.timeout_label is not None:
            self.timeout_label.set_text("%d min" % self.timeout_min)

    def _toggle(self, switch):
        self.led_alert = bool(switch.has_state(lv.STATE.CHECKED))

    def _save(self):
        try:
            editor = SharedPreferences(service.PREFS_APP_ID).edit()
            editor.put_int("led_alert", 1 if self.led_alert else 0)
            editor.put_int("ack_timeout_min", int(self.timeout_min))
            editor.commit()
        except Exception as e:
            print("dinerbadge settings: could not save:", e)
        # Apply straight away, so nobody has to reboot to see it take.
        service.load_prefs()
