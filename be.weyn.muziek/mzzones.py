"""De lijst met Sonos-boxen.

Een rij per speler, 44 hoog zodat een vinger raak is. De gekozen box staat er
omgekeerd op, donker op het oranje van de knop, en een speler die als slaaf in
een groep hangt zegt dat erbij:
hij weigert Play, dus het commando gaat naar de baas van zijn groep. Dat gebeurt
vanzelf in mzstate.zone_baas, maar wie het scherm bekijkt moet wel snappen
waarom de muziek elders begint.
"""

from mpos import Activity

import mzstate as state
import mzui as ui


class MuziekZones(Activity):

    def __init__(self):
        super().__init__()
        self._seq = -1
        self._frame_cb = None

    def onCreate(self):
        s = ui.scherm()

        kop = ui.rij(s, 40)
        titel = ui.label(kop, "Kies een box", ui.COL_DIM)
        try:
            titel.set_flex_grow(1)
        except Exception:
            pass
        ui.knop(kop, ui.SYM_REFRESH, self._opnieuw_zoeken, breedte=52, hoogte=40)

        self.lijst = ui.lijst(s)
        self.status = ui.label(s, "", ui.COL_DIM, breedte=ui.SCHERM_B)

        self.setContentView(s)

    def onResume(self, screen):
        super().onResume(screen)
        self._seq = -1
        if not state.zones:
            state.taak(state.zoek_zones())
        self._tick_aan()
        self._teken()

    def onPause(self, screen):
        super().onPause(screen)
        self._tick_uit()

    def _tick_aan(self):
        if self._frame_cb is not None:
            return
        self._frame_cb = self._op_frame
        try:
            import mpos.ui
            mpos.ui.task_handler.add_event_cb(self._frame_cb, 1)
        except Exception:
            self._frame_cb = None

    def _tick_uit(self):
        if self._frame_cb is None:
            return
        try:
            import mpos.ui
            mpos.ui.task_handler.remove_event_cb(self._frame_cb)
        except Exception:
            pass
        self._frame_cb = None

    def _op_frame(self, a, b):
        self._teken()

    def _teken(self):
        if state.seq == self._seq:
            return
        self._seq = state.seq
        ui.leeg(self.lijst)
        for z in state.zones:
            gekozen = state.zone is not None and z["uid"] == state.zone["uid"]
            merk = ""
            if not z["baas"]:
                merk = "  (gegroepeerd)"
            tekst = ("> " if gekozen else "") + z["naam"] + merk
            knop, label = ui.knop(self.lijst, tekst,
                                  lambda zz=z: self._kies(zz), hoogte=44)
            if gekozen:
                label.set_style_text_color(ui.color(ui.COL_GEKOZEN), 0)
        tekst = state.status
        if state.bezig:
            tekst = (tekst + " ..." if tekst else "zoeken ...")
        self.status.set_text(ui.kort(tekst, 44))

    def _kies(self, z):
        state.kies_zone(z)
        state.taak(state.ververs_speler())
        self.finish()

    def _opnieuw_zoeken(self):
        state.taak(state.zoek_zones())
