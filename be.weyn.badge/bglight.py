"""Scherm en lichtjes: wat de badge 's nachts uitstraalt.

Een eigen scherm en geen twee extra rijen op het instelscherm, want daar passen
er precies drie en de rijen scrollen niet: op een scrollbare container maakt
LVGL van een tik die meebeweegt een scroll en dan leest de knop als dood.

Twee dingen staan hier, en ze horen bij elkaar omdat ze allebei over licht in
een slaapkamer gaan.

De schermtimeout stuurt de helderheid over de I2C-expander, want de LVGL-weg
(`main_display.get_backlight()`) geeft -1 op deze firmware.

De debug-LED is het kleine lampje op diezelfde expander. Het staat af fabriek op
50 en brandt dus altijd. De expander is een eigen microcontroller die zijn
instelling zelf bijhoudt, dus nul zetten overleeft een herstart van de ESP32.
Het wordt hier toch elke keer opnieuw toegepast, want een reflash van die
firmware zet hem terug en dan sta je weer met een lampje in het donker.

Wat hier niet bij staat: de twee groene LEDs van de lader. Die hangen aan de
CHRG- en STDBY-pinnen van de TP4056 op de voedingspagina van het schema, en dat
zijn uitgangen van de laadchip zelf. Geen software raakt daaraan.
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

# Uit, en dan van kort naar lang. Onder de vijftien seconden gaat het scherm uit
# terwijl je nog aan het lezen bent; boven het kwartier is het geen besparing
# meer maar een lampje dat aan blijft.
TIMEOUTS = (0, 15, 30, 60, 120, 300, 600, 900)

# Nul is uit. De rest is er om te kunnen zien dat de badge leeft zonder dat het
# een nachtlampje wordt.
DEBUG_LEDS = (0, 5, 15, 30, 50, 75, 100)


def timeout_text(seconden):
    if not seconden:
        return "nooit"
    if seconden < 60:
        return "%d s" % seconden
    if seconden % 60 == 0:
        return "%d min" % (seconden // 60)
    return "%d min %d s" % (seconden // 60, seconden % 60)


def led_text(niveau):
    return "uit" if not niveau else "%d%%" % niveau


def _volgende(waarden, huidig, delta):
    """Een stap door een vaste reeks, zonder om te slaan.

    Omslaan van uit naar honderd met een misgetikte plus is precies wat je in
    een donkere kamer niet wil."""
    try:
        index = waarden.index(huidig)
    except ValueError:
        index = 0
    return waarden[min(len(waarden) - 1, max(0, index + delta))]


class BadgeLight(Activity):

    def __init__(self):
        super().__init__()
        self.screen_off_s = 0
        self.debug_led = 0
        self.timeout_label = None
        self.led_label = None

    # --- levenscyclus ------------------------------------------------------

    def onCreate(self):
        self.screen_off_s = int(service.SCREEN_OFF_S or 0)
        self.debug_led = int(service.DEBUG_LED or 0)

        screen = lv.obj()
        screen.set_style_pad_all(8, 0)
        screen.set_style_pad_row(ROW_GAP, 0)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self._no_scroll(screen)

        title = lv.label(screen)
        title.set_text("Scherm en lichtjes")
        title.set_style_text_color(lv.color_hex(COL_DIM), 0)

        self.timeout_label = self._stepper_row(
            screen, "Scherm uit na", timeout_text(self.screen_off_s),
            self._cycle_timeout)
        self.led_label = self._stepper_row(
            screen, "Debug-LED", led_text(self.debug_led), self._cycle_led)

        hint = lv.label(screen)
        hint.set_width(304)
        try:
            hint.set_long_mode(lv.label.LONG_MODE.WRAP)
        except Exception:
            pass
        hint.set_text("De twee groene lampjes zijn van de lader en zitten "
                      "vast aan de chip. Daar kan software niets aan doen.")
        hint.set_style_text_color(lv.color_hex(COL_DIM), 0)

        self.setContentView(screen)

    def onPause(self, screen):
        self._save()
        super().onPause(screen)

    # --- invoer ------------------------------------------------------------

    def _cycle_timeout(self, delta):
        self.screen_off_s = _volgende(TIMEOUTS, self.screen_off_s, delta)
        if self.timeout_label is not None:
            self.timeout_label.set_text(timeout_text(self.screen_off_s))

    def _cycle_led(self, delta):
        self.debug_led = _volgende(DEBUG_LEDS, self.debug_led, delta)
        if self.led_label is not None:
            self.led_label.set_text(led_text(self.debug_led))
        # Meteen toepassen, want dit is het soort instelling waarvan je het
        # resultaat wil zien terwijl je hem zet.
        service.apply_debug_led(self.debug_led)

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
            editor.put_int("screen_off_s", int(self.screen_off_s))
            editor.put_int("debug_led", int(self.debug_led))
            editor.commit()
        except Exception as e:
            print("badge lichtjes: kon niet bewaren:", e)
        service.load_prefs()
