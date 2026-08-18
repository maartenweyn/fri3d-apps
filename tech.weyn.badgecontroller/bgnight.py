"""Nacht en helderheid: hoe fel de klok mag staan, en wanneer het nacht is.

Vier rijen, het maximum dat op 240 pixels past zonder te scrollen.

Het nachtvenster loopt over middernacht heen, en dat is de normale vorm: van 23
tot 7 is 23, 0, 1 tot en met 6. Van gelijk aan tot betekent dat er geen nacht is
en dat de klok de hele dag op dezelfde helderheid blijft staan.

Binnen het venster gebeuren er twee dingen. De klok gaat naar de nachtwaarde, en
tien minuten later gaat hij helemaal uit. Die tien minuten staan vast in
`KLOK_UIT_S` en niet op een scherm: de klok mag snel komen en daarna nog een
hele tijd blijven staan, en voor die tweede maat is hier geen rij meer vrij.

De nachtwaarden gaan lager dan de dagwaarden en beginnen bij 1. Nul zou uit zijn
en dat is geen klok. Op 1 procent is dit scherm in een donkere kamer nog prima
te lezen en geeft het geen licht dat je wakker houdt.

Hetzelfde is ook zonder dit scherm te doen: terwijl de klok staat maakt de
joystick omhoog hem feller en omlaag donkerder, en dat past de waarde aan die op
dat moment geldt.
"""

import lvgl as lv

from mpos import Activity

import badge_service as service

try:
    from mpos import SharedPreferences
except Exception:
    from mpos.config import SharedPreferences

COL_DIM = 0x8890A0

ROW_HEIGHT = 44
ROW_GAP = 6

# Dezelfde trappen als de knoppen X en B op het klokscherm, want het zou raar
# zijn als je met de knop op een waarde uitkomt die hier niet te kiezen is.
DAG_NIVEAUS = service.KLOK_DAG_NIVEAUS
NACHT_NIVEAUS = service.KLOK_NACHT_NIVEAUS

volgende = service.stap

UREN = tuple(range(24))


def helderheid_text(niveau):
    return "%d%%" % niveau


def uur_text(uur):
    return "%02d:00" % (int(uur) % 24)


def klem(waarde, niveaus, standaard):
    """De dichtstbijzijnde waarde uit de reeks.

    Wat in de voorkeuren staat kan uit een configbestand komen of van een oudere
    versie, en dan staat het niet per se in deze lijst. Zonder dit begint de
    stepper bij de eerste waarde en springt de instelling weg zodra je hem
    aanraakt."""
    try:
        waarde = int(waarde)
    except (TypeError, ValueError):
        return standaard
    return service.stap(niveaus, waarde, 0)


