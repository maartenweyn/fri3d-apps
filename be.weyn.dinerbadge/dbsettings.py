"""Settings screen for Berichtjes.

Its reason to exist is the name. Both badges run an identical copy of the app,
and you type the name here rather than editing a file and reinstalling. The name
has to match the topic Home Assistant publishes to, which is why it is
normalised before it is stored: a stray capital or trailing space would point the
badge at a topic nobody publishes to, and nothing would arrive, silently.

Two things about the layout are deliberate, both learned by trying to tap it
with a finger rather than by sending events to it. The rows do not scroll: the
content fits, and on a scrollable container LVGL turns a press that drifts a few
pixels into a scroll and cancels the click, which reads as a dead button. And the
name is a full-width button rather than a small chip at the right edge, because
it is the one control anyone comes here for.

Values are written to SharedPreferences when the screen is left, and the service
applies them immediately, which for the name means dropping the MQTT connection
and resubscribing.
"""

import lvgl as lv

from mpos import Activity, Intent, InputActivity

import dinerbadge_service as service
from dbconnection import DinerBadgeConnection

try:
    from mpos import SharedPreferences
except Exception:
    from mpos.config import SharedPreferences

COL_DIM = 0x8890A0

# The screen is 240 high and 8 of padding goes top and bottom, so 224 is the
# budget. A title of 16 plus four rows and their gaps leaves 8 spare. Adding a
# fifth row does not fit: the container deliberately cannot scroll, so anything
# past the bottom is simply unreachable. Split the screen instead, the way the
# broker settings are split off.
ROW_HEIGHT = 44
ROW_GAP = 6
SCREEN_BUDGET = 224


class DinerBadgeSettings(Activity):

    def __init__(self):
        super().__init__()
        self.name = ""
        self.led_alert = True
        self.timeout_min = 30
        self.name_button_label = None
        self.timeout_label = None
        self.switch = None
        self.rows = 0            # against the screen budget above

    # --- lifecycle ---------------------------------------------------------

    def onCreate(self):
        self.name = service.CHILD_NAME
        self.led_alert = bool(service.LED_ALERT)
        self.timeout_min = int(service.ACK_TIMEOUT_MIN)

        screen = lv.obj()
        screen.set_style_pad_all(8, 0)
        screen.set_style_pad_row(ROW_GAP, 0)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        # Measured: the rows reach y=168 on a 240 high screen, so there is
        # nothing to scroll, and a container that cannot scroll cannot swallow
        # a tap by deciding it was a drag.
        self._no_scroll(screen)

        title = lv.label(screen)
        title.set_text("Instellingen")
        title.set_style_text_color(lv.color_hex(COL_DIM), 0)

        # No hint line under this: the input screen it opens carries the note
        # about matching Home Assistant, and the 24 pixels it cost were the
        # difference between four rows fitting and the last one falling off.
        self.name_button_label = self._wide_button(
            screen, self._name_button_text(), self._edit_name)

        self._wide_button(screen, "Verbinding...", self._open_connection)

        self.switch = self._switch_row(screen, "LEDs knipperen")
        self.timeout_label = self._stepper_row(
            screen, "Stop na", "%d min" % self.timeout_min, self._cycle_timeout)

        self.setContentView(screen)

    def onPause(self, screen):
        self._save()
        super().onPause(screen)

    # --- the name ----------------------------------------------------------

    def _display_name(self):
        return service.titlecase(self.name) if self.name else "nog niet ingesteld"

    def _name_button_text(self):
        return "Deze badge: " + self._display_name()

    def _edit_name(self):
        """Hand off to the OS input screen, which owns the keyboard."""
        intent = Intent(activity_class=InputActivity)
        intent.putExtra("setting", {
            "title": "Naam van deze badge",
            "key": "child_name",
            "ui": "textarea",
            "placeholder": "bv. alice",
            "note": "Moet gelijk zijn aan de naam in Home Assistant. "
                    "Kleine letters, geen spaties.",
        })
        intent.putExtra("value", self.name)
        self.startActivityForResult(intent, self._name_result)

    def _name_result(self, result):
        if not result or not result.get("result_code"):
            return                       # cancelled or swiped back
        typed = (result.get("data") or {}).get("value") or ""
        cleaned = service.normalize_name(typed)
        if not cleaned:
            # Rather than storing something that can never receive a message.
            print("dinerbadge settings: %r is not a usable name" % typed)
            return
        self.name = cleaned
        if self.name_button_label is not None:
            self.name_button_label.set_text(self._name_button_text())

    def _open_connection(self):
        """Broker address and credentials, on their own screen so both fit."""
        self.startActivity(Intent(activity_class=DinerBadgeConnection))

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

    def _hint(self, parent, text):
        hint = lv.label(parent)
        hint.set_text(text)
        hint.set_style_text_color(lv.color_hex(COL_DIM), 0)
        return hint

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
        name = service.normalize_name(self.name) or service.CHILD_NAME
        try:
            editor = SharedPreferences(service.PREFS_APP_ID).edit()
            editor.put_string("child_name", name)
            editor.put_int("led_alert", 1 if self.led_alert else 0)
            editor.put_int("ack_timeout_min", int(self.timeout_min))
            editor.commit()
        except Exception as e:
            print("dinerbadge settings: could not save:", e)
        # Apply straight away. Changing the name has to resubscribe, and a child
        # who just typed their name should not have to reboot.
        service.load_prefs()
