"""Sturen: een scherm vol knoppen, op de badge die mag sturen.

De app kent geen enkele naam en geen enkele tekst. Home Assistant publiceert
retained op `home/badges/<naam>/buttons` wat deze badge mag sturen, en dit
scherm tekent wat er binnenkomt. Eén node knoppen geven is dus één keer iets
publiceren, en niet een vinkje op elk toestel.

Een druk zet een verzoek op `home/badges/<naam>/send`. Niet rechtstreeks op het
`msg`-topic van de andere badge: dat werkt wel en gaat langs Home Assistant
heen, en dan blijft het dashboard grijs.

De pictogrammen zijn getekend en niet ingeladen. De symbolenfont van deze
firmware heeft geen mens erin, en een PNG meesturen zou betekenen dat de app
weet wat "een vrouw" is. Nu staat er in de configuratie `figure: woman` en tekent
dit scherm vier rechthoeken. Wat die rechthoeken voorstellen bepaalt Home
Assistant.

Over de layout: knoppen zijn minstens 44 hoog en het raster scrollt niet. Op een
scrollbare container maakt LVGL van een tik die een paar pixels meebeweegt een
scroll, en dan is de knop dood terwijl elke test slaagt.
"""

import time

import lvgl as lv

from mpos import Activity

import messages_service as service


def _const(name, *spellings, **kw):
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


CENTERED = _const("center", "TEXT_ALIGN.CENTER", "TEXT_ALIGN_CENTER",
                  default=None)
ALIGN_TOP_RIGHT = _const("top_right", "ALIGN.TOP_RIGHT", "ALIGN_TOP_RIGHT",
                         default=None)

COL_BG = 0x1A1A2E
COL_DIM = 0x8890A0
COL_TEXT = 0xFFFFFF
COL_OK = 0x44AA44
COL_WARN = 0xCC5555
COL_FIGURE = 0xFFFFFF

PAD = 6
HEADER = 22
FLASH_SECONDS = 3        # hoe lang "verstuurd" blijft staan

# Onder de 44 is een knop een knop die je niet raakt, en boven de 110 is hij
# alleen maar leeg. Twee kolommen tot vier knoppen, dan drie, dan vier.
MIN_CELL = 44
MAX_CELL = 110


def grid(count, width=320, height=240):
    """(kolommen, rijen, celbreedte, celhoogte) voor zoveel knoppen.

    Apart van het tekenen, zodat de maten na te rekenen zijn zonder scherm. Een
    cel die onder MIN_CELL zou uitkomen betekent dat er te veel knoppen zijn;
    de service kapt de lijst daarom al af op MAX_BUTTONS.
    """
    count = max(1, int(count))
    if count <= 4:
        cols = 2
    elif count <= 6:
        cols = 3
    else:
        cols = 4
    rows = (count + cols - 1) // cols
    avail_w = width - 2 * PAD
    avail_h = height - 2 * PAD - HEADER
    cell_w = (avail_w - (cols - 1) * PAD) // cols
    cell_h = (avail_h - (rows - 1) * PAD) // rows
    return cols, rows, cell_w, min(cell_h, MAX_CELL)


def _font(*names):
    for name in names:
        font = getattr(lv, name, None)
        if font is not None:
            return font
    return None


def _hex(value, default=COL_FIGURE):
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


