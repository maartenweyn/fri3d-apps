"""Het klokscherm, als overlay boven wat er ook draait.

Het hangt in `lv.layer_top()` en niet in een eigen activity, en dat is de hele
truc: terugkeren naar wat de gebruiker aan het doen was is dan niets meer dan
de overlay weghalen. Een activity starten zou de app op de voorgrond wegduwen,
en dan moet je bijhouden waar je vandaan kwam en hopen dat die app dat overleeft.

De cijfers zijn getekend en niet getypt. Het grootste lettertype in deze firmware
is `montserrat_28`, en dat lees je niet vanuit bed. `_Digit` en `_Clock` komen
uit tech.weyn.pomodoro, met één verschil: daar staan de niet-brandende segmenten
op opaciteit 18 zodat het op een echt zevensegmentdisplay lijkt. Hier staan ze
helemaal uit, want dat is vijfendertig lampjes die 's nachts licht geven voor de
sier.

De helderheid regelt de achtergrondverlichting, niet dit scherm. Hier is alles
wit op zwart, en hoe donker dat wordt bepaalt `badge_service`.

Dit scherm luistert nergens naar. Aanrakingen gaan door naar de app eronder (de
overlay is niet aanklikbaar, en een tik hoort die app te wekken) en de joystick
wordt door `badge_service` rechtstreeks van de I/O-expander gelezen.

Dat laatste is een omweg met een reden. De eerste versie zette de overlay in de
focusgroep zodat de toetsen hier aankwamen. Twee dingen gingen daar mis. De
driver van het bord roept bij elke druk eerst zijn eigen navigatiehaak aan, dus
X gaat sowieso een scherm terug en B verzet de focus voor er iets bij ons
aankomt. En het onthouden van wie de focus had werd een val: kwam er intussen
een bericht binnen, dan bouwde die app zijn scherm opnieuw op, wees onze
herinnering naar iets dat niet meer bestond, en deed de d-pad daarna niets meer
op de hele badge. Van de expander lezen heeft geen van beide problemen.
"""

import lvgl as lv


def _const(*spellings, **kw):
    standaard = kw.get("default")
    for spelling in spellings:
        obj = lv
        ok = True
        for deel in spelling.split("."):
            if not hasattr(obj, deel):
                ok = False
                break
            obj = getattr(obj, deel)
        if ok:
            return obj
    return standaard


SCROLL_OFF = _const("SCROLLBAR_MODE.OFF", default=0)
CLICKABLE = _const("obj.FLAG.CLICKABLE", "OBJ_FLAG_CLICKABLE")

COL_ACHTERGROND = 0x000000
COL_TIJD = 0xFFFFFF
COL_KLEIN = 0x9098A8
COL_ZON = 0xE8B33C
COL_WOLK = 0x8892A4
COL_REGEN = 0x5C8FD6

SEGMENT_AAN = 255
SEGMENT_UIT = 0          # bij Pomodoro 18, hier nul: geen licht voor de sier


class _Digit:
    """Eén zevensegmentcijfer, zeven rechthoeken.

    Overgenomen uit tech.weyn.pomodoro.
    """

    SEGMENTS = {
        "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc",
        "5": "afgcd", "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcdfg",
        " ": "",
    }
    ORDER = "abcdefg"

    def __init__(self, parent, x, y, w, h, t):
        mid = (h - t) // 2
        boxes = {
            "a": (t, 0, w - 2 * t, t),
            "b": (w - t, t, t, mid - t),
            "c": (w - t, mid + t, t, h - mid - 2 * t),
            "d": (t, h - t, w - 2 * t, t),
            "e": (0, mid + t, t, h - mid - 2 * t),
            "f": (0, t, t, mid - t),
            "g": (t, mid, w - 2 * t, t),
        }
        self.parts = {}
        for name in self.ORDER:
            bx, by, bw, bh = boxes[name]
            part = lv.obj(parent)
            part.set_pos(x + bx, y + by)
            part.set_size(max(2, bw), max(2, bh))
            part.set_style_border_width(0, 0)
            part.set_style_radius(1, 0)
            part.set_style_pad_all(0, 0)
            # Meteen doven. Zonder dit staan er tot de eerste set() achtentwintig
            # rechthoeken in de themakleur op het scherm, en dat is precies het
            # licht waar dit scherm voor bestaat om het niet te geven.
            part.set_style_bg_opa(SEGMENT_UIT, 0)
            try:
                part.set_scrollbar_mode(SCROLL_OFF)
            except Exception:
                pass
            self.parts[name] = part
        self.value = None

    def set(self, char, color):
        if char == self.value:
            return
        self.value = char
        lit = self.SEGMENTS.get(char, "")
        shade = lv.color_hex(color)
        for name, part in self.parts.items():
            part.set_style_bg_color(shade, 0)
            part.set_style_bg_opa(SEGMENT_AAN if name in lit else SEGMENT_UIT, 0)


