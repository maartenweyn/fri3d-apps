#!/usr/bin/env bash
# Rebuilds every part, drawing and image from fri3d_badge_2026_case.scad.
# Needs: openscad, and python3 with shapely and cairosvg. Install trimesh too
# and the interference checks report a volume instead of a file size.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p stl pdf images

echo "STLs..."
openscad -o stl/01_back_shell.stl  --export-format binstl -D 'part="backshell"'  fri3d_badge_2026_case.scad
openscad -o stl/02_front_plate.stl --export-format binstl -D 'part="frontplate"' fri3d_badge_2026_case.scad
openscad -o stl/03_dock.stl        --export-format binstl -D 'part="dock"'       fri3d_badge_2026_case.scad

echo "Interference checks, all three have to come out at zero volume..."
for c in check check2 check3; do
  rm -f "/tmp/$c.stl"
  # An empty result is the good outcome and openscad exits non-zero for it, so
  # that failure has to be swallowed or set -e kills the build right here.
  openscad -o "/tmp/$c.stl" -D "part=\"$c\"" fri3d_badge_2026_case.scad >/dev/null 2>&1 || true
  if [ ! -s "/tmp/$c.stl" ]; then
    echo "  $c: empty, ok"
    continue
  fi
  # A non-empty file is not a problem by itself. Where two parts touch, the
  # boolean leaves coincident-surface slivers with no volume. Only volume counts.
  python3 -c '
import sys
c = sys.argv[1]
try:
    import trimesh
except ImportError:
    print("  " + c + ": non-empty, install trimesh to judge whether it has volume")
    sys.exit(0)
v = abs(trimesh.load("/tmp/" + c + ".stl").volume)
verdict = " INTERFERENCE" if v > 0.01 else ", contact faces only, ok"
print("  " + c + ": " + format(v, ".3f") + " mm3" + verdict)
' "$c"
done

echo "Renders..."
render() {  # part  outfile  camera  size
  echo "  $2"
  openscad -o "images/$2.png" --imgsize="$4" --colorscheme=Tomorrow --camera="$3" \
           -D "part=\"$1\"" fri3d_badge_2026_case.scad >/dev/null 2>&1
}
render assembly   01_case                   0,0,-8,60,0,25,360    1500,1050
render exploded   02_exploded               0,0,4,64,0,28,430     1400,1200
render backshell  03_back                   0,0,-10,235,0,200,360 1400,950
render docked     04_dock                   0,-6,22,72,0,20,470   1500,1050
render dock       05_dock_alone             0,0,18,66,0,30,350    1300,1000
render frontplate 07_front_plate            0,0,20,0,0,0,190      1500,800
render frontplate 08_front_plate_underside  0,0,0,180,0,180,190   1500,820
render backshell  10_inside                 0,0,-6,55,0,20,360    1400,950

echo "Drawings..."
python3 make_sticker.py
mv cover_sticker_A4.pdf pdf/
mv cover_sticker.svg    pdf/
mv cover_sticker.png    images/06_cover_sticker.png
python3 make_ports.py
mv openings.pdf pdf/openings_A4.pdf
mv openings.svg pdf/
mv openings.png images/09_openings.png

echo "done"
