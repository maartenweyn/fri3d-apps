"""Het scherm van Updates: wat er gebeurd is, en drie knoppen.

Het echte werk zit in de service, die ook draait als dit scherm nooit geopend
wordt. Dit scherm is er om te zien of het werkt en om er iets aan te veranderen.

Drie rijen van 44 met gaten van 6, een titel en een statusblok: dat is precies
wat er in 240 past zonder te scrollen. Dat is geen schoonheid maar noodzaak,
want op een scrollbare container maakt LVGL van een tik die een paar pixels
meebeweegt een scroll, en dan lijkt de knop kapot.
"""

import time

import lvgl as lv

from mpos import Activity, Intent, InputActivity

import autoupdate_service as service

COL_DIM = 0x8890A0
COL_OK = 0x44AA44
COL_WARN = 0xCC5555

ROW_HEIGHT = 44
ROW_GAP = 6


class AutoUpdate(Activity):

    def __init__(self):
        super().__init__()
        self.status = None
        self.check_label = None
        self.auto_label = None
        self.index_label = None
        self._shown = None
        self._frame_cb = None

    # --- levenscyclus ------------------------------------------------------

    def onCreate(self):
        screen = lv.obj()
        screen.set_style_pad_all(8, 0)
        screen.set_style_pad_row(ROW_GAP, 0)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self._no_scroll(screen)

        title = lv.label(screen)
        title.set_text("Updates")
        title.set_style_text_color(lv.color_hex(COL_DIM), 0)

        self.check_label = self._wide_button(screen, "Nu controleren",
                                             self._check)
        self.auto_label = self._wide_button(screen, self._auto_text,
                                            self._toggle_auto)
        self.index_label = self._wide_button(screen, self._index_text,
                                             self._edit_index)

        self.status = lv.label(screen)
        self.status.set_width(lv.pct(100))
        try:
            self.status.set_long_mode(lv.label.LONG_MODE.WRAP)
        except Exception:
            pass
        self._paint()

        self.setContentView(screen)

    def onResume(self, screen):
        super().onResume(screen)
        self._paint()
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
        super().onPause(screen)

    def _on_frame(self, a, b):
        self._paint()

    # --- tekenen -----------------------------------------------------------

    def status_text(self):
        if service.state == "checking":
            return "bezig met controleren..."
        if service.state == "error":
            return "laatste poging mislukt: " + (service.last_error or "onbekend")

        regels = []
        if service.last_check:
            regels.append("gecontroleerd " + ago(service.last_check))
        else:
            regels.append("nog niet gecontroleerd")

        gedaan = [n for n in service.last_run
                  if n.get("uitkomst") in ("bijgewerkt", "nieuw")]
        if gedaan:
            namen = [service.short_name(n["fullname"]) + " " + str(n["naar"])
                     for n in gedaan]
            regels.append("bijgewerkt: " + ", ".join(namen))
        elif service.catalog:
            regels.append("%d app%s in de index, alles bij" % (
                len(service.catalog), "" if len(service.catalog) == 1 else "s"))

        if service.reboot_advised:
            regels.append("herstart nodig voor de achtergronddelen")
        return "\n".join(regels)

    def _paint(self):
        if self.status is None:
            return
        text = self.status_text()
        if text != self._shown:
            self._shown = text
            self.status.set_text(text)
            self.status.set_style_text_color(
                lv.color_hex(COL_WARN if service.state == "error" else COL_DIM), 0)
        if self.auto_label is not None:
            self.auto_label.set_text(self._auto_text())
        if self.index_label is not None:
            self.index_label.set_text(self._index_text())

    def _auto_text(self):
        return "Automatisch: " + ("aan" if service.auto_install else "uit")

    def _index_text(self):
        return "Index: " + host_of(service.index_url)

    # --- knoppen -----------------------------------------------------------

    def _check(self):
        service.request_check()
        self._paint()

    def _toggle_auto(self):
        service.set_auto_install(not service.auto_install)
        self._paint()

    def _edit_index(self):
        """Doorgeven aan het invoerscherm van het OS, dat het toetsenbord bezit."""
        intent = Intent(activity_class=InputActivity)
        intent.putExtra("setting", {
            "title": "URL van de app-index",
            "key": "index_url",
            "ui": "textarea",
            "placeholder": "http://192.168.68.100:8123/local/appstore/app_index.json",
            "note": "Het app_index.json dat tools/publish.sh schrijft. "
                    "Downloads die naast de index staan mogen relatief.",
        })
        intent.putExtra("value", service.index_url)
        self.startActivityForResult(intent, self._index_result)

    def _index_result(self, result):
        if not result or not result.get("result_code"):
            return                       # geannuleerd of weggeveegd
        typed = (result.get("data") or {}).get("value") or ""
        if not service.set_index_url(typed):
            print("autoupdate: %r is geen bruikbare URL" % typed)
            return
        self._paint()

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


def host_of(url):
    """`http://host:8123/local/...` -> `host:8123`. Een URL past niet op een knop."""
    rest = url
    cut = rest.find("://")
    if cut >= 0:
        rest = rest[cut + 3:]
    slash = rest.find("/")
    return rest[:slash] if slash > 0 else rest


def ago(when):
    """Verstreken tijd in woorden.

    Met opzet relatief: `time.localtime()` geeft op deze badge UTC, ook met de
    tijdzone goed ingesteld, dus een klokje hier zou er een uur naast staan.
    """
    seconds = int(time.time()) - int(when)
    if seconds < 0:
        return "zojuist"
    if seconds < 90:
        return "zojuist"
    if seconds < 3600:
        return "%d min geleden" % (seconds // 60)
    if seconds < 86400:
        uren = seconds // 3600
        return "%d uur geleden" % uren if uren > 1 else "een uur geleden"
    dagen = seconds // 86400
    return "%d dagen geleden" % dagen if dagen > 1 else "gisteren"
