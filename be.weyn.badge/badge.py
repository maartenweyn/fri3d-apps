"""Het instelscherm van de badge: wie hij is, waar hij praat, en zijn scherm.

Dit is de enige activity van de app. De rest gebeurt in de service, die op
`boot_completed` start en blijft draaien welke app er ook op het scherm staat.

Drie rijen, en dat is niet toevallig het maximum: de rijen scrollen niet, want
op een scrollbare container maakt LVGL van een tik die een paar pixels meebeweegt
een scroll en annuleert de klik. Het scherm is 240 hoog, 8 padding boven en
onder, dus 224 te verdelen. Een titel van 16 plus drie rijen van 44 met gaten van
6 laat ruimte voor de statusregel. Een vierde rij past niet: splits dan af naar
een eigen scherm, zoals Verbinding.
"""

import lvgl as lv

from mpos import Activity, Intent, InputActivity

import badge_service as service
from bgconnection import BadgeConnection

try:
    from mpos import SharedPreferences
except Exception:
    from mpos.config import SharedPreferences

COL_DIM = 0x8890A0
COL_OK = 0x44AA44
COL_WARN = 0xCC5555

ROW_HEIGHT = 44
ROW_GAP = 6

# Uit, en dan van kort naar lang. Onder de vijftien seconden gaat het scherm uit
# terwijl je nog aan het lezen bent; boven het kwartier is het geen besparing
# meer maar een lampje dat aan blijft.
TIMEOUTS = (0, 15, 30, 60, 120, 300, 600, 900)


