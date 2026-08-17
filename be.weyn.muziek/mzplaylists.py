"""De lijst om uit te kiezen: playlists uit Spotify, of de Sonos-favorieten.

Twee bronnen omdat ze los van elkaar kapot kunnen. De playlists komen van
api.spotify.com en hebben een refresh token nodig; de favorieten komen uit de
Sonos zelf en werken zonder login. Valt het ene weg, dan is het andere er nog,
en de knop bovenaan wisselt.

Tikken op een rij zet de lijst op de gekozen box en gaat terug naar de speler.
"""

from mpos import Activity

import mzstate as state
import mzui as ui


class MuziekLijsten(Activity):

    def __init__(self):
        super().__init__()
        self._seq = -1
        self._frame_cb = None
        # Zonder Spotify-sleutels heeft de Spotify-kant niets te tonen, dus
        # begin dan meteen bij wat er wel is.
        self._bron = "spotify" if state.spotify_ingesteld() else "favorieten"

    def onCreate(self):
        s = ui.scherm()

        kop = ui.rij(s, 40)
        self.kop_label = ui.label(kop, "Playlists", ui.COL_DIM)
        try:
            self.kop_label.set_flex_grow(1)
        except Exception:
            pass
        _, self.bron_label = ui.knop(kop, "", self._wissel_bron,
                                     breedte=104, hoogte=40)
        ui.knop(kop, ui.SYM_REFRESH, self._ververs, breedte=52, hoogte=40)

        self.lijst = ui.lijst(s)
        self.status = ui.label(s, "", ui.COL_DIM, breedte=ui.SCHERM_B)

        self.setContentView(s)

    def onResume(self, screen):
        super().onResume(screen)
        self._seq = -1
        self._laad()
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

    # --- laden -------------------------------------------------------------

    def _laad(self, force=False):
        if self._bron == "spotify":
            state.taak(state.ververs_lijsten(force=force))
        else:
            if force or not state.favorieten:
                state.taak(state.ververs_favorieten())

    def _ververs(self):
        self._laad(force=True)

    def _wissel_bron(self):
        self._bron = "favorieten" if self._bron == "spotify" else "spotify"
        self._seq = -1
        self._laad()
        self._teken()

    # --- tekenen -----------------------------------------------------------

    def _teken(self):
        if state.seq == self._seq:
            return
        self._seq = state.seq

        spotify = self._bron == "spotify"
        self.kop_label.set_text("Playlists" if spotify else "Favorieten")
        self.bron_label.set_text("favorieten" if spotify else "Spotify")

        ui.leeg(self.lijst)
        if spotify:
            for p in state.lijsten:
                # Spotify geeft voor deze playlists geen bruikbare tracks.total
                # terug, dus alles kwam als "(0)" op het scherm. Een getal dat
                # nul is als het onbekend is, is erger dan geen getal.
                aantal = p.get("aantal") or 0
                if aantal:
                    tekst = "%s  (%d)" % (ui.kort(p["naam"], 26), aantal)
                else:
                    tekst = ui.kort(p["naam"], 32)
                ui.knop(self.lijst, tekst,
                        lambda pp=p: self._speel_lijst(pp), hoogte=44)
            if not state.lijsten and not state.bezig:
                ui.label(self.lijst,
                         "geen playlists" if state.spotify_ingesteld()
                         else "Spotify staat niet in muziek_config.py",
                         ui.COL_DIM, breedte=ui.SCHERM_B)
        else:
            for f in state.favorieten:
                ui.knop(self.lijst, ui.kort(f["titel"], 30),
                        lambda ff=f: self._speel_favoriet(ff), hoogte=44)
            if not state.favorieten and not state.bezig:
                ui.label(self.lijst, "geen favorieten in dit Sonos-systeem",
                         ui.COL_DIM, breedte=ui.SCHERM_B)

        tekst = state.status
        if state.bezig:
            tekst = (tekst + " ..." if tekst else "ophalen ...")
        self.status.set_text(ui.kort(tekst, 44))

    # --- invoer ------------------------------------------------------------

    def _speel_lijst(self, p):
        state.taak(state.speel_lijst(p["uri"], p["naam"]))
        self.finish()

    def _speel_favoriet(self, f):
        state.taak(state.speel_favoriet(f))
        self.finish()
