"""Het klokscherm tekenen zonder badge.

Draait `bgclock` tegen de lvgl-stub uit de tests, leest terug welke
rechthoeken en labels er op het scherm zouden staan, en tekent dat na met
Pillow. Bedoeld om een layout te beoordelen als de badge niet aan de Mac
hangt: past de temperatuur naast het pictogram, is de max leesbaar, botsen de
twee helften niet.

Geen vervanging voor een echte schermafdruk. De lettertypes zijn DejaVu en
niet Montserrat, dus de tekst loopt een paar procent anders; de posities en de
maten komen wel rechtstreeks uit de app.

    python3 tools/klok_preview.py [uitvoermap]
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests", "stubs"))
sys.path.insert(0, os.path.join(ROOT, "tech.weyn.badgecontroller"))
sys.dont_write_bytecode = True

from PIL import Image, ImageDraw, ImageFont      # noqa: E402
import lvgl as lv                                # noqa: E402
import bgclock                                   # noqa: E402

LETTER = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
SCHAAL = 3

# Welke montserrat-maat een label kreeg is alleen te zien aan welk object de
# stub bewaarde; die objecten hebben geen naam, dus terugzoeken op identiteit.
MATEN = {id(getattr(lv, "font_montserrat_%d" % m)): m
         for m in (8, 10, 12, 14, 16, 18, 20, 24, 28)
         if hasattr(lv, "font_montserrat_%d" % m)}

_fonts = {}


def _font(px):
    if px not in _fonts:
        _fonts[px] = ImageFont.truetype(LETTER, px)
    return _fonts[px]


def teken(klok, pad):
    beeld = Image.new("RGB", (320 * SCHAAL, 240 * SCHAAL), "#000000")
    tekenaar = ImageDraw.Draw(beeld)

    def loop(obj, ox=0, oy=0):
        x, y = obj.pos or (0, 0)
        x += ox
        y += oy
        if obj.text is not None:
            px = MATEN.get(id(obj.styles.get("text_font")), 14)
            tekenaar.text((x * SCHAAL, y * SCHAAL), obj.text,
                          font=_font(int(px * SCHAAL * 0.95)),
                          fill="#%06X" % obj.styles.get("text_color", 0xFFFFFF))
        elif obj.size and obj.styles.get("bg_opa"):
            w, h = obj.size
            straal = min(obj.styles.get("radius", 0), min(w, h) // 2)
            tekenaar.rounded_rectangle(
                [x * SCHAAL, y * SCHAAL,
                 (x + w) * SCHAAL - 1, (y + h) * SCHAAL - 1],
                radius=straal * SCHAAL,
                fill="#%06X" % obj.styles.get("bg_color", 0xFFFFFF))
        for kind in obj.children:
            loop(kind, x, y)

    for kind in klok.root.children:
        loop(kind)
    beeld.save(pad)
    return pad


GEVALLEN = (
    ("zonnige-dag-met-bui", {"toestand": "cloudy", "dag": "sunny",
                             "regen": True, "nu": 12.4, "max": 21, "min": 11}),
    ("regen", {"toestand": "rainy", "dag": "rainy", "regen": True,
               "nu": 12.4, "max": 15, "min": 8}),
    ("zonnig-en-droog", {"toestand": "sunny", "dag": "sunny", "regen": False,
                         "nu": 24.8, "max": 27, "min": 16}),
    ("zonder-weerbericht", {}),
)


def main(uit):
    for naam, weer in GEVALLEN:
        klok = bgclock.ClockOverlay()
        klok.toon()
        klok.werk_bij("07:16", "ma 24 aug", 84, weer, "Slaapkamer")
        print(teken(klok, os.path.join(uit, "klok-%s.png" % naam)))
        klok.weg()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp")
