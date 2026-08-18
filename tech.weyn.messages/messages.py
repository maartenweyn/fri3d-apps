"""Berichtjes: the screen a child sees when a message arrives.

The work happens in messages_service; this activity only renders the
service's state and sends the acknowledgement. It owns no MQTT connection of
its own, so closing the app does not stop messages from arriving. The connection
itself lives one app further along, in tech.weyn.badgecontroller, which is why this screen
can tell "no broker" apart from "no Badge app at all": those need different
things done about them.
"""

import lvgl as lv

from mpos import Activity, Intent

import messages_service as service
from msgsettings import MessagesSettings


def _const(name, *spellings, **kw):
    """Resolve an LVGL constant across the spellings this build might use.

    lv.ANIM is missing on the Fri3d 2026 firmware while lv.ANIM_OFF exists,
    and that pattern repeats. Resolve, do not assume.
    """
    default = kw.get("default")
    for spelling in spellings:
        parts = spelling.split(".")
        obj = lv
        ok = True
        for part in parts:
            if not hasattr(obj, part):
                ok = False
                break
            obj = getattr(obj, part)
        if ok:
            return obj
    return default


WRAP = _const("wrap", "label.LONG_MODE.WRAP", "LABEL_LONG.WRAP",
              "LABEL_LONG_WRAP", default=None)
DISABLED = _const("disabled", "STATE.DISABLED", "STATE_DISABLED", default=None)
CENTERED = _const("center", "TEXT_ALIGN.CENTER", "TEXT_ALIGN_CENTER",
                  default=None)
ALIGN_TOP_RIGHT = _const("top_right", "ALIGN.TOP_RIGHT", "ALIGN_TOP_RIGHT",
                         default=None)
ALIGN_BOTTOM_LEFT = _const("bottom_left", "ALIGN.BOTTOM_LEFT",
                           "ALIGN_BOTTOM_LEFT", default=None)

COL_BG = 0x1A1A2E
COL_DIM = 0x8890A0
COL_TEXT = 0xFFFFFF
COL_NEW = 0xFFCC00
COL_OK = 0x44AA44
COL_WARN = 0xCC5555


def _font(*names):
    for name in names:
        font = getattr(lv, name, None)
        if font is not None:
            return font
    return None


def _gear():
    symbol = getattr(getattr(lv, "SYMBOL", None), "SETTINGS", None)
    if isinstance(symbol, str) and symbol:
        return symbol
    return "cfg"


