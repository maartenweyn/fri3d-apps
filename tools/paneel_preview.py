"""Het Huis-paneel tekenen zonder badge.

Zelfde truc als klok_preview, maar dan voor `tech.weyn.homecontrol`: het scherm
wordt tegen de stubs gebouwd met een nep-brug in sys.modules, precies zoals de
tests het doen, en daarna nagetekend.

Draait alle toestanden af die je anders alleen met een vinger op een badge ziet,
de bewapende alarmknop voorop - dat is degene die te weinig opviel.

    python3 tools/paneel_preview.py [uitvoermap]
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tests", "stubs"))
sys.path.insert(0, os.path.join(ROOT, "tech.weyn.homecontrol"))
sys.dont_write_bytecode = True


class NepBrug:
    """Genoeg brug om een paneel binnen te laten komen."""

    BADGE_NAME = "keuken"
    connected = True
    last_error = None
    subscribers = {}

    @classmethod
    def subscribe(cls, suffix, callback):
        cls.subscribers[suffix] = callback
        return True

    @classmethod
    def unsubscribe(cls, suffix):
        cls.subscribers.pop(suffix, None)

    @classmethod
    def publish(cls, suffix, payload, retain=False):
        return True

    @classmethod
    def wake(cls):
        return True

    @classmethod
    def deliver(cls, suffix, tekst):
        cb = cls.subscribers.get(suffix)
        if cb is None:
            return False
        cb("home/badges/%s/%s" % (cls.BADGE_NAME, suffix), tekst.encode())
        return True


import lvgl as lv                                 # noqa: E402
import mpos                                       # noqa: E402
import mpos.ui                                    # noqa: E402
import mpos.config                                # noqa: E402
import hcpanel as service                         # noqa: E402
from homecontrol import HomeControl, COL_BG       # noqa: E402
import lv_render                                  # noqa: E402

PANEEL = json.dumps({"title": "Huis", "buttons": [
    {"id": "alarm_aan", "label": "Alarm aan", "state": "alarm",
     "symbol": "BELL", "confirm": True},
    {"id": "licht_uit", "label": "Licht beneden", "state": "licht",
     "symbol": "POWER"},
    {"id": "koepel_lucht", "label": "Koepel ventilatie", "state": "koepel",
     "symbol": "UP"},
    {"id": "koepel_dicht", "label": "Koepel dicht", "state": "koepel",
     "symbol": "DOWN"},
]})

TOESTAND = json.dumps({
    "alarm": {"text": "uit", "color": "CC5555"},
    "licht": {"text": "2 aan", "color": "E0A030"},
    "koepel": "dicht",
})


def scherm():
    mpos.config._STORE.clear()
    sys.modules[service.BRIDGE_MODULE] = NepBrug
    NepBrug.subscribers = {}
    service.buttons = []
    service.panel_title = service.DEFAULT_TITLE
    service.panel_seq = 0
    service.states = {}
    service.state_seq = 0
    service.press_seq = 0
    service.press_error = None
    service.reset()
    service.sync_bridge()
    service.subscribe_all()
    NepBrug.deliver(service.SUFFIX_PANEL, PANEEL)
    NepBrug.deliver(service.SUFFIX_STATE, TOESTAND)
    act = HomeControl()
    act.onCreate()
    act.onResume(act.screen)
    return act


def main(uit):
    maten = lv_render.font_maten(lv)
    grond = "#%06X" % COL_BG

    def bewaar(act, naam):
        act._refresh()
        return lv_render.teken(act.screen.children,
                               os.path.join(uit, "paneel-%s.png" % naam),
                               maten, achtergrond=grond, lv=lv)

    act = scherm()
    print(bewaar(act, "rust"))

    # De alarmknop na een eerste tik: dit is wat er te weinig uitzag.
    act = scherm()
    act.tiles["alarm_aan"][0].click()
    print(bewaar(act, "alarm-bewapend"))

    # En een gewone knop die op bewijs staat te wachten.
    act = scherm()
    act.tiles["licht_uit"][0].click()
    print(bewaar(act, "licht-wacht"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp")
