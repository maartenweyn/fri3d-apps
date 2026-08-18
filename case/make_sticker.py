"""Coversticker voor de Fri3d badge 2026 behuizing.

Zelfde geometrie als fri3d_badge_2026_case.scad, op 1:1 schaal.
Levert een SVG en een PDF in millimeter.
"""
import cairosvg
from shapely.geometry import Polygon, Point, box
from shapely.ops import unary_union

# ---- geometrie, identiek aan de scad ---------------------------------------
FIT, WALL = 0.30, 2.40
outline = [(-55.5,27),(55.5,27),(56.2803,26.9229),(57.0305,26.6951),(57.7219,26.3254),
(58.328,25.828),(58.8254,25.2219),(59.1951,24.5305),(59.4229,23.7803),(59.5,23),
(59.5,-25),(59.4317,-25.5176),(59.2318,-25.9998),(58.914,-26.414),(58.4998,-26.7318),
(58.0176,-26.9317),(57.5,-27),(-57.5,-27),(-58.0176,-26.9317),(-58.4998,-26.7318),
(-58.914,-26.414),(-59.2318,-25.9998),(-59.4317,-25.5176),(-59.5,-25),(-59.5,23),
(-59.4229,23.7803),(-59.1951,24.5305),(-58.8254,25.2219),(-58.328,25.828),
(-57.7219,26.3254),(-57.0305,26.6951),(-56.2803,26.9229)]

pcb   = Polygon(outline)
outer = pcb.buffer(FIT + WALL, join_style=1, quad_segs=32)   # buitenrand frontplaat

mounts = [(-37.5,-17.5),(-32.5,23.5),(37.5,18.5),(37.5,-17.5)]
btns   = {(45.75, 9.25):"X", (54.75,-1):"A", (36.25,-1):"Y", (45.75,-11.25):"B",
          (-13.5,-22.5):None, (13.5,-22.5):None}
CL = 0.40                       # speling rond elke uitsparing
sticker = outer.buffer(-0.60)   # sticker net binnen de rand van de plaat

cuts = []
# schermrand: het verhoogde deel steekt door de sticker
bezel = box(-31.0, -13.8, 31.0, 30.0).buffer(2.0, join_style=1).buffer(-2.0).intersection(outer)
cuts.append(bezel.buffer(CL))
# joystick
cuts.append(box(-50.78,-8.15,-34.78,7.85).buffer(2.5, join_style=1).buffer(CL))
# drukknoppen
for (x,y) in btns: cuts.append(Point(x,y).buffer(3.7 + CL, quad_segs=48))
# een gaatje per LED
for x in (-20,-10,0,10,20): cuts.append(Point(x,-16.2).buffer(2.20 + CL, quad_segs=32))
# status-LED D15
cuts.append(Point(-33.27,17.1).buffer(3.7 + CL, quad_segs=32))
# geen schroef- of lanyardgaten meer: de frontplaat is aan de voorzijde dicht

sticker = sticker.difference(unary_union(cuts))
if sticker.geom_type == "MultiPolygon":
    sticker = max(sticker.geoms, key=lambda g: g.area)

# ---- svg (A4, 1:1) ---------------------------------------------------------
PW, PH = 210.0, 297.0          # A4 staand
CX, CY = PW/2, 92.0            # middelpunt van de sticker op de pagina
def T(x, y): return (CX + x, CY - y)

def path_of(poly):
    parts = []
    for ring in [poly.exterior, *poly.interiors]:
        pts = [T(*p) for p in ring.coords]
        parts.append("M " + " L ".join(f"{a:.3f},{b:.3f}" for a,b in pts) + " Z")
    return " ".join(parts)

def label(x, y, txt, size=3.6, anchor="middle", weight=700, fill="#141414", ls=0):
    a, b = T(x, y)
    return (f'<text x="{a:.2f}" y="{b + size*0.35:.2f}" text-anchor="{anchor}" '
            f'font-family="DejaVu Sans, Helvetica, Arial, sans-serif" font-weight="{weight}" '
            f'font-size="{size}" letter-spacing="{ls}" fill="{fill}">{txt}</text>')

