"""Huis: een handvol knoppen die Home Assistant uitvoert.

Dit scherm kent geen entiteiten en geen services. Home Assistant publiceert
retained op `home/badges/<naam>/control_panel` welke knoppen deze badge heeft,
en hier wordt getekend wat er binnenkomt. Een badge waar nooit iets naartoe
gepubliceerd is heeft dus een leeg paneel, en dat is meteen de aan-en-uitknop:
één badge knoppen geven is één keer publiceren.

Twee dingen die dit scherm hard maakt.

**Een knop liegt niet.** Bij een druk gaat hij in afwachting, niet meteen om. Hij
gaat om als de toestand die eraan hangt verandert, of als Home Assistant een ack
stuurt. Komt er niets, dan staat er dat er niets terugkwam. Dit is dezelfde les
als het verbindingslabel van Berichtjes: cache op wat er te zien is, niet op een
deel ervan.

**Wat je niet per ongeluk wil doen vraagt twee tikken.** Een knop met
`confirm` in zijn configuratie wacht op een tweede tik binnen vier seconden.

Over de layout: knoppen zijn minstens 44 hoog en het raster scrollt niet. Op een
scrollbare container maakt LVGL van een tik die een paar pixels meebeweegt een
scroll, en dan is de knop dood terwijl elke test slaagt.
"""

import time

import lvgl as lv

from mpos import Activity

import hcpanel as service


def _lv_const(*spellings, **kw):
    """Een LVGL-constante over de spellingen die deze build kan hebben."""
    default = kw.get("default")
    for spelling in spellings:
        obj = lv
        ok = True
        for part in spelling.split("."):
            if not hasattr(obj, part):
                ok = False
                break
            obj = getattr(obj, part)
        if ok:
            return obj
    return default


CENTERED = _lv_const("TEXT_ALIGN.CENTER", "TEXT_ALIGN_CENTER", default=None)
ALIGN_TOP_RIGHT = _lv_const("ALIGN.TOP_RIGHT", "ALIGN_TOP_RIGHT", default=None)
WRAP = _lv_const("label.LONG_MODE.WRAP", default=None)

COL_BG = 0x1A1A2E
COL_DIM = 0x8890A0
COL_TEXT = 0xFFFFFF
COL_OK = 0x44AA44
COL_WARN = 0xCC5555
COL_BUSY = 0xE0A030

PAD = 6
HEADER = 22

# Onder de 44 is een knop een knop die je niet raakt. Twee knoppen krijgen de
# volle breedte, daarboven twee kolommen: op 320 is dat 152 per knop, en dat is
# ruim genoeg voor een opschrift van achttien tekens.
MIN_CELL = 44


def grid(count, width=320, height=240):
    """(kolommen, rijen, celbreedte, celhoogte) voor zoveel knoppen.

    Apart van het tekenen, zodat de maten na te rekenen zijn zonder scherm. Zes
    is het maximum dat de service doorlaat; bij zes is de cel 60 hoog en dat is
    nog altijd ruim boven MIN_CELL.
    """
    count = max(1, int(count))
    cols = 1 if count <= 2 else 2
    rows = (count + cols - 1) // cols
    avail_w = width - 2 * PAD
    avail_h = height - 2 * PAD - HEADER
    cell_w = (avail_w - (cols - 1) * PAD) // cols
    cell_h = (avail_h - (rows - 1) * PAD) // rows
    return cols, rows, cell_w, cell_h


def _font(*names):
    for name in names:
        font = getattr(lv, name, None)
        if font is not None:
            return font
    return None


def _hex(value, default=COL_TEXT):
    """Een kleur uit de configuratie, of de standaard.

    Komt van het netwerk, dus alles wat geen zes hexcijfers is wordt genegeerd
    in plaats van een uitzondering te worden midden in het tekenen.
    """
    if not value:
        return default
    text = str(value).strip()
    if text[:1] == "#":
        text = text[1:]
    try:
        return int(text, 16)
    except Exception:
        return default


def _symbol(name):
    symbols = getattr(lv, "SYMBOL", None)
    value = getattr(symbols, str(name).upper(), None) if symbols else None
    return value if isinstance(value, str) and value else None


