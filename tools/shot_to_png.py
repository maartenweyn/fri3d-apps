"""Zet de schermafdruk van de badge om naar een PNG.

    python3 shot_to_png.py shot.b64 uit.png [schaal]

Het bestand komt uit tools/screenshot.py op de badge: per lopende lengte vier
bytes, twee voor de kleur in RGB565 en twee voor het aantal, allebei
little-endian, en het geheel daarna base64. Standaard wordt er twee keer
vergroot, want 320 bij 240 is klein in een README.
"""
import base64
import sys

from PIL import Image

BREEDTE, HOOGTE = 320, 240


def main():
    bron, doel = sys.argv[1], sys.argv[2]
    schaal = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    ruw = base64.b64decode("".join(open(bron).read().split()))
    pixels = []
    for i in range(0, len(ruw), 4):
        kleur = ruw[i] | (ruw[i + 1] << 8)
        aantal = ruw[i + 2] | (ruw[i + 3] << 8)
        pixels.extend([_rgb888(kleur)] * aantal)
    if len(pixels) != BREEDTE * HOOGTE:
        print("let op: %d pixels, verwacht %d"
              % (len(pixels), BREEDTE * HOOGTE))
        pixels = (pixels + [(0, 0, 0)] * (BREEDTE * HOOGTE))[:BREEDTE * HOOGTE]
    beeld = Image.new("RGB", (BREEDTE, HOOGTE))
    beeld.putdata(pixels)
    if schaal > 1:
        beeld = beeld.resize((BREEDTE * schaal, HOOGTE * schaal), Image.NEAREST)
    beeld.save(doel)
    print("geschreven", doel, beeld.size)


def _rgb888(w):
    """RGB565 uitrekken naar acht bits per kanaal.

    31 moet 255 worden en niet 248, anders is wit net geen wit."""
    return (((w >> 11) & 0x1F) * 255 + 15) // 31, \
           (((w >> 5) & 0x3F) * 255 + 31) // 63, \
           ((w & 0x1F) * 255 + 15) // 31


main()
