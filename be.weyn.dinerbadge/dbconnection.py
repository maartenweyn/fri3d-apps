"""Broker settings for Berichtjes, on the badge itself.

Its own screen rather than four more rows on the settings screen, for the same
reason that screen does not scroll: everything has to fit, because a scrollable
container turns a tap that drifts into a scroll and the button reads as dead.

With these here, nothing sensitive has to live in a file. A fresh badge can be
set up entirely on the badge, and dinerbadge_config.py only supplies starting
values for a badge nobody has configured yet.

The password is never shown. Editing it starts from an empty field and an empty
result keeps what is stored, so a child reading over a shoulder learns nothing
and the value cannot be lost by accident.
"""

import lvgl as lv

from mpos import Activity, Intent, InputActivity

import dinerbadge_service as service

try:
    from mpos import SharedPreferences
except Exception:
    from mpos.config import SharedPreferences

COL_DIM = 0x8890A0
COL_OK = 0x44AA44
COL_WARN = 0xCC5555

ROW_HEIGHT = 38


class DinerBadgeConnection(Activity):

    def __init__(self):
        super().__init__()
        self.host = ""
        self.port = 1883
        self.user = ""
        self.password = ""
        self.labels = {}
        self._frame_cb = None
        self._shown_status = None

    # --- lifecycle ---------------------------------------------------------

    def onCreate(self):
        self.host = service.MQTT_BROKER or ""
        self.port = int(service.MQTT_PORT or 1883)
        self.user = service.MQTT_USER or ""
        self.password = service.MQTT_PASS or ""

        screen = lv.obj()
        screen.set_style_pad_all(8, 0)
        screen.set_style_pad_row(6, 0)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self._no_scroll(screen)

        title = lv.label(screen)
        title.set_text("Verbinding")
        title.set_style_text_color(lv.color_hex(COL_DIM), 0)

        # What the service is actually doing, which is the thing you want to
        # see while typing an address in.
        self.status = lv.label(screen)
        self._paint_status()

        self._field(screen, "host", "Broker", lambda: self.host or "leeg")
        self._field(screen, "port", "Poort", lambda: str(self.port))
        self._field(screen, "user", "Gebruiker", lambda: self.user or "geen")
        self._field(screen, "pass", "Wachtwoord",
                    lambda: "ingesteld" if self.password else "geen")

        self.setContentView(screen)

    def onResume(self, screen):
        super().onResume(screen)
        # A status painted once is a status that lies within seconds. Someone
        # standing here has just changed an address and is waiting to see
        # whether it took.
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

    # --- rendering ---------------------------------------------------------

    def status_text(self):
        if service.connected:
            return "verbonden met " + (service.MQTT_BROKER or "?")
        reason = service.last_error
        return "geen verbinding" if not reason else "geen verbinding: " + reason

    def _paint_status(self):
        if getattr(self, "status", None) is None:
            return
        text = self.status_text()
        if text == self._shown_status:
            return
        self._shown_status = text
        self.status.set_text(text)
        self.status.set_style_text_color(
            lv.color_hex(COL_OK if service.connected else COL_WARN), 0)

    def _refresh(self, key):
        label, text = self.labels[key]
        label.set_text("%s: %s" % (text[0], text[1]()))

    # --- fields ------------------------------------------------------------

    def _field(self, parent, key, name, value):
        btn = lv.button(parent)
        btn.set_size(lv.pct(100), ROW_HEIGHT)
        btn.add_event_cb(lambda event, k=key: self._edit(k),
                         lv.EVENT.CLICKED, None)
        label = lv.label(btn)
        label.center()
        self.labels[key] = (label, (name, value))
        self._refresh(key)
        self._focusable(btn)
        return label

    def _edit(self, key):
        name, _ = self.labels[key][1]
        setting = {"title": name, "key": key, "ui": "textarea"}
        if key == "host":
            setting["placeholder"] = "IP of hostnaam"
            setting["note"] = "Het IP van Home Assistant werkt betrouwbaarder " \
                              "dan een .local naam op een ESP32."
            value = self.host
        elif key == "port":
            setting["placeholder"] = "1883"
            setting["note"] = "Standaard 1883."
            value = str(self.port)
        elif key == "user":
            setting["placeholder"] = "leeg voor anoniem"
            setting["note"] = "De Mosquitto add-on laat anonieme clients " \
                              "standaard niet toe."
            value = self.user
        else:
            setting["placeholder"] = "leeg laten om te bewaren"
            setting["note"] = "Wordt niet weergegeven. Leeg laten houdt het " \
                              "huidige wachtwoord."
            value = ""            # never show the stored one back
        intent = Intent(activity_class=InputActivity)
        intent.putExtra("setting", setting)
        intent.putExtra("value", value)
        self.startActivityForResult(intent, lambda result, k=key:
                                    self._result(k, result))

    def _result(self, key, result):
        if not result or not result.get("result_code"):
            return
        typed = ((result.get("data") or {}).get("value") or "").strip()
        if key == "host":
            if typed:
                self.host = typed
        elif key == "port":
            port = service.normalize_port(typed)
            if port:
                self.port = port
        elif key == "user":
            self.user = typed          # empty means anonymous, which is valid
        else:
            if typed:                  # empty keeps the stored password
                self.password = typed
        self._refresh(key)

    # --- plumbing ----------------------------------------------------------

    def _no_scroll(self, obj):
        try:
            obj.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        except Exception:
            pass
        for spelling in ("SCROLLABLE", "SCROLL_ELASTIC", "SCROLL_MOMENTUM"):
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

    def _save(self):
        try:
            editor = SharedPreferences(service.PREFS_APP_ID).edit()
            editor.put_string("mqtt_host", self.host)
            editor.put_int("mqtt_port", int(self.port))
            editor.put_string("mqtt_user", self.user)
            editor.put_string("mqtt_pass", self.password)
            editor.commit()
        except Exception as e:
            print("dinerbadge connection: could not save:", e)
        # Applying drops the connection and reconnects, which is the only way to
        # find out whether what you typed works.
        service.load_prefs()
