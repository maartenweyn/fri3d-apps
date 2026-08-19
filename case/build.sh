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

echo "Renders..."
render() {  # part outfile camera size
  openscad -o "images/$2.png" --imgsize="$4" --colorscheme=Tomorrow --camera="$3" \
           -D "part=\"$1\"" fri3d_badge_2026_case.scad 2>/dev/null
}
mkdir -p images
render assembly   01_case                     0,0,-8,60,0,25,360   1500,1050
render exploded   02_exploded                 0,0,4,64,0,28,430    1400,1200
render backshell  03_back                     0,0,-10,235,0,200,360 1400,950
render docked     04_dock                     0,-6,22,72,0,20,470  1500,1050
render dock       05_dock_alone               0,0,18,66,0,30,350   1300,1000
render frontplate 07_front_plate              0,0,20,0,0,0,190     1500,800
render frontplate 08_front_plate_underside    0,0,0,180,0,180,190  1500,820
render backshell  10_inside                   0,0,-6,55,0,20,360   1400,950

echo "Drawings..."
python3 make_sticker.py && mv cover_sticker_A4.pdf pdf/ && mv cover_sticker.svg pdf/
python3 make_ports.py   && mv openings.pdf pdf/openings_A4.pdf && mv openings.svg pdf/
mv cover_sticker.png images/06_cover_sticker.png
mv openings.png      images/09_openings.png
echo "done"
