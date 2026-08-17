"""Pomodoro timer for the Fri3d badge, running on MicroPythonOS.

Drive it with the touchscreen or with the badge keys: the buttons are added
to the default focus group, so the d-pad moves focus and the action key
presses the focused button.
"""

import time

import lvgl as lv

from mpos import Activity, Intent
import mpos.config
import mpos.ui

try:
    from mpos import LightsManager
except Exception:
    LightsManager = None

try:
    from mpos import AudioManager
except Exception:
    AudioManager = None

from posettings import PomodoroSettings, APP_ID, DEFAULTS

WORK = "work"
SHORT = "short"
LONG = "long"

TITLES = {WORK: "Focus", SHORT: "Short break", LONG: "Long break"}
COLORS = {WORK: 0xE5484D, SHORT: 0x30A46C, LONG: 0x3E63DD}
LED_RGB = {WORK: (255, 40, 0), SHORT: (0, 255, 60), LONG: (0, 60, 255)}

# Ring Tone Text Transfer Language, played on the badge buzzer.
CHIME_END_WORK = "brk:d=4,o=5,b=160:8g,8c6,8e6,4g6"
CHIME_END_BREAK = "wrk:d=4,o=5,b=160:8e6,8c6,8g,4e"

LED_DIM = 0.12          # steady glow while the timer runs
FLASH_MS = 4000         # how long the LEDs blink at a phase change
FLASH_PERIOD_MS = 250

GEAR = getattr(getattr(lv, "SYMBOL", None), "SETTINGS", None) or "Set"


def _big_font():
    """Largest Montserrat font compiled into this build, or None."""
    for name in ("font_montserrat_48", "font_montserrat_44", "font_montserrat_40",
                 "font_montserrat_36", "font_montserrat_34", "font_montserrat_32",
                 "font_montserrat_28", "font_montserrat_24"):
        font = getattr(lv, name, None)
        if font is not None:
            return font
    return None


