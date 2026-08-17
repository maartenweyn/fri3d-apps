"""Muziek: het spelerscherm.

De bovenste knop is de gekozen box. Die keuze wordt onthouden in
SharedPreferences en bij het opstarten teruggezocht op uid, niet op IP: DHCP
verhuist een speler, zijn uid verandert nooit. Wie op de naam tikt, krijgt de
lijst met boxen.

Het scherm rekent niet en praat niet met het netwerk. Het kijkt per frame naar
mzstate.seq en tekent alleen opnieuw als dat getal veranderd is. Alle trage
dingen zijn taken in mzstate, want een blokkerende socket op deze thread
bevriest LVGL.
"""

import lvgl as lv

from mpos import Activity, Intent

import mzstate as state
import mzui as ui
from mzzones import MuziekZones
from mzplaylists import MuziekLijsten
from mzalarms import MuziekWekkers

STAAT_NL = {
    "PLAYING": "speelt",
    "PAUSED_PLAYBACK": "pauze",
    "STOPPED": "gestopt",
    "TRANSITIONING": "even geduld",
}


class Muziek(Activity):

    def __init__(self):
        super().__init__()
        self._seq = -1
        self._frame_cb = None
        self._gestart = False

    # --- opbouw ------------------------------------------------------------

    def onCreate(self):
        s = ui.scherm()

        kop = ui.rij(s, 40)
        self.naam_knop, self.naam_label = ui.knop(
            kop, "zoeken...", self._open_zones, hoogte=40, grow=1)
        ui.knop(kop, ui.SYM_REFRESH, self._ververs, breedte=52, hoogte=40)

        self.titel = ui.label(s, "", ui.COL_TEXT,
                              ui.font("font_montserrat_20", "font_montserrat_18"),
                              breedte=ui.SCHERM_B)

        info = ui.rij(s, 20)
        self.artiest = ui.label(info, "", ui.COL_DIM)
        try:
            self.artiest.set_flex_grow(1)
        except Exception:
            pass
        self.vol_label = ui.label(info, "", ui.COL_DIM)

        # Transport en volume op een rij: vijf knoppen van 56 breed met gaten
        # van 4 passen precies in 304, en zes rijen passen niet in 224 hoog.
        bediening = ui.rij(s, 44, gap=4)
        ui.knop(bediening, ui.SYM_PREV, lambda: self._spring(False), grow=1)
        _, self.speel_label = ui.knop(bediening, ui.SYM_PLAY, self._wissel, grow=1)
        ui.knop(bediening, ui.SYM_NEXT, lambda: self._spring(True), grow=1)
        ui.knop(bediening, "-", lambda: self._volume(-4), grow=1)
        ui.knop(bediening, "+", lambda: self._volume(4), grow=1)

        onder = ui.rij(s, 44)
        ui.knop(onder, "Playlists", self._open_lijsten, grow=1)
        ui.knop(onder, "Wekkers", self._open_wekkers, grow=1)

        self.status = ui.label(s, "", ui.COL_DIM, breedte=ui.SCHERM_B)

        self.setContentView(s)

    # --- levenscyclus ------------------------------------------------------

    def onResume(self, screen):
        super().onResume(screen)
        self._seq = -1                      # altijd een keer volledig tekenen
        if not self._gestart:
            self._gestart = True
            state.taak(state.opstarten())
        elif state.zone is not None:
            state.taak(state.ververs_speler())
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
            return
        except Exception:
            pass
        try:
            self._timer = lv.timer_create(self._op_timer, 400, None)
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
        t = getattr(self, "_timer", None)
        if t is not None:
            try:
                t.delete()
            except Exception:
                pass
            self._timer = None
        self._frame_cb = None

    def _op_frame(self, a, b):
        self._teken()

    def _op_timer(self, timer):
        self._teken()

    # --- tekenen -----------------------------------------------------------

    def _teken(self):
        if state.seq == self._seq:
            return
        self._seq = state.seq

        if state.zone is None:
            self.naam_label.set_text("geen box")
        else:
            self.naam_label.set_text(state.zone["naam"])

        titel = state.speler["titel"]
        self.titel.set_text(titel if titel else "niets aan het spelen")
        staat = STAAT_NL.get(state.speler["staat"], "")
        artiest = state.speler["artiest"]
        self.artiest.set_text(artiest if artiest else staat)
        self.vol_label.set_text("vol %d" % state.speler["volume"])
        self.speel_label.set_text(
            ui.SYM_PAUSE if state.speler["staat"] == "PLAYING" else ui.SYM_PLAY)

        tekst = state.status
        if state.bezig:
            tekst = (tekst + " ..." if tekst else "bezig ...")
        self.status.set_text(ui.kort(tekst, 44))

    # --- invoer ------------------------------------------------------------

    def _wissel(self):
        state.taak(state.wissel_afspelen())

    def _spring(self, vooruit):
        state.taak(state.spring(vooruit))

    def _volume(self, delta):
        state.taak(state.zet_volume(delta))

    def _ververs(self):
        state.taak(state.zoek_zones(), klaar=lambda r: state.taak(state.ververs_speler()))

    def _open_zones(self):
        self.startActivity(Intent(activity_class=MuziekZones))

    def _open_lijsten(self):
        if state.zone is None:
            return
        self.startActivity(Intent(activity_class=MuziekLijsten))

    def _open_wekkers(self):
        if state.zone is None:
            return
        self.startActivity(Intent(activity_class=MuziekWekkers))