class HomeControl(Activity):

    def __init__(self):
        super().__init__()
        self.screen = None
        self.heading = None
        self.status = None
        self.holder = None
        self.tiles = {}           # knop-id -> (knop, toestandslabel)
        self._painted = None      # (panel_seq,), zodat we niet elke frame een
                                  # raster opnieuw opbouwen
        self._shown = None        # wat er nu op de knoppen staat
        self._armed = None        # (knop-id, deadline) voor een bevestiging
        self._frame_cb = None
        self._timer = None

    # --- lifecycle ---------------------------------------------------------

    def onCreate(self):
        service.load_cached_panel()

        self.screen = lv.obj()
        self.screen.set_style_bg_color(lv.color_hex(COL_BG), 0)
        self.screen.set_style_pad_all(PAD, 0)
        self.screen.set_style_border_width(0, 0)
        self._no_scroll(self.screen)

        self.heading = lv.label(self.screen)
        self.heading.set_text(service.panel_title)
        self.heading.align(lv.ALIGN.TOP_LEFT, 0, 0)
        self.heading.set_style_text_color(lv.color_hex(COL_DIM), 0)

        self.status = lv.label(self.screen)
        self.status.set_text("")
        if ALIGN_TOP_RIGHT is not None:
            self.status.align(ALIGN_TOP_RIGHT, 0, 0)
        else:
            self.status.align(lv.ALIGN.TOP_MID, 90, 0)
        self.status.set_style_text_color(lv.color_hex(COL_DIM), 0)

        # Alle knoppen hangen hieronder, zodat een nieuw paneel één clean() is
        # in plaats van bijhouden wat er allemaal getekend was.
        self.holder = lv.obj(self.screen)
        self.holder.set_size(320 - 2 * PAD, 240 - 2 * PAD - HEADER)
        self.holder.set_pos(0, HEADER)
        self.holder.set_style_bg_opa(lv.OPA.TRANSP, 0)
        self.holder.set_style_border_width(0, 0)
        self.holder.set_style_pad_all(0, 0)
        self._no_scroll(self.holder)

        self.setContentView(self.screen)

    def onResume(self, screen):
        super().onResume(screen)
        service.reset()
        self._armed = None
        self._painted = None        # bij binnenkomst altijd opnieuw tekenen
        self._shown = None
        service.sync_bridge()
        service.subscribe_all()
        self._tick_on()
        self._refresh()

    def onPause(self, screen):
        super().onPause(screen)
        self._tick_off()
        # Geen abonnement laten staan voor een scherm waar niemand naar kijkt.
        # De retained berichten komen bij het volgende openen vanzelf opnieuw.
        service.unsubscribe_all()

    # --- per frame ---------------------------------------------------------

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
        if self._timer is not None:
            try:
                self._timer.delete()
            except Exception:
                pass
            self._timer = None
        self._frame_cb = None

    def _on_frame(self, a, b):
        self._refresh()

    def _on_timer(self, timer):
        self._refresh()

    # --- tekenen -----------------------------------------------------------

    def _refresh(self):
        service.sync_bridge()
        service.subscribe_all()
        service.tick()
        now = time.time()
        if self._armed is not None and now >= self._armed[1]:
            self._armed = None
        if service.panel_seq != self._painted:
            self._painted = service.panel_seq
            self._shown = None
            self._paint()
        self._paint_states()

    def _paint(self):
        self.heading.set_text(service.panel_title)
        self.holder.clean()
        self.tiles = {}
        items = service.buttons
        if not items:
            hint = lv.label(self.holder)
            hint.set_width(320 - 2 * PAD - 8)
            if WRAP is not None:
                hint.set_long_mode(WRAP)
            if CENTERED is not None:
                hint.set_style_text_align(CENTERED, 0)
            hint.set_style_text_color(lv.color_hex(COL_DIM), 0)
            hint.set_text("Geen knoppen. Home Assistant publiceert ze retained "
                          "op home/badges/%s/control_panel."
                          % (service.BADGE_NAME or "<naam>"))
            hint.align(lv.ALIGN.CENTER, 0, 0)
            return
        cols, rows, cell_w, cell_h = grid(len(items))
        for index, button in enumerate(items):
            row, col = divmod(index, cols)
            x = col * (cell_w + PAD)
            y = row * (cell_h + PAD)
            self._tile(button, x, y, cell_w, cell_h)

    def _tile(self, button, x, y, w, h):
        btn = lv.button(self.holder)
        btn.set_size(w, h)
        btn.set_pos(x, y)
        btn.set_style_pad_all(2, 0)
        btn.add_event_cb(lambda event, b=button: self._on_press(b),
                         lv.EVENT.CLICKED, None)
        self._focusable(btn)

        label = lv.label(btn)
        text = button.get("label") or ""
        mark = _symbol(button.get("symbol")) or button.get("initial")
        if mark:
            text = "%s %s" % (mark, text)
        label.set_text(text)
        label.set_width(w - 8)
        if WRAP is not None:
            label.set_long_mode(WRAP)
        if CENTERED is not None:
            label.set_style_text_align(CENTERED, 0)
        font = _font("font_montserrat_16", "font_montserrat_14")
        if font is not None:
            label.set_style_text_font(font, 0)
        label.set_style_text_color(lv.color_hex(_hex(button.get("color"))), 0)
        label.align(lv.ALIGN.TOP_MID, 0, 4)
        self._inert(label)

        # De toestandsregel onderaan. Leeg voor een knop zonder sleutel, en dat
        # is geen gebrek: een scene heeft geen toestand.
        note = lv.label(btn)
        note.set_text("")
        font = _font("font_montserrat_14")
        if font is not None:
            note.set_style_text_font(font, 0)
        note.set_style_text_color(lv.color_hex(COL_DIM), 0)
        note.align(lv.ALIGN.BOTTOM_MID, 0, -2)
        self._inert(note)

        self.tiles[button.get("id")] = (btn, note)
        return btn

    def _paint_states(self):
        """Wat er onder op elke knop staat, en de statusregel.

        Op één plek, zodat de knop en de regel eronder niet uit elkaar kunnen
        lopen. Cache op alles wat er te zien is: alleen op de toestandsteller
        cachen zou een wachtende knop laten staan tot er toevallig iets anders
        verandert.
        """
        shown = (service.state_seq, len(service.pending), len(service.results),
                 self._armed[0] if self._armed else None,
                 service.connected, service.last_error)
        if shown == self._shown:
            return
        self._shown = shown

        for button in service.buttons:
            tile = self.tiles.get(button.get("id"))
            if tile is None:
                continue
            btn, note = tile
            kind, text = service.status_of(button)
            if self._armed is not None and self._armed[0] == button.get("id"):
                note.set_text("nog eens")
                note.set_style_text_color(lv.color_hex(COL_BUSY), 0)
                continue
            if kind == "wacht":
                note.set_text("...")
                note.set_style_text_color(lv.color_hex(COL_BUSY), 0)
                continue
            if kind == "ok":
                note.set_text(text or "ok")
                note.set_style_text_color(lv.color_hex(COL_OK), 0)
                continue
            if kind == "fout":
                note.set_text(text or "mislukt")
                note.set_style_text_color(lv.color_hex(COL_WARN), 0)
                continue
            entry = service.state_of(button)
            if entry is None:
                note.set_text("")
                continue
            note.set_text(entry.get("text") or "")
            note.set_style_text_color(
                lv.color_hex(_hex(entry.get("color"), COL_DIM)), 0)

        if service.connected:
            self._say("", COL_DIM)
        else:
            self._say(service.last_error or "geen verbinding", COL_WARN)

    # --- helpers -----------------------------------------------------------

    def _no_scroll(self, obj):
        try:
            obj.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        except Exception:
            pass
        self._drop_flags(obj, ("SCROLLABLE", "SCROLL_ELASTIC", "SCROLL_MOMENTUM",
                               "SCROLL_CHAIN_HOR", "SCROLL_CHAIN_VER"))

    def _inert(self, obj):
        """Een opschrift mag de tik niet opeten die voor de knop bedoeld is."""
        self._drop_flags(obj, ("CLICKABLE", "CLICK_FOCUSABLE", "PRESS_LOCK"))

    def _drop_flags(self, obj, spellings):
        for spelling in spellings:
            flag = getattr(getattr(lv.obj, "FLAG", None), spelling, None)
            if flag is None:
                flag = getattr(lv, "OBJ_FLAG_" + spelling, None)
            if flag is None:
                continue
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

    def _say(self, text, color):
        if self.status is None:
            return
        self.status.set_text(text)
        self.status.set_style_text_color(lv.color_hex(color), 0)

    # --- invoer ------------------------------------------------------------

    def _on_press(self, button):
        ident = button.get("id")
        if button.get("confirm"):
            armed = self._armed
            if armed is None or armed[0] != ident:
                # Eerste tik: alleen scherpstellen. Een alarm dat aangaat omdat
                # iemand de badge oppakte is geen alarm.
                self._armed = (ident, time.time() + service.CONFIRM_SECONDS)
                self._shown = None
                self._paint_states()
                return
        self._armed = None
        if not service.press(button):
            # Geen wachtstand voor iets dat de deur niet uit is. Wat er mis ging
            # staat erbij, want "geen verbinding" en "Badge-app draait niet"
            # vragen om iets heel anders.
            service.results[ident] = {
                "ok": False,
                "text": service.press_error or "niet verstuurd",
                "until": time.time() + service.FLASH_SECONDS,
            }
        self._shown = None
        self._paint_states()
