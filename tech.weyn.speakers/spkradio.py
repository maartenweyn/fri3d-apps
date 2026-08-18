"""Radio: de zenders uit je Sonos-favorieten, een tik per zender.

Sonos bewaart radio en playlists door elkaar in dezelfde favorietenlijst. Dit
scherm laat er alleen de zenders van zien, want daarvoor pak je de badge: VRT 1
in de keuken aanzetten hoort niet twee schermen diep te liggen.

Een zender start ook anders dan een playlist, en dat verschil zit in
`spksonos.play_favorite()` en niet hier. Dit scherm weet alleen welke
favorieten zenders zijn.
"""

import spkstate as state
import spkui as ui

from mpos import Activity


class SpeakerRadio(Activity):

    def __init__(self):
        super().__init__()
        self.lijst = None
        self.status = None
        self._seq = -1
        self._frame_cb = None

    def onCreate(self):
        s = ui.scherm()

        kop = ui.rij(s, 40)
        kop_label = ui.label(kop, "Radio", ui.COL_DIM)
        try:
            kop_label.set_flex_grow(1)
        except Exception:
            pass
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

    # --- laden ---------------------------------------------------------------

    def _laad(self, force=False):
        if force or not state.favorieten:
            state.taak(state.ververs_favorieten())

    def _ververs(self):
        self._laad(force=True)

    # --- tekenen -------------------------------------------------------------

    def _teken(self):
        if self.lijst is None or state.seq == self._seq:
            return
        self._seq = state.seq
        self.lijst.clean()
        zenders = state.radiozenders()
        for zender in zenders:
            ui.knop(self.lijst, zender["titel"],
                    lambda z=zender: self._speel(z), hoogte=44)
        if not zenders and not state.bezig:
            self.status.set_text("geen zenders in je favorieten")
        else:
            self.status.set_text(state.status or "")

    def _speel(self, zender):
        state.taak(state.speel_favoriet(zender))
        self.finish()