class BadgeNight(Activity):

    def __init__(self):
        super().__init__()
        self.dag = 30
        self.nacht = 5
        self.van = 23
        self.tot = 7
        self.dag_label = None
        self.nacht_label = None
        self.van_label = None
        self.tot_label = None

    # --- levenscyclus ------------------------------------------------------

    def onCreate(self):
        self.dag = klem(service.CLOCK_DAY, DAG_NIVEAUS, 30)
        self.nacht = klem(service.CLOCK_NIGHT, NACHT_NIVEAUS, 5)
        self.van = int(service.NIGHT_FROM or 0) % 24
        self.tot = int(service.NIGHT_TO or 0) % 24

        screen = lv.obj()
        screen.set_style_pad_all(8, 0)
        screen.set_style_pad_row(ROW_GAP, 0)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self._no_scroll(screen)

        title = lv.label(screen)
        title.set_text("Nacht en helderheid")
        title.set_style_text_color(lv.color_hex(COL_DIM), 0)

        self.dag_label = self._stepper_row(
            screen, "Klok overdag", helderheid_text(self.dag), self._cycle_dag)
        self.van_label = self._stepper_row(
            screen, "Nacht van", uur_text(self.van), self._cycle_van)
        self.tot_label = self._stepper_row(
            screen, "Nacht tot", uur_text(self.tot), self._cycle_tot)
        self.nacht_label = self._stepper_row(
            screen, "Klok 's nachts", helderheid_text(self.nacht),
            self._cycle_nacht)

        self.setContentView(screen)

    def onPause(self, screen):
        self._save()
        super().onPause(screen)

    # --- invoer ------------------------------------------------------------

    def _cycle_dag(self, delta):
        self.dag = volgende(DAG_NIVEAUS, self.dag, delta)
        if self.dag_label is not None:
            self.dag_label.set_text(helderheid_text(self.dag))

    def _cycle_nacht(self, delta):
        self.nacht = volgende(NACHT_NIVEAUS, self.nacht, delta)
        if self.nacht_label is not None:
            self.nacht_label.set_text(helderheid_text(self.nacht))

    def _cycle_van(self, delta):
        # De uren slaan wél om: van 23 naar 0 is de stap die je hier het vaakst
        # zet, en het is niet de stap waar je in het donker spijt van hebt.
        self.van = (self.van + delta) % 24
        if self.van_label is not None:
            self.van_label.set_text(uur_text(self.van))

    def _cycle_tot(self, delta):
        self.tot = (self.tot + delta) % 24
        if self.tot_label is not None:
            self.tot_label.set_text(uur_text(self.tot))

    # --- rijen -------------------------------------------------------------

    def _no_scroll(self, obj):
        try:
            obj.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        except Exception:
            pass
        for spelling in ("SCROLLABLE", "SCROLL_ELASTIC", "SCROLL_MOMENTUM",
                         "SCROLL_CHAIN_HOR", "SCROLL_CHAIN_VER"):
            flag = getattr(getattr(lv.obj, "FLAG", None), spelling, None)
            if flag is None:
                flag = getattr(lv, "OBJ_FLAG_" + spelling, None)
            if flag is not None:
                try:
                    obj.remove_flag(flag)
                except Exception:
                    try:
                        obj.clear_flag(flag)
                    except Exception:
                        pass

    def _focusable(self, obj):
        try:
            group = lv.group_get_default()
            if group:
                group.add_obj(obj)
        except Exception:
            pass

    def _row(self, parent, height):
        row = lv.obj(parent)
        row.set_size(lv.pct(100), height)
        row.set_style_border_width(0, 0)
        row.set_style_bg_opa(lv.OPA.TRANSP, 0)
        row.set_style_pad_all(2, 0)
        row.set_style_pad_column(8, 0)
        self._no_scroll(row)
        row.set_flex_flow(lv.FLEX_FLOW.ROW)
        row.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER,
                           lv.FLEX_ALIGN.CENTER)
        return row

    def _step_button(self, parent, text, callback):
        btn = lv.button(parent)
        btn.set_size(48, 40)
        btn.add_event_cb(lambda event, cb=callback: cb(), lv.EVENT.CLICKED, None)
        label = lv.label(btn)
        label.set_text(text)
        label.center()
        self._focusable(btn)
        return btn

    def _stepper_row(self, parent, text, value, cycle):
        row = self._row(parent, ROW_HEIGHT)
        name = lv.label(row)
        name.set_text(text)
        try:
            name.set_flex_grow(1)
        except Exception:
            pass
        self._step_button(row, "-", lambda c=cycle: c(-1))
        value_label = lv.label(row)
        value_label.set_text(value)
        self._step_button(row, "+", lambda c=cycle: c(1))
        return value_label

    # --- bewaren -----------------------------------------------------------

    def _save(self):
        try:
            editor = SharedPreferences(service.PREFS_APP_ID).edit()
            editor.put_int("clock_day", int(self.dag))
            editor.put_int("clock_night", int(self.nacht))
            editor.put_int("night_from", int(self.van))
            editor.put_int("night_to", int(self.tot))
            editor.commit()
        except Exception as e:
            print("badge nacht: kon niet bewaren:", e)
        service.load_prefs()