def page_text(x, y, txt, size=3.4, anchor="start", weight=400, fill="#3c3c38", ls=0):
    return (f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="{anchor}" '
            f'font-family="DejaVu Sans, Helvetica, Arial, sans-serif" font-weight="{weight}" '
            f'font-size="{size}" letter-spacing="{ls}" fill="{fill}">{txt}</text>')

svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{PW}mm" height="{PH}mm" '
       f'viewBox="0 0 {PW} {PH}">',
       f'<rect width="{PW}" height="{PH}" fill="#ffffff"/>']

svg.append(page_text(18, 26, "Fri3d badge 2026 - coversticker frontplaat", 6.2, weight=700, fill="#1c1c1a"))
svg.append(page_text(18, 34, "Alleen de knopnamen. Print op 100 procent, zet schalen of passend maken uit.", 3.6, fill="#6b6b64"))

# vlak van de sticker
svg.append(f'<path d="{path_of(sticker)}" fill="#f0efe9" fill-rule="evenodd" '
           f'stroke="#c9312a" stroke-width="0.25"/>')

# accentvlak achter de knopgroep, netjes binnen de sticker
accent = Point(45.75,-1).buffer(15.5, quad_segs=64).intersection(sticker)
if not accent.is_empty:
    geoms = accent.geoms if accent.geom_type == "MultiPolygon" else [accent]
    for g in geoms:
        svg.append(f'<path d="{path_of(g)}" fill="#e2ded2" fill-rule="evenodd"/>')

# knoplabels
for (x,y), lab in btns.items():
    if lab is None: continue
    dx, dy = {"X":(0,6.4), "A":(0,6.4), "Y":(0,-6.6), "B":(0,-6.6)}[lab]
    svg.append(label(x+dx, y+dy, lab, size=4.6))
svg.append(label(-18.2,-22.5, "MENU", size=3.0, anchor="end", ls=0.35))
svg.append(label( 18.2,-22.5, "START", size=3.0, anchor="start", ls=0.35))

# verder geen tekst: AUDIO, LoRa en FRI3D 2026 staan in de behuizing zelf

# controlemaat
y0 = CY + 46
svg.append(f'<path d="M {CX-50:.2f},{y0:.2f} L {CX+50:.2f},{y0:.2f}" stroke="#c9312a" stroke-width="0.3"/>')
for dx in (-50, 50):
    svg.append(f'<path d="M {CX+dx:.2f},{y0-2:.2f} L {CX+dx:.2f},{y0+2:.2f}" stroke="#c9312a" stroke-width="0.3"/>')
svg.append(page_text(CX, y0+6, "controlemaat 100 mm - klopt dit niet, dan staat de schaal van je printer verkeerd",
                     3.0, anchor="middle", fill="#8d8a80"))

# uitleg
ty = CY + 66
for i, line in enumerate([
    "1.  Print dit blad op zelfklevend papier of gewoon papier met dubbelzijdige tape.",
    "2.  Snij langs de rode lijn, ook de binnenvormen. Een hobbymes op een snijmat werkt beter dan een schaar.",
    "3.  De grote opening in het midden is voor de verhoogde schermrand; die steekt door de sticker heen.",
    "4.  Leg de sticker op de frontplaat voor je het beschermlaagje weghaalt en kijk of alle gaten kloppen.",
    "5.  Lamineer hem eventueel, of spuit een laagje matte vernis, dan blijft hij leesbaar onder de duimen."]):
    svg.append(page_text(18, ty + i*7.0, line, 3.4, fill="#3c3c38"))

svg.append(page_text(18, PH-18, "Geometrie uit Fri3D_Badge_2026_02.step - knopnamen uit het schema van revisie 02",
                     2.8, fill="#a8a49a"))
svg.append('</svg>')
open("sticker_front.svg","w").write("\n".join(svg))
cairosvg.svg2pdf(url="sticker_front.svg", write_to="sticker_front_A4.pdf")
cairosvg.svg2png(url="sticker_front.svg", write_to="sticker_front.png", scale=4)
print("sticker oppervlak %.1f cm2" % (sticker.area/100))