class MessagesSend(Activity):

    def __init__(self):
        super().__init__()
        self.screen = None
        self.title = None
        self.status = None
        self.holder = None
        self._painted = None      # (buttons_seq, badgenaam), zodat we niet elke
                                  # frame een raster opnieuw opbouwen
        self._flash_until = 0
        self._frame_cb = None

    # --- lifecycle ---------------------------------------------------------

    def onCreate(self):
        self.screen = lv.obj()
        self.screen.set_style_bg_color(lv.color_hex(COL_BG), 0)
        self.screen.set_style_pad_all(PAD, 0)
        self.screen.set_style_border_width(0, 0)
        self._no_scroll(self.screen)

        self.title = lv.label(self.screen)
        self.title.set_text(service.buttons_title)
        self.title.align(lv.ALIGN.TOP_LEFT, 0, 0)
        self.title.set_style_text_color(lv.color_hex(COL_DIM), 0)

        self.status = lv.label(self.screen)
        self.status.set_text("")
        if ALIGN_TOP_RIGHT is not None:
            self.status.align(ALIGN_TOP_RIGHT, 0, 0)
        else:
            self.status.align(lv.ALIGN.TOP_MID, 90, 0)
        self.status.set_style_text_color(lv.color_hex(COL_DIM), 0)

        # Alle knoppen hangen hieronder, zodat een nieuwe configuratie één
        # clean() is in plaats van bijhouden wat er allemaal getekend was.
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
        self._painted = None        # bij binnenkomst altijd opnieuw tekenen
        self._tick_on()
        self._refresh()

    def onPause(self, screen):
        super().onPause(screen)
        self._tick_off()

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

    # --- tekenen -----------------------------------------------------------

    def _refresh(self):
        # De naam wordt van de Badge-app geleend en kan daar veranderen, en de
        # naam bepaalt welke knoppen zichtbaar zijn: naar jezelf sturen mag niet.
        service.sync_bridge()
        state = (service.buttons_seq, service.CHILD_NAME)
        if state != self._painted:
            self._painted = state
            self._paint()
        if self._flash_until and time.time() >= self._flash_until:
            self._flash_until = 0
            self._say("", COL_DIM)

    def _paint(self):
        self.title.set_text(service.buttons_title)
        self.holder.clean()
        items = service.visible_buttons()
        if not items:
            hint = lv.label(self.holder)
            hint.set_width(320 - 2 * PAD - 8)
            if CENTERED is not None:
                hint.set_style_text_align(CENTERED, 0)
            hint.set_style_text_color(lv.color_hex(COL_DIM), 0)
            hint.set_text("Geen knoppen. Home Assistant publiceert ze "
                          "retained op home/badges/%s/buttons."
                          % (service.CHILD_NAME or "<naam>"))
            hint.align(lv.ALIGN.CENTER, 0, 0)
            return
        cols, rows, cell_w, cell_h = grid(len(items))
        for index, button in enumerate(items):
            row, col = divmod(index, cols)
            x = col * (cell_w + PAD)
            y = row * (cell_h + PAD)
            self._button(button, x, y, cell_w, cell_h)

    def _button(self, button, x, y, w, h):
        btn = lv.button(self.holder)
        btn.set_size(w, h)
        btn.set_pos(x, y)
        btn.set_style_pad_all(2, 0)
        btn.add_event_cb(lambda event, b=button: self._on_press(b),
                         lv.EVENT.CLICKED, None)
        self._focusable(btn)

        color = _hex(button.get("color"))
        art_h = max(0, h - 22)
        if art_h >= 24:
            self._art(btn, button, color, min(art_h, w - 8))

        label = lv.label(btn)
        label.set_text(button.get("label") or "")
        font = _font("font_montserrat_14", "font_montserrat_16")
        if font is not None:
            label.set_style_text_font(font, 0)
        label.set_style_text_color(lv.color_hex(COL_TEXT), 0)
        label.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        return btn

    def _art(self, parent, button, color, size):
        """Het plaatje boven het opschrift: een figuur, een teken of een letter."""
        figure = (button.get("figure") or "").lower()
        if figure:
            box = lv.obj(parent)
            box.set_size(size, size)
            box.set_style_bg_opa(lv.OPA.TRANSP, 0)
            box.set_style_border_width(0, 0)
            box.set_style_pad_all(0, 0)
            box.align(lv.ALIGN.TOP_MID, 0, 0)
            self._no_scroll(box)
            self._inert(box)
            self._figure(box, figure, color, size)
            return box
        text = _symbol(button.get("symbol")) or button.get("initial")
        if not text:
            return None
        mark = lv.label(parent)
        mark.set_text(str(text)[:2])
        font = _font("font_montserrat_24", "font_montserrat_20")
        if font is not None:
            mark.set_style_text_font(font, 0)
        mark.set_style_text_color(lv.color_hex(color), 0)
        mark.align(lv.ALIGN.TOP_MID, 0, max(0, (size - 26) // 2))
        return mark

    def _figure(self, box, kind, color, s):
        """Een mannetje of een vrouwtje uit rechthoeken.

        Vier of vijf blokjes, want deze firmware heeft geen mens in zijn
        symbolenfont en een PNG meesturen zou betekenen dat de app weet wie er
        op de knop staat. Een rok is drie steeds bredere blokjes; op deze maat
        leest dat als een jurk.
        """
        def rect(cx, top, w, h, radius=0):
            obj = lv.obj(box)
            obj.set_size(max(2, int(w)), max(2, int(h)))
            obj.set_pos(int(cx - w / 2), int(top))
            obj.set_style_bg_color(lv.color_hex(color), 0)
            obj.set_style_border_width(0, 0)
            obj.set_style_pad_all(0, 0)
            obj.set_style_radius(int(radius), 0)
            self._no_scroll(obj)
            self._inert(obj)
            return obj

        mid = s / 2
        head = s * 0.28
        rect(mid, 0, head, head, head)
        if kind == "woman":
            rect(mid, s * 0.32, s * 0.34, s * 0.14)
            rect(mid, s * 0.44, s * 0.50, s * 0.14)
            rect(mid, s * 0.56, s * 0.66, s * 0.14)
            rect(mid - s * 0.11, s * 0.72, s * 0.12, s * 0.22)
            rect(mid + s * 0.11, s * 0.72, s * 0.12, s * 0.22)
        else:
            rect(mid, s * 0.32, s * 0.46, s * 0.36, s * 0.08)
            rect(mid - s * 0.12, s * 0.70, s * 0.15, s * 0.28)
            rect(mid + s * 0.12, s * 0.70, s * 0.15, s * 0.28)

    # --- helpers -----------------------------------------------------------

    def _no_scroll(self, obj):
        try:
            obj.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        except Exception:
            pass
        self._drop_flags(obj, ("SCROLLABLE", "SCROLL_ELASTIC", "SCROLL_MOMENTUM",
                               "SCROLL_CHAIN_HOR", "SCROLL_CHAIN_VER"))

    def _inert(self, obj):
        """Een versiering mag de tik niet opeten die voor de knop bedoeld is."""
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
        if service.publish_send(button):
            self._say("verstuurd", COL_OK)
        else:
            # Geen groen vinkje voor iets dat de deur niet uit is. Wat er mis
            # ging staat er ook bij, want "geen verbinding" en "Badge-app draait
            # niet" vragen om iets heel anders.
            self._say(service.send_error or "niet verstuurd", COL_WARN)
        self._flash_until = time.time() + FLASH_SECONDS
