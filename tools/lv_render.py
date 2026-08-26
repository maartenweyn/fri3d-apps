"""Een LVGL-scherm natekenen dat tegen de teststubs gebouwd is.

De stub in `tests/stubs/lvgl.py` onthoudt van elk object zijn positie, maat,
achtergrondkleur, opaciteit, radius, tekst en lettertype. Dat is genoeg om er
een plaatje van te maken, en dat plaatje is genoeg om te beoordelen of iets van
een halve meter leesbaar is - de vraag waar een badge aan USB anders voor nodig
is.

Geen vervanging voor een echte schermafdruk: de lettertypes zijn DejaVu en niet
Montserrat, dus tekst loopt een paar procent anders. De posities en de maten
komen wel rechtstreeks uit de app.
"""

from PIL import Image, ImageDraw, ImageFont

LETTER = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BREED = 320
HOOG = 240
SCHAAL = 3

_fonts = {}


def _font(px):
    if px not in _fonts:
        _fonts[px] = ImageFont.truetype(LETTER, px)
    return _fonts[px]


def font_maten(lv):
    """Van elk montserrat-object in de stub naar zijn puntgrootte.

    De objecten hebben geen naam, dus terugzoeken gaat op identiteit."""
    maten = {}
    for m in (8, 10, 12, 14, 16, 18, 20, 24, 28):
        font = getattr(lv, "font_montserrat_%d" % m, None)
        if font is not None:
            maten[id(font)] = m
    return maten


def _uitlijning(lv):
    """Van de ALIGN-waarde naar zijn naam, om erop te kunnen kiezen."""
    namen = {}
    groep = getattr(lv, "ALIGN", None)
    if groep is None:
        return namen
    for naam in dir(groep):
        if not naam.startswith("_"):
            namen[getattr(groep, naam)] = naam
    return namen


def _plaats(obj, breedte, hoogte, ouder_w, ouder_h, namen):
    """Waar een object staat: zijn vaste positie, of waar align() het legt.

    Een scherm dat met align() gebouwd is heeft geen posities, en zonder deze
    omrekening staat alles op de linkerbovenhoek van zijn ouder gestapeld."""
    if obj.pos is not None:
        return obj.pos
    if not obj.alignment:
        return (0, 0)
    waarde, dx, dy = obj.alignment
    naam = namen.get(waarde, "TOP_LEFT")
    if "RIGHT" in naam:
        x = ouder_w - breedte
    elif "LEFT" in naam:
        x = 0
    else:
        x = (ouder_w - breedte) // 2
    if "TOP" in naam:
        y = 0
    elif "BOTTOM" in naam:
        y = ouder_h - hoogte
    else:
        y = (ouder_h - hoogte) // 2
    return (x + dx, y + dy)


def teken(kinderen, pad, maten, achtergrond="#000000", schaal=SCHAAL, lv=None):
    """Een lijst LVGL-objecten naar een PNG. Geeft het pad terug."""
    beeld = Image.new("RGB", (BREED * schaal, HOOG * schaal), achtergrond)
    tekenaar = ImageDraw.Draw(beeld)
    namen = _uitlijning(lv) if lv is not None else {}

    def loop(obj, ox=0, oy=0, ouder_w=BREED, ouder_h=HOOG):
        px = maten.get(id(obj.styles.get("text_font")), 14)
        if obj.text is not None:
            font = _font(int(px * schaal * 0.95))
            breedte = int(tekenaar.textlength(obj.text, font=font) / schaal)
            hoogte = int(px * 1.35)
        else:
            breedte, hoogte = obj.size or (ouder_w, ouder_h)
        x, y = _plaats(obj, breedte, hoogte, ouder_w, ouder_h, namen)
        x += ox
        y += oy
        stijl = obj.styles
        if obj.text is not None:
            tekenaar.text((x * schaal, y * schaal), obj.text,
                          font=_font(int(px * schaal * 0.95)),
                          fill="#%06X" % stijl.get("text_color", 0xFFFFFF))
        elif obj.size:
            # Een object dat nooit een opaciteit kreeg maar wel een kleur is
            # zichtbaar; een object dat expliciet op nul staat niet.
            opa = stijl.get("bg_opa", 255 if "bg_color" in stijl else 0)
            if opa:
                straal = min(stijl.get("radius", 0),
                             min(breedte, hoogte) // 2)
                tekenaar.rounded_rectangle(
                    [x * schaal, y * schaal,
                     (x + breedte) * schaal - 1, (y + hoogte) * schaal - 1],
                    radius=straal * schaal,
                    fill="#%06X" % stijl.get("bg_color", 0xFFFFFF))
        for kind in obj.children:
            loop(kind, x, y, breedte, hoogte)

    for kind in kinderen:
        loop(kind)
    beeld.save(pad)
    return pad
