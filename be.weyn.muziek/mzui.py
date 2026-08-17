"""Gedeelde LVGL-bouwstenen voor de vier schermen van Muziek.

Twee lessen uit Berichtjes zitten hier ingebakken.

Constantes worden opgezocht, niet aangenomen. Deze firmware heeft
`lv.label.LONG_MODE.WRAP` en geen `lv.LABEL_LONG_WRAP`, en dat patroon herhaalt
zich. `zoek()` probeert de spellingen op volgorde en geeft None als geen ervan
bestaat, zodat de aanroeper kan overslaan in plaats van te crashen.

De functie heet met opzet niet `const`. Een module-level `NAAM = const(...)`
wordt door de MicroPython-compiler onderschept als een constantendeclaratie, en
die eist een constante uitdrukking: de hele module valt om met
`SyntaxError: not a constant`, nog voor er iets draait. Op desktop merk je daar
niets van.

En scrollen is besmettelijk. Op een scrollbaar element maakt LVGL van een tik
die een paar pixels meebeweegt een scroll, en annuleert de klik. Een knop voelt
dan kapot. Schermen die passen krijgen daarom `no_scroll`; alleen de lijsten
scrollen echt, en daar zijn de rijen 44 hoog zodat een vinger raak is.
"""

import lvgl as lv

# 240 hoog min 8 padding boven en onder.
SCHERM_H = 224
SCHERM_B = 304
RIJ_H = 44
RIJ_GAP = 6

COL_BG = 0x141824
COL_DIM = 0x8890A0
COL_TEXT = 0xFFFFFF
COL_ACCENT = 0x3FBF7F
COL_WARN = 0xCC5555


def color(hexwaarde):
    return lv.color_hex(hexwaarde)


def zoek(*spellings, **kw):
    standaard = kw.get("default")
    for spelling in spellings:
        obj = lv
        ok = True
        for deel in spelling.split("."):
            if not hasattr(obj, deel):
                ok = False
                break
            obj = getattr(obj, deel)
        if ok:
            return obj
    return standaard


WRAP = zoek("label.LONG_MODE.WRAP", "LABEL_LONG.WRAP", "LABEL_LONG_WRAP")
DOTS = zoek("label.LONG_MODE.DOTS", "LABEL_LONG.DOT", "LABEL_LONG_DOT")
DISABLED = zoek("STATE.DISABLED", "STATE_DISABLED")
CENTER = zoek("TEXT_ALIGN.CENTER", "TEXT_ALIGN_CENTER")
TOP_RIGHT = zoek("ALIGN.TOP_RIGHT", "ALIGN_TOP_RIGHT")


def symbol(naam, terugval):
    """lv.SYMBOL.PLAY en vrienden, met tekst als de build ze niet heeft."""
    s = getattr(getattr(lv, "SYMBOL", None), naam, None)
    return s if isinstance(s, str) and s else terugval


SYM_PLAY = symbol("PLAY", ">")
SYM_PAUSE = symbol("PAUSE", "||")
SYM_PREV = symbol("PREV", "|<")
SYM_NEXT = symbol("NEXT", ">|")
SYM_LIST = symbol("LIST", "lijst")
SYM_BELL = symbol("BELL", "wekker")
SYM_REFRESH = symbol("REFRESH", "verver")
SYM_LEFT = symbol("LEFT", "<")


def font(*namen):
    for naam in namen:
        f = getattr(lv, naam, None)
        if f is not None:
            return f
    return None


def no_scroll(obj):
    try:
        obj.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    except Exception:
        pass
    for spelling in ("SCROLLABLE", "SCROLL_ELASTIC", "SCROLL_MOMENTUM",
                     "SCROLL_CHAIN_HOR", "SCROLL_CHAIN_VER"):
        vlag = getattr(getattr(lv.obj, "FLAG", None), spelling, None)
        if vlag is None:
            vlag = getattr(lv, "OBJ_FLAG_" + spelling, None)
        if vlag is None:
            continue
        try:
            obj.remove_flag(vlag)
        except Exception:
            try:
                obj.clear_flag(vlag)
            except Exception:
                pass


def focusable(obj):
    """In de standaardgroep, zodat de d-pad van de badge het ding ook bedient."""
    try:
        groep = lv.group_get_default()
        if groep:
            groep.add_obj(obj)
    except Exception:
        pass


def scherm():
    s = lv.obj()
    s.set_style_bg_color(lv.color_hex(COL_BG), 0)
    s.set_style_pad_all(8, 0)
    s.set_style_pad_row(RIJ_GAP, 0)
    s.set_style_border_width(0, 0)
    s.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    no_scroll(s)
    return s


def label(ouder, tekst="", kleur=COL_TEXT, lettertype=None, breedte=None):
    l = lv.label(ouder)
    l.set_text(tekst)
    l.set_style_text_color(lv.color_hex(kleur), 0)
    if lettertype is not None:
        l.set_style_text_font(lettertype, 0)
    if breedte is not None:
        l.set_width(breedte)
        if DOTS is not None:
            l.set_long_mode(DOTS)
    return l


def rij(ouder, hoogte=None, gap=8):
    r = lv.obj(ouder)
    r.set_size(lv.pct(100), hoogte or lv.SIZE_CONTENT)
    r.set_style_border_width(0, 0)
    r.set_style_bg_opa(lv.OPA.TRANSP, 0)
    r.set_style_pad_all(0, 0)
    r.set_style_pad_column(gap, 0)
    no_scroll(r)
    r.set_flex_flow(lv.FLEX_FLOW.ROW)
    r.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER,
                     lv.FLEX_ALIGN.CENTER)
    return r


def knop(ouder, tekst, cb, breedte=None, hoogte=RIJ_H, grow=None):
    b = lv.button(ouder)
    if grow:
        b.set_height(hoogte)
        try:
            b.set_flex_grow(grow)
        except Exception:
            b.set_width(breedte or 80)
    else:
        b.set_size(breedte if breedte is not None else lv.pct(100), hoogte)
    b.add_event_cb(lambda e, f=cb: f(), lv.EVENT.CLICKED, None)
    l = lv.label(b)
    l.set_text(tekst)
    l.center()
    focusable(b)
    return b, l


def lijst(ouder):
    """Een scrollbare kolom voor rijen die niet op het scherm passen."""
    c = lv.obj(ouder)
    c.set_width(lv.pct(100))
    try:
        c.set_flex_grow(1)
    except Exception:
        c.set_height(150)
    c.set_style_border_width(0, 0)
    c.set_style_bg_opa(lv.OPA.TRANSP, 0)
    c.set_style_pad_all(0, 0)
    c.set_style_pad_row(4, 0)
    c.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    try:
        c.set_scrollbar_mode(lv.SCROLLBAR_MODE.AUTO)
    except Exception:
        pass
    return c


def leeg(obj):
    try:
        obj.clean()
    except Exception:
        for kind in list(getattr(obj, "children", []) or []):
            try:
                kind.delete()
            except Exception:
                pass


def kort(tekst, n):
    """Afkappen zonder str-methodes die MicroPython niet heeft."""
    if tekst is None:
        return ""
    return tekst if len(tekst) <= n else tekst[:n - 1] + "…"
