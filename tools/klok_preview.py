"""Het klokscherm tekenen zonder badge.

Draait `bgclock` tegen de lvgl-stub uit de tests en tekent na wat er op het
scherm zou staan. Bedoeld om een layout te beoordelen als de badge niet aan de
Mac hangt: past de temperatuur naast het pictogram, is de max leesbaar, botsen
de twee helften niet.

    python3 tools/klok_preview.py [uitvoermap]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tests", "stubs"))
sys.path.insert(0, os.path.join(ROOT, "tech.weyn.badgecontroller"))
sys.dont_write_bytecode = True

import lvgl as lv                                 # noqa: E402
import bgclock                                    # noqa: E402
import lv_render                                  # noqa: E402

GEVALLEN = (
    ("zonnige-dag-met-bui", {"toestand": "cloudy", "dag": "sunny",
                             "regen": True, "nu": 12.4, "max": 21, "min": 11}),
    ("regen", {"toestand": "rainy", "dag": "rainy", "regen": True,
               "nu": 12.4, "max": 15, "min": 8}),
    ("zonnig-en-droog", {"toestand": "sunny", "dag": "sunny", "regen": False,
                         "nu": 24.8, "max": 27, "min": 16}),
    ("zonder-weerbericht", {}),
)


def main(uit):
    maten = lv_render.font_maten(lv)
    for naam, weer in GEVALLEN:
        klok = bgclock.ClockOverlay()
        klok.toon()
        klok.werk_bij("07:16", "ma 24 aug", 84, weer, "Slaapkamer")
        print(lv_render.teken(klok.root.children,
                              os.path.join(uit, "klok-%s.png" % naam),
                              maten, lv=lv))
        klok.weg()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp")
