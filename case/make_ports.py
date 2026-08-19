"""Tekening van alle randopeningen in de behuizing, uit dezelfde maten als de scad."""
import cairosvg
from shapely.geometry import Polygon

FIT, WALL = 0.30, 2.40
BACK_Z, DECK_Z1 = -15.99, 3.80
outline = [(-55.5,27),(55.5,27),(56.2803,26.9229),(57.0305,26.6951),(57.7219,26.3254),
(58.328,25.828),(58.8254,25.2219),(59.1951,24.5305),(59.4229,23.7803),(59.5,23),
(59.5,-25),(59.4317,-25.5176),(59.2318,-25.9998),(58.914,-26.414),(58.4998,-26.7318),
(58.0176,-26.9317),(57.5,-27),(-57.5,-27),(-58.0176,-26.9317),(-58.4998,-26.7318),
(-58.914,-26.414),(-59.2318,-25.9998),(-59.4317,-25.5176),(-59.5,-25),(-59.5,23),
(-59.4229,23.7803),(-59.1951,24.5305),(-58.8254,25.2219),(-58.328,25.828),
(-57.7219,26.3254),(-57.0305,26.6951),(-56.2803,26.9229)]
outer = Polygon(outline).buffer(FIT + WALL, join_style=1, quad_segs=32)

# naam, rand, x0, x1, z0, z1
PORTS = [
    ("Audio, 3.5 mm TRRS", "boven", -44.35, -36.25, -7.40, -0.50),
    ("USB-C",              "boven",  22.20,  32.80, -5.70,  0.40),
    ("microSD",            "onder",  14.90,  28.20, -4.30, -0.20),
    ("Aan/uit, SW4",       "onder", -34.50, -24.00, -4.20, -0.50),
]

S  = 1.25                       # schaal van de tekening
PW, PH = 297.0, 210.0           # A4 liggend
PLAN_CY = 71.0
def sx(x): return 148.5 + x*S
def sy(y): return PLAN_CY - y*S
def ez(z, base): return base - (z - BACK_Z)*S

def txt(x, y, t, size=3.4, anchor="start", w=400, fill="#3c3c38", ls=0):
    return (f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="{anchor}" font-family="DejaVu Sans, '
            f'Helvetica, Arial, sans-serif" font-weight="{w}" font-size="{size}" '
            f'letter-spacing="{ls}" fill="{fill}">{t}</text>')

g = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{PW}mm" height="{PH}mm" viewBox="0 0 {PW} {PH}">',
     f'<rect width="{PW}" height="{PH}" fill="#ffffff"/>']
g.append(txt(18, 15, "Fri3d badge 2026 - alle openingen in de behuizing", 6.2, w=700, fill="#1c1c1a"))
g.append(txt(18, 22, "Vier stuks, alle vier in de lange randen. De korte kanten links en rechts zijn dicht, "
                     "net als de rug en de voorkant. De LoRa-antenne is dicht gelaten.", 3.4, fill="#6b6b64"))

# ---- plattegrond
pts = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in outer.exterior.coords)
g.append(f'<polygon points="{pts}" fill="#f0efe9" stroke="#3c3c38" stroke-width="0.5"/>')
g.append(txt(sx(-62.2), sy(0)+1.2, "plattegrond", 3.2, fill="#a8a49a"))

for naam, rand, x0, x1, z0, z1 in PORTS:
    yb = 29.7 if rand == "boven" else -29.7
    yy = sy(yb)
    g.append(f'<rect x="{sx(x0):.2f}" y="{yy-1.5:.2f}" width="{(x1-x0)*S:.2f}" height="3.0" fill="#c9312a"/>')
    lx = sx((x0+x1)/2)
    ly = yy + (-7 if rand == "boven" else 7)
    g.append(f'<path d="M {lx:.2f},{yy:.2f} L {lx:.2f},{ly:.2f}" stroke="#c9312a" stroke-width="0.3"/>')
    g.append(txt(lx, ly + (-1.6 if rand == "boven" else 4.2), naam, 3.4, "middle", w=700, fill="#c9312a"))

# ---- aanzichten van de twee lange randen
for rand, base, kop in [("boven", 157.0, "bovenrand, van buitenaf gezien"),
                        ("onder", 200.0, "onderrand, van buitenaf gezien")]:
    top = ez(DECK_Z1, base)
    g.append(f'<rect x="{sx(-62.2):.2f}" y="{top:.2f}" width="{124.4*S:.2f}" '
             f'height="{(DECK_Z1-BACK_Z)*S:.2f}" fill="#f0efe9" stroke="#3c3c38" stroke-width="0.5"/>')
    g.append(f'<path d="M {sx(-62.2):.2f},{ez(0.9,base):.2f} L {sx(62.2):.2f},{ez(0.9,base):.2f}" '
             f'stroke="#a8a49a" stroke-width="0.3" stroke-dasharray="2,1.5"/>')
    g.append(txt(sx(-62.2), top - 2.6, kop, 3.4, w=600, fill="#6b6b64"))
    g.append(txt(sx(-62.2)+2.0, ez(0.9,base)-1.3, "naad frontplaat / achterschaal", 2.6, fill="#a8a49a"))
    for naam, r, x0, x1, z0, z1 in PORTS:
        if r != rand: continue
        g.append(f'<rect x="{sx(x0):.2f}" y="{ez(z1,base):.2f}" width="{(x1-x0)*S:.2f}" '
                 f'height="{(z1-z0)*S:.2f}" fill="#c9312a"/>')
        g.append(txt(sx((x0+x1)/2), ez(z0,base)+4.0, naam, 3.0, "middle", w=700, fill="#c9312a"))
        g.append(txt(sx((x0+x1)/2), ez(z0,base)+8.0,
                     f"{x1-x0:.1f} x {z1-z0:.1f} mm", 2.7, "middle", fill="#6b6b64"))

g.append(txt(18, PH-6, "Gegenereerd uit fri3d_badge_2026_case.scad, module edge_ports(). "
            "Buitenmaat behuizing 124,4 x 59,4 x 22,9 mm. Exacte coordinaten staan in LEESMIJ.md.",
            2.8, fill="#a8a49a"))
g.append('</svg>')
open("openingen.svg","w").write("\n".join(g))
cairosvg.svg2pdf(url="openingen.svg", write_to="openingen.pdf")
cairosvg.svg2png(url="openingen.svg", write_to="openingen.png", scale=4)
print("ok")
