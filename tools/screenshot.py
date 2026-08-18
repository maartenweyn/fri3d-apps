"""Een schermafdruk van de badge, klein genoeg om over de seriële lijn te halen.

    badge_run_file tools/screenshot.py

Schrijft /tmp/shot.b64 en print hoe groot dat geworden is. Lees dat daarna in
stukken uit en zet het met tools/shot_to_png.py om naar een PNG.

Waarom niet de rauwe pixels: 320 bij 240 in RGB565 is 153600 bytes, en base64
maakt daar 204800 tekens van. Dat leest niemand door een REPL. Deze schermen
zijn platte vlakken met wat tekst erop, dus lopende lengtes comprimeren ze tot
een fractie: een klokscherm is bijna helemaal zwart en haalt makkelijk honderd
keer minder.

Het `deflate` van deze firmware kan alleen uitpakken en niet inpakken, dus het
gaat met de hand. De pixels worden daarbij als 16-bits gelezen via een
memoryview met cast en niet als twee losse bytes met een verschuiving erbij;
dat scheelt op de badge het verschil tussen ruim een minuut en een halve.

Het formaat is bewust dom, zodat de kant die het uitpakt in tien regels past:
per lengte vier bytes, twee voor de kleur zoals LVGL hem opslaat en twee voor
het aantal, allebei little-endian. Daarna base64, want dit gaat door een REPL.

`all_layers=True` is niet optioneel voor deze apps: het klokscherm van de
Badge-app hangt in lv.layer_top() en staat zonder dat niet op de afdruk.
"""

import gc

import lvgl as lv
import ubinascii

from mpos.ui.testing import capture_screenshot

BREEDTE = 320
HOOGTE = 240
UIT = "/tmp/shot.b64"
MAX_LENGTE = 0xFFFF


def rle(buf):
    """De pixels als lopende lengtes, vier bytes per lengte."""
    pixels = memoryview(buf).cast("H")
    uit = bytearray()
    kleur = -1
    aantal = 0
    for i in range(len(pixels)):
        p = pixels[i]
        if p == kleur and aantal < MAX_LENGTE:
            aantal += 1
            continue
        if aantal:
            uit.append(kleur & 0xFF)
            uit.append((kleur >> 8) & 0xFF)
            uit.append(aantal & 0xFF)
            uit.append((aantal >> 8) & 0xFF)
        kleur = p
        aantal = 1
    if aantal:
        uit.append(kleur & 0xFF)
        uit.append((kleur >> 8) & 0xFF)
        uit.append(aantal & 0xFF)
        uit.append((aantal >> 8) & 0xFF)
    return uit


def main():
    gc.collect()
    buf = capture_screenshot(None, width=BREEDTE, height=HOOGTE,
                             color_format=lv.COLOR_FORMAT.RGB565,
                             all_layers=True)
    ruw = len(buf)
    gepakt = rle(buf)
    del buf
    gc.collect()
    tekst = ubinascii.b2a_base64(gepakt).decode().strip()
    with open(UIT, "w") as fh:
        fh.write(tekst)
    print("rauw", ruw, "-> lengtes", len(gepakt), "-> base64", len(tekst))
    print("geschreven naar", UIT)


main()