class Pomodoro(Activity):

    def __init__(self):
        super().__init__()
        self.cfg = dict(DEFAULTS)
        self.phase = WORK
        self.running = False
        self.remaining_ms = DEFAULTS["work_min"] * 60000
        self.deadline = 0
        self.round = 0
        self.done_today = 0
        self.day = ""
        self._shown = -1
        self._flash_until = 0
        self._led_key = None
        self._ticking = False
        self._durations = None

    # ---------------------------------------------------------------- lifecycle

    def onCreate(self):
        self._load()
        self._build()
        self._set_phase(WORK)
        self.setContentView(self.root)

    def onResume(self, screen):
        super().onResume(screen)
        changed = self._load()
        if changed and not self.running:
            self._set_phase(self.phase)
        else:
            self._draw()
        self._tick_on()

    def onPause(self, screen):
        self._tick_off()
        self._leds_clear()
        self._save()
        super().onPause(screen)

    def onDestroy(self, screen):
        self._tick_off()
        self._leds_clear()

    # -------------------------------------------------------------- persistence

    def _today(self):
        t = time.localtime()
        return "%04d-%02d-%02d" % (t[0], t[1], t[2])

    def _load(self):
        """Read config and counters. Returns True if the durations changed."""
        prefs = mpos.config.SharedPreferences(APP_ID)
        cfg = {}
        for key, default in DEFAULTS.items():
            try:
                cfg[key] = prefs.get_int(key, default)
            except Exception:
                cfg[key] = default
        self.cfg = cfg

        durations = (cfg["work_min"], cfg["short_min"], cfg["long_min"], cfg["rounds"])
        changed = self._durations is not None and durations != self._durations
        self._durations = durations

        today = self._today()
        try:
            stored_day = prefs.get_string("day", "")
        except Exception:
            stored_day = ""
        if stored_day == today:
            self.done_today = prefs.get_int("done_today", 0)
            self.round = prefs.get_int("round", 0)
        else:
            self.done_today = 0
            self.round = 0
        self.day = today
        return changed

    def _save(self):
        try:
            editor = mpos.config.SharedPreferences(APP_ID).edit()
            editor.put_string("day", self.day)
            editor.put_int("done_today", self.done_today)
            editor.put_int("round", self.round)
            editor.commit()
        except Exception as exc:
            print("pomodoro: could not save state:", exc)

    # ------------------------------------------------------------------ user interface

    def _build(self):
        self.root = lv.obj()
        self.root.set_style_pad_all(8, 0)
        self.root.set_style_border_width(0, 0)
        self.root.set_style_radius(0, 0)
        self.root.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        self.root.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self.root.set_flex_align(lv.FLEX_ALIGN.SPACE_EVENLY,
                                 lv.FLEX_ALIGN.CENTER,
                                 lv.FLEX_ALIGN.CENTER)

        self.phase_label = lv.label(self.root)
        self.phase_label.set_text(TITLES[WORK])

        self.time_label = lv.label(self.root)
        font = _big_font()
        if font is not None:
            self.time_label.set_style_text_font(font, 0)
        self.time_label.set_text("--:--")

        self.bar = lv.bar(self.root)
        self.bar.set_size(lv.pct(88), 8)
        self.bar.set_range(0, 1000)
        self.bar.set_value(0, lv.ANIM.OFF)

        self.status_label = lv.label(self.root)
        self.status_label.set_text("")

        row = lv.obj(self.root)
        row.set_size(lv.pct(100), lv.SIZE_CONTENT)
        row.set_style_border_width(0, 0)
        row.set_style_bg_opa(lv.OPA.TRANSP, 0)
        row.set_style_pad_all(0, 0)
        row.set_style_pad_column(4, 0)
        row.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        row.set_flex_flow(lv.FLEX_FLOW.ROW)
        row.set_flex_align(lv.FLEX_ALIGN.SPACE_EVENLY,
                           lv.FLEX_ALIGN.CENTER,
                           lv.FLEX_ALIGN.CENTER)

        self.start_btn, self.start_lbl = self._button(row, "Start", self._toggle)
        self._button(row, "Reset", self._reset)
        self._button(row, "Skip", self._skip)
        self._button(row, GEAR, self._open_settings)

    def _button(self, parent, text, callback):
        btn = lv.button(parent)
        btn.set_style_pad_hor(8, 0)
        btn.set_style_pad_ver(6, 0)
        label = lv.label(btn)
        label.set_text(text)
        label.center()
        btn.add_event_cb(lambda event, cb=callback: cb(), lv.EVENT.CLICKED, None)
        try:
            group = lv.group_get_default()
            if group:
                group.add_obj(btn)
        except Exception:
            pass
        return btn, label

    def _draw(self):
        """Full refresh after a state change."""
        color = lv.color_hex(COLORS[self.phase])
        self.phase_label.set_text(TITLES[self.phase])
        self.phase_label.set_style_text_color(color, 0)
        self.time_label.set_style_text_color(color, 0)
        try:
            self.bar.set_style_bg_color(color, lv.PART.INDICATOR)
        except Exception:
            pass
        self.start_lbl.set_text("Pause" if self.running else "Start")
        rounds = max(1, self.cfg["rounds"])
        self.status_label.set_text("Round %d/%d    Today %d" % (
            (self.round % rounds) + 1, rounds, self.done_today))
        self._shown = -1
        self._update_time()

    def _update_time(self):
        secs = (self.remaining_ms + 999) // 1000
        if secs == self._shown:
            return
        self._shown = secs
        self.time_label.set_text("%02d:%02d" % (secs // 60, secs % 60))
        total = self._phase_ms()
        if total > 0:
            done = 1000 - (self.remaining_ms * 1000 // total)
            self.bar.set_value(max(0, min(1000, done)), lv.ANIM.OFF)

    # ----------------------------------------------------------------- the clock

    def _minutes(self, phase):
        if phase == WORK:
            return max(1, self.cfg["work_min"])
        if phase == SHORT:
            return max(1, self.cfg["short_min"])
        return max(1, self.cfg["long_min"])

    def _phase_ms(self):
        return self._minutes(self.phase) * 60000

    def _set_phase(self, phase):
        self.phase = phase
        self.running = False
        self.remaining_ms = self._phase_ms()
        self._draw()

    def _toggle(self):
        if self.running:
            self.remaining_ms = max(0, time.ticks_diff(self.deadline, time.ticks_ms()))
            self.running = False
        else:
            if self.remaining_ms <= 0:
                self.remaining_ms = self._phase_ms()
            self.deadline = time.ticks_add(time.ticks_ms(), self.remaining_ms)
            self.running = True
        self._draw()

    def _reset(self):
        self._leds_clear()
        self._set_phase(self.phase)

    def _skip(self):
        self._advance(alert=False)

    def _advance(self, alert=True):
        finished = self.phase
        if finished == WORK:
            self.done_today += 1
            self.round += 1
            rounds = max(1, self.cfg["rounds"])
            nxt = LONG if self.round % rounds == 0 else SHORT
        else:
            nxt = WORK
        self._save()
        if alert:
            self._alert(finished)
        self._set_phase(nxt)
        if alert and self.cfg["autostart"]:
            self._toggle()

    # -------------------------------------------------------------- frame ticker

    def _tick_on(self):
        if self._ticking:
            return
        try:
            mpos.ui.task_handler.add_event_cb(self.update_frame, 1)
            self._ticking = True
        except Exception as exc:
            print("pomodoro: no frame callback available:", exc)

    def _tick_off(self):
        if not self._ticking:
            return
        try:
            mpos.ui.task_handler.remove_event_cb(self.update_frame)
        except Exception:
            pass
        self._ticking = False

    def update_frame(self, a, b):
        now = time.ticks_ms()
        if self.running:
            left = time.ticks_diff(self.deadline, now)
            if left <= 0:
                self.remaining_ms = 0
                self._update_time()
                self._advance(alert=True)
                return
            self.remaining_ms = left
            self._update_time()
        self._leds_update(now)

    # ------------------------------------------------------------ sound and light

    def _alert(self, finished_phase):
        if self.cfg["sound"]:
            self._play(CHIME_END_WORK if finished_phase == WORK else CHIME_END_BREAK)
        if self.cfg["leds"]:
            self._flash_until = time.ticks_add(time.ticks_ms(), FLASH_MS)

    def _play(self, rtttl):
        if AudioManager is None:
            return
        try:
            player = AudioManager.rtttl_player(
                rtttl, stream_type=AudioManager.STREAM_ALARM)
            player.start()
        except Exception as exc:
            print("pomodoro: could not play chime:", exc)

    def _leds_ok(self):
        try:
            return LightsManager is not None and LightsManager.is_available()
        except Exception:
            return False

    def _leds_apply(self, key, rgb):
        if key == self._led_key:
            return
        self._led_key = key
        try:
            if rgb is None:
                LightsManager.clear()
            else:
                LightsManager.set_all(*rgb)
            LightsManager.write()
        except Exception as exc:
            print("pomodoro: LED update failed:", exc)

    def _leds_update(self, now):
        if not self.cfg["leds"] or not self._leds_ok():
            return
        if time.ticks_diff(self._flash_until, now) > 0:
            on = (now // FLASH_PERIOD_MS) % 2 == 0
            self._leds_apply(("flash", self.phase, on),
                             LED_RGB[self.phase] if on else None)
            return
        if self.running:
            r, g, b = LED_RGB[self.phase]
            self._leds_apply(("run", self.phase),
                             (int(r * LED_DIM), int(g * LED_DIM), int(b * LED_DIM)))
        else:
            self._leds_apply(("off",), None)

    def _leds_clear(self):
        self._flash_until = 0
        if self._leds_ok():
            self._led_key = None
            self._leds_apply(("off",), None)

    # ------------------------------------------------------------------ settings

    def _open_settings(self):
        self.startActivity(Intent(activity_class=PomodoroSettings))
