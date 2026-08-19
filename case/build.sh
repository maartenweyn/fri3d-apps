#!/usr/bin/env bash
# Bouwt alle onderdelen opnieuw uit fri3d_badge_2026_case.scad.
# Nodig: openscad, python3 met shapely en cairosvg.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p stl pdf

echo "STL's..."
openscad -o stl/01_achterschaal.stl --export-format binstl -D 'part="backshell"'  fri3d_badge_2026_case.scad
openscad -o stl/02_frontplaat.stl   --export-format binstl -D 'part="frontplate"' fri3d_badge_2026_case.scad
openscad -o stl/03_dock.stl         --export-format binstl -D 'part="dock"'       fri3d_badge_2026_case.scad

echo "Botsingscontrole, alle drie horen leeg te zijn..."
for c in check check2 check3; do
  openscad -o /tmp/$c.stl -D "part=\"$c\"" fri3d_badge_2026_case.scad 2>/dev/null
  s=$(stat -f%z /tmp/$c.stl 2>/dev/null || stat -c%s /tmp/$c.stl)
  if [ "$s" -gt 200 ]; then echo "  $c: BOTSING, $s bytes"; else echo "  $c: leeg, ok"; fi
done

echo "Tekeningen..."
python3 make_sticker.py && mv sticker_front_A4.pdf pdf/coversticker_A4.pdf && mv sticker_front.svg pdf/coversticker.svg
python3 make_ports.py   && mv openingen.pdf pdf/openingen_A4.pdf && mv openingen.svg pdf/openingen.svg
rm -f sticker_front.png openingen.png
echo "klaar"
