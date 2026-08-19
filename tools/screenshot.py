"""Een schermafdruk van de badge, klein genoeg om over de seriële lijn te halen.

    badge_run_file tools/screenshot.py

Schrijft /tmp/shot.b64 en print hoe groot dat geworden is. Lees dat daarna in
genummerde regels uit en zet het met tools/shot_to_png.py om naar een PNG.

Waarom niet de rauwe pixels: 320 bij 240 in RGB565 is 153600 bytes, en base64
maakt daar 204800 tekens van. Dat leest niemand door een REPL. Deze schermen
zijn platte vlakken met wat tekst erop, dus ze comprimeren tot een fractie.

Het `deflate` van deze firmware kan alleen uitpakken en niet inpakken, dus het
gaat met de hand. De pixels worden in één keer uitgepakt met `struct` en daarna
als tuple doorlopen. Twee andere wegen vallen af: `memoryview.cast` bestaat hier
niet, en de bytes twee aan twee lezen met een verschuiving erbij duurt ruim een
minuut, wat langer is dan een aanroep over de seriële lijn mag duren.

Drie dingen maken het klein, in volgorde van opbrengst:

  Een palet. Een instelscherm haalt zelden meer dan zestig kleuren, ook met
  antialiasing, dus een verwijzing van zes bits vervangt twee bytes kleur.

  Lopende lengtes van één tot drie in datzelfde byte. Antialiasing van tekst
  levert vooral hele korte lengtes op, en die zijn met de kleur samen één byte
  in plaats van vier.

  Rijen die gelijk zijn aan de rij erboven, met één teken afgedaan. Een knop van
  veertig pixels hoog is veertig keer dezelfde rij, en de vergelijking van twee
  plakjes bytes gebeurt in C.

Samen scheelt dat een factor dertig: een instelscherm gaat van 204800 tekens
naar ongeveer zevenduizend.

Het formaat:

    "BS2" breedte:u16 hoogte:u16 aantal:u8 palet:u16*aantal romp

  romp, per byte:
    255       neem de vorige rij nog een keer
    anders    kleur = byte >> 2, lengte = byte & 3
              lengte 0 betekent: de lengte staat in het volgende byte

Alle getallen little-endian. Daarna base64, want dit gaat door een REPL.

`all_layers=True` is niet optioneel voor deze apps: het klokscherm van de
Badge-app hangt in lv.layer_top() en staat zonder dat niet op de afdruk.
"""

import gc
import struct

import lvgl as lv
import ubinascii

from mpos.ui.testing import capture_screenshot

BREEDTE = 320
HOOGTE = 240
UIT = "/tmp/shot.b64"
RIJ_HERHAALD = 255
MAX_PALET = 63          # 63 << 2 | 3 is 255, en dat is de herhaalde rij


def palet(buf):
    """De kleuren die echt voorkomen, meest gebruikte eerst."""
    telling = {}
    rij_bytes = BREEDTE * 2
    for y in range(HOOGTE):
        rij = buf[y * rij_bytes:(y + 1) * rij_bytes]
        for p in struct.unpack("<%dH" % BREEDTE, rij):
            telling[p] = telling.get(p, 0) + 1
    kleuren = sorted(telling, key=lambda k: -telling[k])
    if len(kleuren) > MAX_PALET:
        raise ValueError("%d kleuren, meer dan het palet aankan" % len(kleuren))
    return kleuren


def pak(buf, index):
    """De pixels als lopende lengtes, per rij, met herhaalde rijen ingekort."""
    uit = bytearray()
    rij_bytes = BREEDTE * 2
    for y in range(HOOGTE):
        begin = y * rij_bytes
        rij = buf[begin:begin + rij_bytes]
        if y and rij == buf[begin - rij_bytes:begin]:
            uit.append(RIJ_HERHAALD)
            continue
        kleur = -1
        aantal = 0
        for p in struct.unpack("<%dH" % BREEDTE, rij):
            if p == kleur and aantal < 255:
                aantal += 1
                continue
            if aantal:
                _lengte(uit, index[kleur], aantal)
            kleur = p
            aantal = 1
        if aantal:
            _lengte(uit, index[kleur], aantal)
    return uit


def _lengte(uit, i, aantal):
    if aantal <= 3:
        uit.append((i << 2) | aantal)
        return
    uit.append(i << 2)
    uit.append(aantal)


def main():
    gc.collect()
    buf = capture_screenshot(None, width=BREEDTE, height=HOOGTE,
                             color_format=lv.COLOR_FORMAT.RGB565,
                             all_layers=True)
    ruw = len(buf)
    kleuren = palet(buf)
    index = {k: i for i, k in enumerate(kleuren)}
    kop = bytearray(b"BS2")
    kop += struct.pack("<HHB", BREEDTE, HOOGTE, len(kleuren))
    for k in kleuren:
        kop += struct.pack("<H", k)
    gepakt = kop + pak(buf, index)
    del buf
    gc.collect()
    tekst = ubinascii.b2a_base64(gepakt).decode().strip()
    with open(UIT, "w") as fh:
        fh.write(tekst)
    print("rauw", ruw, "-> palet", len(kleuren), "-> gepakt", len(gepakt),
          "-> base64", len(tekst))
    print("geschreven naar", UIT)


main()
