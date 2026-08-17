"""De wekkers van de gekozen box.

Sonos bewaart alle alarmen van het hele huishouden in een lijst, met een
RoomUUID per alarm om te zeggen waar hij hoort. Dit scherm filtert op de
gekozen box, want een lijst met de wekkers van vijf kamers door elkaar is niet
te lezen op 320 bij 240.

Wijzigen kan aan of uit, en de tijd in stappen van vijf minuten. Alles wat niet
aangeraakt wordt gaat onveranderd terug, want UpdateAlarm is een volledige
vervanging: wie een veld weglaat, wist het.
"""

from mpos import Activity

import mzsonos
import mzstate as state
import mzui as ui


class MuziekWekkers(Activity):

    def __init__(self):
        super().__init__()
        self._seq = -1
        self._frame_cb = None

    def onCreate(self):
        s = ui.scherm()

        kop = ui.rij(s, 40)
        self.kop_label = ui.label(kop, "Wekkers", ui.COL_DIM)
        try:
            self.kop_label.set_flex_grow(1)
        except Exception:
            pass
        ui.knop(kop, ui.SYM_REFRESH, self._ververs, breedte=52, hoogte=40)

        self.lijst = ui.lijst(s)
        self.status = ui.label(s, "", ui.COL_DIM, breedte=ui.SCHERM_B)

        self.setContentView(s)

    def onResume(self, screen):
        super().onResume(screen)
        self._seq = -1
        if not state.wekkers:
            state.taak(state.ververs_wekkers())
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

    # --- tekenen -----------------------------------------------------------

    def _teken(self):
        if state.seq == self._seq:
            return
        self._seq = state.seq

        naam = state.zone["naam"] if state.zone else ""
        self.kop_label.set_text("Wekkers " + naam if naam else "Wekkers")

        ui.leeg(self.lijst)
        for a in state.wekkers:
            self._rij(a)
        if not state.wekkers and not state.bezig:
            ui.label(self.lijst, "geen wekkers voor deze box", ui.COL_DIM,
                     breedte=ui.SCHERM_B)

        tekst = state.status
        if state.bezig:
            tekst = (tekst + " ..." if tekst else "ophalen ...")
        self.status.set_text(ui.kort(tekst, 44))

    def _rij(self, alarm):
        import lvgl as lv

        r = ui.rij(self.lijst, 44, gap=4)
        ui.knop(r, "-", lambda a=alarm: self._verschuif(a, -5),
                breedte=38, hoogte=40)
        tijd = ui.label(r, alarm["tijd"], ui.COL_TEXT,
                        ui.font("font_montserrat_20", "font_montserrat_18"))
        try:
            tijd.set_width(56)
        except Exception:
            pass
        ui.knop(r, "+", lambda a=alarm: self._verschuif(a, 5),
                breedte=38, hoogte=40)

        omschrijving = "%s · %s" % (mzsonos.recurrence_text(alarm["herhaling"]),
                                    alarm["bron"])
        wat = ui.label(r, ui.kort(omschrijving, 18), ui.COL_DIM)
        try:
            wat.set_flex_grow(1)
        except Exception:
            pass

        sw = lv.switch(r)
        try:
            sw.set_size(52, 28)
        except Exception:
            pass
        if alarm["aan"]:
            sw.add_state(lv.STATE.CHECKED)
        sw.add_event_cb(lambda e, s=sw, a=alarm: self._schakel(a, s),
                        lv.EVENT.VALUE_CHANGED, None)
        ui.focusable(sw)

    # --- invoer ------------------------------------------------------------

    def _schakel(self, alarm, sw):
        import lvgl as lv
        state.taak(state.zet_wekker(alarm, aan=bool(sw.has_state(lv.STATE.CHECKED))))

    def _verschuif(self, alarm, minuten):
        state.taak(state.zet_wekker(alarm, minuten=minuten))

    def _ververs(self):
        state.taak(state.ververs_wekkers())