class Messages(Activity):

    def __init__(self):
        super().__init__()
        self._shown_state = None
        self._shown_seq = -1
        self._shown_connected = None
        self._shown_name = None
        self._frame_cb = None

    # --- lifecycle ---------------------------------------------------------

    def onCreate(self):
        self.screen = lv.obj()
        self.screen.set_style_bg_color(lv.color_hex(COL_BG), 0)
        self.screen.set_style_pad_all(8, 0)

        self.title = lv.label(self.screen)
        self.title.set_text("")
        self.title.align(lv.ALIGN.TOP_LEFT, 0, 0)
        self.title.set_style_text_color(lv.color_hex(COL_DIM), 0)

        self.link = lv.label(self.screen)
        self.link.set_text("")
        if ALIGN_TOP_RIGHT is not None:
            self.link.align(ALIGN_TOP_RIGHT, 0, 0)
        else:
            self.link.align(lv.ALIGN.TOP_MID, 90, 0)
        self.link.set_style_text_color(lv.color_hex(COL_DIM), 0)

        self.msg_label = lv.label(self.screen)
        self.msg_label.set_width(288)
        if WRAP is not None:
            self.msg_label.set_long_mode(WRAP)
        if CENTERED is not None:
            self.msg_label.set_style_text_align(CENTERED, 0)
        self.msg_label.set_style_text_color(lv.color_hex(COL_TEXT), 0)
        font = _font("font_montserrat_24", "font_montserrat_20")
        if font is not None:
            self.msg_label.set_style_text_font(font, 0)
        self.msg_label.align(lv.ALIGN.CENTER, 0, -34)
        self.msg_label.set_text("Geen berichten")

        # When a message says "over 10 minuten", the useful thing is knowing
        # when those ten minutes started.
        self.time_label = lv.label(self.screen)
        self.time_label.set_text("")
        self.time_label.align(lv.ALIGN.CENTER, 0, 22)
        self.time_label.set_style_text_color(lv.color_hex(COL_DIM), 0)

        self.status_label = lv.label(self.screen)
        self.status_label.set_text("")
        self.status_label.align(lv.ALIGN.CENTER, 0, 48)
        self.status_label.set_style_text_color(lv.color_hex(COL_DIM), 0)

        self.ack_btn = lv.button(self.screen)
        self.ack_btn.set_size(170, 50)
        self.ack_btn.align(lv.ALIGN.BOTTOM_MID, 0, -6)
        self.ack_btn.add_event_cb(self._on_ack, lv.EVENT.CLICKED, None)
        ack_label = lv.label(self.ack_btn)
        ack_label.set_text("Ontvangen!")
        ack_label.center()

        # Out of the way at the bottom left: a child needs it once, to type
        # their name, and never again. Finger-sized anyway, because a control
        # you cannot hit is a control that does not exist.
        self.gear_btn = lv.button(self.screen)
        self.gear_btn.set_size(56, 50)
        if ALIGN_BOTTOM_LEFT is not None:
            self.gear_btn.align(ALIGN_BOTTOM_LEFT, 0, -6)
        else:
            self.gear_btn.align(lv.ALIGN.BOTTOM_MID, -128, -6)
        self.gear_btn.add_event_cb(self._on_settings, lv.EVENT.CLICKED, None)
        gear_label = lv.label(self.gear_btn)
        gear_label.set_text(_gear())
        gear_label.center()

        # The badge d-pad drives whatever sits in the default focus group, so
        # both buttons work without touching the screen.
        group = lv.group_get_default()
        if group:
            group.add_obj(self.ack_btn)
            group.add_obj(self.gear_btn)

        self._set_enabled(False)
        self.setContentView(self.screen)

    def onResume(self, screen):
        super().onResume(screen)
        self._shown_seq = -1          # force a repaint on every entry
        self._shown_connected = None
        self._shown_name = None       # the name may have changed in settings
        self._tick_on()
        self._refresh()

    def onPause(self, screen):
        super().onPause(screen)
        self._tick_off()

    # --- per-frame polling -------------------------------------------------
    # The service owns the state and cannot call into the UI, so the screen
    # polls. Cheap: it compares two integers and returns.

    def _tick_on(self):
        if self._frame_cb is not None:
            return
        self._frame_cb = self._on_frame
        try:
            import mpos.ui
            mpos.ui.task_handler.add_event_cb(self._frame_cb, 1)
            return
        except Exception:
            pass
        try:
            self._timer = lv.timer_create(self._on_timer, 500, None)
        except Exception:
            self._frame_cb = None

    def _tick_off(self):
        if self._frame_cb is None:
            return
        try:
            import mpos.ui
            mpos.ui.task_handler.remove_event_cb(self._frame_cb)
        except Exception:
            pass
        timer = getattr(self, "_timer", None)
        if timer is not None:
            try:
                timer.delete()
            except Exception:
                pass
            self._timer = None
        self._frame_cb = None

    def _on_frame(self, a, b):
        self._refresh()

    def _on_timer(self, timer):
        self._refresh()

    # --- rendering ---------------------------------------------------------

    def _refresh(self):
        # The name and the link are borrowed from the Badge app, and that app's
        # service may start after this one. Ask again every frame rather than
        # trusting what was true at onCreate.
        service.sync_bridge()
        # Includes whether an acknowledgement is still waiting for a link, so
        # "Bevestigd, niet verzonden" turns into "Bevestigd" by itself once it
        # goes out, without the child having to touch anything.
        state = (service.last_message_seq, service.acked_seq,
                 service.pending_ack is not None)
        if state != self._shown_state:
            self._shown_state = state
            self._shown_seq = state[0]
            self._paint_message(state[0])
        self._paint_link()
        self._paint_name()

    def _paint_name(self):
        name = service.CHILD_NAME
        if name == self._shown_name:
            return
        self._shown_name = name
        self.title.set_text(service.titlecase(name))

    def _paint_message(self, seq):
        if seq <= 0:
            self.msg_label.set_text("Geen berichten")
            self.time_label.set_text("")
            self._status("", COL_DIM)
            self._set_enabled(False)
            return
        self.msg_label.set_text(service.last_message or "")
        clock = service.clock_text(service.last_message_time)
        self.time_label.set_text("gestuurd om " + clock if clock else "")
        if seq > service.acked_seq:
            self._status("Nieuw bericht!", COL_NEW)
            self._set_enabled(True)
        elif service.pending_ack is not None:
            self._status("Bevestigd, nog niet verzonden", COL_WARN)
            self._set_enabled(False)
        else:
            self._status("Bevestigd", COL_OK)
            self._set_enabled(False)

    def _paint_link(self):
        # Op de verbinding alleen cachen was fout: er zijn twee manieren om niet
        # verbonden te zijn, en de overgang van de ene naar de andere verandert
        # `online` niet. Dan bleef er "geen verbinding" staan terwijl de Badge-app
        # intussen helemaal weg was, en dat stuurt iemand een uur zijn wifi
        # nakijken. Cache op wat er te zien is, niet op een deel ervan.
        online = bool(service.connected)
        toestand = (online, service.bridge_missing_reason())
        if toestand == self._shown_connected:
            return
        self._shown_connected = toestand
        if online:
            self.link.set_text("verbonden")
            self.link.set_style_text_color(lv.color_hex(COL_DIM), 0)
        else:
            # "geen Badge-app" and "geen verbinding" call for different repairs:
            # one is an app that is not installed or not started, the other is a
            # broker that is not answering. Saying only the second would send
            # someone to check their WiFi for an hour.
            self.link.set_text("geen Badge-app"
                               if service.bridge_missing_reason()
                               else "geen verbinding")
            self.link.set_style_text_color(lv.color_hex(COL_WARN), 0)

    def _status(self, text, color):
        self.status_label.set_text(text)
        self.status_label.set_style_text_color(lv.color_hex(color), 0)

    def _set_enabled(self, enabled):
        if DISABLED is None:
            return
        if enabled:
            self.ack_btn.remove_state(DISABLED)
        else:
            self.ack_btn.add_state(DISABLED)

    # --- input -------------------------------------------------------------

    def _on_ack(self, event):
        seq = service.last_message_seq
        if seq <= 0 or seq <= service.acked_seq:
            return
        sent = service.publish_ack(seq)
        self._set_enabled(False)
        if sent:
            self._status("Bevestigd", COL_OK)
        else:
            # Read on the badge but not delivered. Say so rather than showing a
            # green tick nobody in the kitchen will see. It is held and sent
            # when the link returns, and then this line changes by itself.
            self._status("Bevestigd, nog niet verzonden", COL_WARN)
        self._shown_state = (service.last_message_seq, service.acked_seq,
                             service.pending_ack is not None)
        self._shown_seq = service.last_message_seq

    def _on_settings(self, event):
        self.startActivity(Intent(activity_class=MessagesSettings))
