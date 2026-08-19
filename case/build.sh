#!/usr/bin/env bash
# Rebuilds every part from fri3d_badge_2026_case.scad.
# Needs: openscad, and python3 with shapely and cairosvg.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p stl pdf

echo "STLs..."
openscad -o stl/01_back_shell.stl  --export-format binstl -D 'part="backshell"'  fri3d_badge_2026_case.scad
openscad -o stl/02_front_plate.stl --export-format binstl -D 'part="frontplate"' fri3d_badge_2026_case.scad
openscad -o stl/03_dock.stl        --export-format binstl -D 'part="dock"'       fri3d_badge_2026_case.scad

echo "Interference checks, all three have to come out empty..."
for c in check check2 check3; do
  openscad -o /tmp/$c.stl -D "part=\"$c\"" fri3d_badge_2026_case.scad 2>/dev/null
  s=$(stat -f%z /tmp/$c.stl 2>/dev/null || stat -c%s /tmp/$c.stl)
  if [ "$s" -gt 200 ]; then echo "  $c: INTERFERENCE, $s bytes"; else echo "  $c: empty, ok"; fi
done

echo "Drawings..."
python3 make_sticker.py && mv cover_sticker_A4.pdf pdf/ && mv cover_sticker.svg pdf/
python3 make_ports.py   && mv openings.pdf pdf/openings_A4.pdf && mv openings.svg pdf/
rm -f cover_sticker.png openings.png
echo "done"
