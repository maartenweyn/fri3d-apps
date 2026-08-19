"""Zet de base64 van tools/screenshot.py om naar een PNG.

    python3 tools/shot_to_png.py shot.b64 shot.png [schaal]

Het formaat staat beschreven in tools/screenshot.py. Kort: een kop met de
afmetingen en een palet, daarna een byte per lopende lengte.

Het overhalen zelf gaat door een REPL, en daar gaat het mis als je een muur
base64 in één stuk overneemt: een tekenreeks van zevenduizend tekens waarin
dezelfde letter twintig keer achter elkaar staat is met de hand niet
betrouwbaar over te tikken. Print hem daarom genummerd, in regels van 96, en
plak de nummers mee. Dan is een ontbrekende of dubbele regel meteen te zien in
plaats van pas bij de md5 aan het eind:

    d = open("/tmp/shot.b64").read()
    for i in range(0, len(d), 96):
        print("%02d|%s" % (i // 96, d[i:i+96]))

Controleer daarna altijd de md5 tegen die op de badge voor je de PNG maakt.
"""

import base64
import struct
import sys
import zlib

HERHAALD = 255


def lees(pad):
    ruw = base64.b64decode(open(pad).read().strip())
    if ruw[:3] != b"BS2":
        raise SystemExit("geen BS2-afdruk: %r" % ruw[:3])
    breedte, hoogte, n = struct.unpack("<HHB", ruw[3:8])
    palet = struct.unpack("<%dH" % n, ruw[8:8 + n * 2])
    return breedte, hoogte, palet, ruw[8 + n * 2:]


def pixels(breedte, hoogte, palet, romp):
    rijen = []
    rij = []
    i = 0
    while len(rijen) < hoogte:
        if i >= len(romp):
            raise SystemExit("romp op na %d rijen" % len(rijen))
        b = romp[i]
        i += 1
        if b == HERHAALD:
            if rij:
                raise SystemExit("herhaalde rij midden in een rij")
            rijen.append(rijen[-1])
            continue
        kleur = palet[b >> 2]
        aantal = b & 3
        if aantal == 0:
            aantal = romp[i]
            i += 1
        rij.extend([kleur] * aantal)
        if len(rij) >= breedte:
            if len(rij) != breedte:
                raise SystemExit("rij %d is %d breed" % (len(rijen), len(rij)))
            rijen.append(rij)
            rij = []
    return rijen


def scanlijnen(rijen, schaal):
    """PNG-ruwe bytes: per rij een filterbyte 0 en daarna RGB per pixel."""
    uit = bytearray()
    for rij in rijen:
        for _ in range(schaal):
            uit.append(0)
            for p in rij:
                r = (p >> 11) & 0x1F
                g = (p >> 5) & 0x3F
                b = p & 0x1F
                drie = bytes((r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2))
                uit += drie * schaal
    return uit


def brok(soort, data):
    kop = soort + data
    return (struct.pack(">I", len(data)) + kop
            + struct.pack(">I", zlib.crc32(kop) & 0xFFFFFFFF))


def main():
    bron, doel = sys.argv[1], sys.argv[2]
    schaal = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    breedte, hoogte, palet, romp = lees(bron)
    rijen = pixels(breedte, hoogte, palet, romp)
    ruw = scanlijnen(rijen, schaal)
    kop = struct.pack(">IIBBBBB", breedte * schaal, hoogte * schaal,
                      8, 2, 0, 0, 0)
    with open(doel, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(brok(b"IHDR", kop))
        fh.write(brok(b"IDAT", zlib.compress(bytes(ruw), 9)))
        fh.write(brok(b"IEND", b""))
    print("geschreven %s (%d, %d)" % (doel, breedte * schaal, hoogte * schaal))


main()