def timeout_text(seconden):
    if not seconden:
        return "nooit"
    if seconden < 60:
        return "%d s" % seconden
    if seconden % 60 == 0:
        return "%d min" % (seconden // 60)
    return "%d min %d s" % (seconden // 60, seconden % 60)


class Badge(Activity):

    def __init__(self):
        super().__init__()
        self.name = ""
        self.screen_off_s = 0
        self.name_label = None
        self.timeout_label = None
        self.status = None
        self._frame_cb = None
        self._shown_status = None

    # --- levenscyclus ------------------------------------------------------

    def onCreate(self):
        self.name = service.BADGE_NAME
        self.screen_off_s = int(service.SCREEN_OFF_S or 0)

        screen = lv.obj()
        screen.set_style_pad_all(8, 0)
        screen.set_style_pad_row(ROW_GAP, 0)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self._no_scroll(screen)

        title = lv.label(screen)
        title.set_text("Badge")
        title.set_style_text_color(lv.color_hex(COL_DIM), 0)

        self.name_label = self._wide_button(screen, self._name_text,
                                            self._edit_name)
        self._wide_button(screen, lambda: "Verbinding...",
                          self._open_connection)
        self.timeout_label = self._stepper_row(screen, "Scherm uit na",
                                               self._cycle_timeout)

        self.status = lv.label(screen)
        self._paint_status()

        self.setContentView(screen)

    def onResume(self, screen):
        super().onResume(screen)
        self.name = service.BADGE_NAME
        if self.name_label is not None:
            self.name_label.set_text(self._name_text())
        self._paint_status()
        if self._frame_cb is None:
            self._frame_cb = self._on_frame
            try:
                import mpos.ui
                mpos.ui.task_handler.add_event_cb(self._frame_cb, 1)
            except Exception:
                self._frame_cb = None

    def onPause(self, screen):
        if self._frame_cb is not None:
            try:
                import mpos.ui
                mpos.ui.task_handler.remove_event_cb(self._frame_cb)
            except Exception:
                pass
            self._frame_cb = None
        self._save()
        super().onPause(screen)

    def _on_frame(self, a, b):
        self._paint_status()

    # --- tekenen -----------------------------------------------------------

    def status_text(self):
        if service.connected:
            regels = ["verbonden"]
            if service.battery_pct is not None:
                regels.append("%d%%" % service.battery_pct)
            if service.wifi_rssi is not None:
                regels.append("%d dBm" % service.wifi_rssi)
            return "  ".join(regels)
        reason = service.last_error
        return "geen verbinding" if not reason else "geen verbinding: " + reason

    def _paint_status(self):
        if self.status is None:
            return
        text = self.status_text()
        if text == self._shown_status:
            return
        self._shown_status = text
        self.status.set_text(text)
        self.status.set_style_text_color(
            lv.color_hex(COL_OK if service.connected else COL_WARN), 0)

    def _name_text(self):
        naam = service.titlecase(self.name) if self.name else "nog niet ingesteld"
        return "Deze badge: " + naam

    # --- invoer ------------------------------------------------------------

    def _edit_name(self):
        """Doorgeven aan het invoerscherm van het OS, dat het toetsenbord bezit."""
        intent = Intent(activity_class=InputActivity)
        intent.putExtra("setting", {
            "title": "Naam van deze badge",
            "key": "badge_name",
            "ui": "textarea",
            "placeholder": "bv. alice",
            "note": "Staat in de MQTT-topics en in Home Assistant. "
                    "Kleine letters, geen spaties.",
        })
        intent.putExtra("value", self.name)
        self.startActivityForResult(intent, self._name_result)

    def _name_result(self, result):
        if not result or not result.get("result_code"):
            return                       # geannuleerd of weggeveegd
        typed = (result.get("data") or {}).get("value") or ""
        cleaned = service.normalize_name(typed)
        if not cleaned:
            # Liever niets bewaren dan een naam waar nooit een bericht op
            # aankomt.
            print("badge: %r is geen bruikbare naam" % typed)
            return
        self.name = cleaned
        if self.name_label is not None:
            self.name_label.set_text(self._name_text())

    def _open_connection(self):
        self.startActivity(Intent(activity_class=BadgeConnection))

    def _cycle_timeout(self, delta):
        try:
            index = TIMEOUTS.index(self.screen_off_s)
        except ValueError:
            index = 0
        index = min(len(TIMEOUTS) - 1, max(0, index + delta))
        self.screen_off_s = TIMEOUTS[index]
        if self.timeout_label is not None:
            self.timeout_label.set_text(timeout_text(self.screen_off_s))

    # --- rijen -------------------------------------------------------------

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

    def _focusable(self, obj):
        try:
            group = lv.group_get_default()
            if group:
                group.add_obj(obj)
        except Exception:
            pass

    def _wide_button(self, parent, text, callback):
        """Schermbreed en vingergroot. Met opzet moeilijk te missen."""
        btn = lv.button(parent)
        btn.set_size(lv.pct(100), ROW_HEIGHT)
        btn.add_event_cb(lambda event, cb=callback: cb(), lv.EVENT.CLICKED, None)
        label = lv.label(btn)
        label.set_text(text() if callable(text) else text)
        label.center()
        self._focusable(btn)
        return label

    def _row(self, parent, height):
        row = lv.obj(parent)
        row.set_size(lv.pct(100), height)
        row.set_style_border_width(0, 0)
        row.set_style_bg_opa(lv.OPA.TRANSP, 0)
        row.set_style_pad_all(2, 0)
        row.set_style_pad_column(8, 0)
        self._no_scroll(row)
        row.set_flex_flow(lv.FLEX_FLOW.ROW)
        row.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER,
                           lv.FLEX_ALIGN.CENTER)
        return row

    def _step_button(self, parent, text, callback):
        btn = lv.button(parent)
        btn.set_size(48, 40)
        btn.add_event_cb(lambda event, cb=callback: cb(), lv.EVENT.CLICKED, None)
        label = lv.label(btn)
        label.set_text(text)
        label.center()
        self._focusable(btn)
        return btn

    def _stepper_row(self, parent, text, cycle):
        row = self._row(parent, ROW_HEIGHT)
        name = lv.label(row)
        name.set_text(text)
        try:
            name.set_flex_grow(1)
        except Exception:
            pass
        self._step_button(row, "-", lambda c=cycle: c(-1))
        value_label = lv.label(row)
        value_label.set_text(timeout_text(self.screen_off_s))
        self._step_button(row, "+", lambda c=cycle: c(1))
        return value_label

    # --- bewaren -----------------------------------------------------------

    def _save(self):
        name = service.normalize_name(self.name) or service.BADGE_NAME
        try:
            editor = SharedPreferences(service.PREFS_APP_ID).edit()
            editor.put_string("badge_name", name)
            editor.put_int("screen_off_s", int(self.screen_off_s))
            editor.commit()
        except Exception as e:
            print("badge instellingen: kon niet bewaren:", e)
        # Meteen toepassen. Een naamswijziging moet opnieuw abonneren, en wie
        # net zijn naam typte hoort niet te moeten herstarten.
        service.load_prefs()