class _Klok:
    """HH:MM in getekende cijfers, passend gemaakt op de ruimte die hij krijgt."""

    def __init__(self, parent, x, y, breedte, hoogte):
        dikte = max(4, hoogte // 7)
        cijfer_b = max(2 * dikte + 4, int(hoogte * 0.58))
        gat = max(3, cijfer_b // 8)
        dubbelpunt_b = dikte

        xs = [0, cijfer_b + gat]
        dp_x = 2 * cijfer_b + 2 * gat
        xs.append(dp_x + dubbelpunt_b + gat)
        xs.append(xs[2] + cijfer_b + gat)
        totaal = xs[3] + cijfer_b
        marge = max(0, (breedte - totaal) // 2)

        self.digits = [
            _Digit(parent, x + marge + dx, y, cijfer_b, hoogte, dikte)
            for dx in xs
        ]
        self.dots = []
        for dot_y in (int(hoogte * 0.30), int(hoogte * 0.62)):
            dot = lv.obj(parent)
            dot.set_pos(x + marge + dp_x, y + dot_y)
            dot.set_size(dubbelpunt_b, dikte)
            dot.set_style_border_width(0, 0)
            dot.set_style_radius(1, 0)
            dot.set_style_pad_all(0, 0)
            dot.set_style_bg_opa(0, 0)
            try:
                dot.set_scrollbar_mode(SCROLL_OFF)
            except Exception:
                pass
            self.dots.append(dot)
        self._punten = None

    def set_time(self, tekst, kleur):
        for digit, char in zip(self.digits, tekst[:2] + tekst[3:5]):
            digit.set(char, kleur)
        if self._punten != kleur:
            self._punten = kleur
            shade = lv.color_hex(kleur)
            for dot in self.dots:
                dot.set_style_bg_color(shade, 0)
                dot.set_style_bg_opa(SEGMENT_AAN, 0)


# Home Assistant kent tientallen weertoestanden en dit scherm heeft er drie
# pictogrammen voor. Alles wat naar beneden komt is regen, de rest is bewolkt,
# en alleen een echt onbewolkte hemel is zon.
REGEN = ("rainy", "pouring", "snowy", "snowy-rainy", "hail", "lightning",
         "lightning-rainy")
ZON = ("sunny", "clear-night", "clear")


def icoon_soort(toestand):
    if not toestand:
        return None
    t = str(toestand).strip().lower()
    if t in REGEN:
        return "regen"
    if t in ZON:
        return "zon"
    return "bewolkt"


class _Weericoon:
    """Zon, wolk of regen, getekend met rechthoeken en rondingen.

    Geen plaatjes: die kosten flash, moeten geladen worden en zien er op 32 bij
    32 niet beter uit dan dit."""

    def __init__(self, parent, x, y, maat=34):
        self.maat = maat
        self.zon = lv.obj(parent)
        self.zon.set_pos(x + maat // 5, y + maat // 5)
        self.zon.set_size(maat * 3 // 5, maat * 3 // 5)
        self._plat(self.zon, maat)

        self.wolk_groot = lv.obj(parent)
        self.wolk_groot.set_pos(x, y + maat // 3)
        self.wolk_groot.set_size(maat, maat * 2 // 5)
        self._plat(self.wolk_groot, maat // 5)

        self.wolk_bult = lv.obj(parent)
        self.wolk_bult.set_pos(x + maat // 4, y + maat // 6)
        self.wolk_bult.set_size(maat // 2, maat // 2)
        self._plat(self.wolk_bult, maat)

        self.druppels = []
        for i in range(3):
            d = lv.obj(parent)
            d.set_pos(x + maat // 5 + i * (maat // 4), y + maat * 4 // 5)
            d.set_size(max(2, maat // 12), maat // 5)
            self._plat(d, maat // 12)
            self.druppels.append(d)

        self.soort = None

    def _plat(self, obj, radius):
        obj.set_style_border_width(0, 0)
        obj.set_style_pad_all(0, 0)
        obj.set_style_radius(radius, 0)
        try:
            obj.set_scrollbar_mode(SCROLL_OFF)
        except Exception:
            pass
        obj.set_style_bg_opa(0, 0)

    def _toon(self, obj, aan, kleur):
        obj.set_style_bg_opa(255 if aan else 0, 0)
        if aan:
            obj.set_style_bg_color(lv.color_hex(kleur), 0)

    def set(self, soort):
        if soort == self.soort:
            return
        self.soort = soort
        self._toon(self.zon, soort == "zon", COL_ZON)
        wolk = soort in ("bewolkt", "regen")
        self._toon(self.wolk_groot, wolk, COL_WOLK)
        self._toon(self.wolk_bult, wolk, COL_WOLK)
        for d in self.druppels:
            self._toon(d, soort == "regen", COL_REGEN)


class ClockOverlay:
    """De klok, boven alles, aan of weg.

    Bouwt zichzelf pas bij de eerste keer tonen. Een badge die dit nooit gebruikt
    betaalt er dan ook geen geheugen voor."""

    def __init__(self):
        self.root = None
        self.klok = None
        self.naam = None
        self.datum = None
        self.batterij = None
        self.icoon = None
        self.nu_temp = None
        self.bereik = None
        self._getoond = ""

    # --- opbouw ------------------------------------------------------------

    def _bouw(self):
        laag = lv.layer_top()
        self.root = lv.obj(laag)
        self.root.set_size(320, 240)
        self.root.set_pos(0, 0)
        self.root.set_style_bg_color(lv.color_hex(COL_ACHTERGROND), 0)
        self.root.set_style_bg_opa(255, 0)
        self.root.set_style_border_width(0, 0)
        self.root.set_style_pad_all(0, 0)
        try:
            self.root.set_scrollbar_mode(SCROLL_OFF)
        except Exception:
            pass
        # Niet aanklikbaar, zodat een tik gewoon doorgaat naar de app eronder en
        # de inactiviteitsteller toch reset. Een overlay die aanrakingen opslokt
        # zou de app eronder onbereikbaar maken zolang de klok staat.
        if CLICKABLE is not None:
            try:
                self.root.remove_flag(CLICKABLE)
            except Exception:
                try:
                    self.root.clear_flag(CLICKABLE)
                except Exception:
                    pass

        # De naam bovenaan, klein en gedimd. Wie drie badges in huis heeft wil
        # 's nachts weten naar welke hij kijkt, en het is de enige tekst op dit
        # scherm die niet elke minuut verandert.
        self.naam = lv.label(self.root)
        self.naam.set_pos(0, 2)
        self.naam.set_width(320)
        try:
            self.naam.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        except Exception:
            pass
        self.naam.set_style_text_color(lv.color_hex(COL_KLEIN), 0)
        self.naam.set_text("")

        self.klok = _Klok(self.root, 0, 22, 320, 100)

        self.datum = lv.label(self.root)
        self.datum.set_pos(14, 128)
        self.datum.set_style_text_color(lv.color_hex(COL_KLEIN), 0)
        self.datum.set_text("")

        self.batterij = lv.label(self.root)
        self.batterij.set_pos(250, 128)
        self.batterij.set_style_text_color(lv.color_hex(COL_KLEIN), 0)
        self.batterij.set_text("")

        self.icoon = _Weericoon(self.root, 20, 168, 40)

        self.nu_temp = lv.label(self.root)
        self.nu_temp.set_pos(76, 176)
        self.nu_temp.set_style_text_color(lv.color_hex(COL_TIJD), 0)
        font = getattr(lv, "font_montserrat_24", None) or \
            getattr(lv, "font_montserrat_20", None)
        if font is not None:
            self.nu_temp.set_style_text_font(font, 0)
        self.nu_temp.set_text("")

        self.bereik = lv.label(self.root)
        self.bereik.set_pos(168, 182)
        self.bereik.set_style_text_color(lv.color_hex(COL_KLEIN), 0)
        self.bereik.set_text("")

    # --- tonen en weghalen -------------------------------------------------

    def zichtbaar(self):
        return self.root is not None

    def toon(self):
        if self.root is None:
            self._bouw()
            self._getoond = ""
        return True

    def weg(self):
        if self.root is None:
            return False
        try:
            self.root.delete()
        except Exception:
            pass
        self.root = None
        self.klok = None
        self.naam = None
        self._getoond = ""
        return True

    # --- inhoud ------------------------------------------------------------

    def werk_bij(self, tijd, datum, batterij, weer, naam=""):
        """Alles wat op het scherm staat in een keer.

        Vergelijkt eerst of er iets veranderd is: dit draait elke seconde, en
        LVGL-tekst herschrijven die hetzelfde blijft geeft geflikker."""
        if self.root is None:
            return False
        soort = icoon_soort((weer or {}).get("toestand"))
        nu = (weer or {}).get("nu")
        hoog = (weer or {}).get("max")
        laag = (weer or {}).get("min")
        sleutel = "%s|%s|%s|%s|%s|%s|%s" % (tijd, datum, batterij, soort, nu,
                                            "%s/%s" % (hoog, laag), naam)
        if sleutel == self._getoond:
            return False
        self._getoond = sleutel

        if tijd and self.klok is not None:
            self.klok.set_time(tijd, COL_TIJD)
        self.naam.set_text(naam or "")
        self.datum.set_text(datum or "")
        self.batterij.set_text("%d%%" % batterij if batterij is not None else "")
        self.icoon.set(soort)
        self.nu_temp.set_text(graden(nu))
        if hoog is None and laag is None:
            self.bereik.set_text("")
        else:
            self.bereik.set_text("%s / %s" % (graden(hoog), graden(laag)))
        return True


def graden(waarde):
    """Een temperatuur zoals je hem zegt, of leeg.

    Geen kommagetal: op een klok naast je bed is 12 genoeg en 12.3 alleen maar
    meer licht."""
    if waarde is None:
        return ""
    try:
        return "%d°" % int(round(float(waarde)))
    except (ValueError, TypeError):
        return ""
