"""Pomodoro timer for the Fri3d badge, running on MicroPythonOS.

Built for a badge sitting on a desk rather than hanging on a lanyard, so the
countdown is drawn as seven-segment digits that fill the screen and stay
readable from across the room, and the five onboard LEDs act as an hourglass
you can read out of the corner of your eye.

Red means focus and green means break, which also tells anyone walking up to
the desk whether they are interrupting.
"""

import time

import lvgl as lv

from mpos import Activity, Intent
import mpos.ui

try:
    # Fri3d 2026 firmware exports this from mpos directly; the docs show it
    # living in mpos.config, which does not exist on this build.
    from mpos import SharedPreferences
except Exception:
    from mpos.config import SharedPreferences

try:
    from mpos import AudioManager
except Exception:
    AudioManager = None

from posettings import PomodoroSettings, APP_ID, DEFAULTS


def _find_lights():
    """LightsManager moved around between builds; find whatever this one has.

    On the Fri3d 2026 badge `from mpos import LightsManager` fails, but the
    `mpos.lights` module is present, either exporting the class or the
    functions themselves.
    """
    try:
        from mpos import LightsManager as found
        return found
    except Exception:
        pass
    try:
        import mpos.lights as module
    except Exception:
        return None
    found = getattr(module, "LightsManager", None)
    if found is not None:
        return found
    if hasattr(module, "write") and hasattr(module, "set_all"):
        return module
    return None


LightsManager = _find_lights()


def _find_start_button():
    """The badge's S button, exposed by the active board module as btn_start.

    On the Fri3d 2026 it is GPIO0 and reads 0 while held, 1 at rest. Going
    through mpos.board rather than machine.Pin keeps the pin shared with the
    firmware instead of reconfiguring it underneath.
    """
    try:
        import mpos.board as board
    except Exception:
        board = None
    if board is not None:
        for name in dir(board):
            if name.startswith("_"):
                continue
            pin = getattr(getattr(board, name, None), "btn_start", None)
            if pin is not None and hasattr(pin, "value"):
                return pin
    try:
        import machine
        return machine.Pin(0, machine.Pin.IN, machine.Pin.PULL_UP)
    except Exception:
        return None


def _lv_const(group, name, fallback):
    """Resolve an LVGL constant across binding styles.

    Different lvgl_micropython builds expose these as `lv.GROUP.NAME`, as a
    flat `lv.GROUP_NAME`, or as `lv.group_t.NAME`. The Fri3d 2026 build has
    no `lv.ANIM` at all, so fall back to the numeric value.
    """
    holder = getattr(lv, group, None)
    if holder is not None:
        value = getattr(holder, name, None)
        if value is not None:
            return value
    value = getattr(lv, group + "_" + name, None)
    if value is not None:
        return value
    holder = getattr(lv, group.lower() + "_enable_t", None)
    if holder is not None:
        value = getattr(holder, name, None)
        if value is not None:
            return value
    return fallback


ANIM_OFF = _lv_const("ANIM", "OFF", 0)
SCROLL_OFF = _lv_const("SCROLLBAR_MODE", "OFF", 0)
OPA_TRANSP = _lv_const("OPA", "TRANSP", 0)
PART_INDICATOR = _lv_const("PART", "INDICATOR", 0x020000)
GEAR = getattr(getattr(lv, "SYMBOL", None), "SETTINGS", None) or "Set"

WORK = "work"
SHORT = "short"
LONG = "long"

TITLES = {WORK: "Focus", SHORT: "Short break", LONG: "Long break"}
COLORS = {WORK: 0xE5484D, SHORT: 0x30A46C, LONG: 0x3E63DD}
LED_RGB = {WORK: (255, 30, 0), SHORT: (0, 255, 50), LONG: (0, 70, 255)}
AMBER = (255, 150, 0)

# Ring Tone Text Transfer Language, played on the badge buzzer. Short, because
# the badge is an arm's length away. Rising when you are freed, falling when
# you are called back, and a distinct one for the end of a long break.
CHIME_END_WORK = "brk:d=8,o=5,b=180:c6,e6,g6"
CHIME_END_SHORT = "wrk:d=8,o=5,b=180:g5,e5,c5"
CHIME_END_LONG = "new:d=8,o=5,b=180:g5,c5,e5,4c5"

SEGMENT_ON_OPA = 255
SEGMENT_GHOST_OPA = 18
FLASH_MS = 2000
FLASH_PERIOD_MS = 200
LED_INTERVAL_MS = 50
PULSE_PERIOD_MS = 1400
START_DEBOUNCE_MS = 300


class _Digit:
    """One seven-segment digit, drawn as seven rectangles."""

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
            part.set_scrollbar_mode(SCROLL_OFF)
            self.parts[name] = part
        self.value = None
        self.color = None

    def set(self, char, color):
        if char == self.value and color == self.color:
            return
        self.value = char
        self.color = color
        lit = self.SEGMENTS.get(char, "")
        shade = lv.color_hex(color)
        for name, part in self.parts.items():
            part.set_style_bg_color(shade, 0)
            part.set_style_bg_opa(
                SEGMENT_ON_OPA if name in lit else SEGMENT_GHOST_OPA, 0)


class _Clock:
    """MM:SS in seven-segment digits, sized to fill the space it is given."""

    def __init__(self, parent, width, height):
        self.height = height
        thickness = max(4, height // 7)
        digit_w = max(2 * thickness + 4, int(height * 0.58))
        gap = max(3, digit_w // 8)
        colon_w = thickness

        xs = [0, digit_w + gap]
        colon_x = 2 * digit_w + 2 * gap
        xs.append(colon_x + colon_w + gap)
        xs.append(xs[2] + digit_w + gap)
        total = xs[3] + digit_w
        offset = max(0, (width - total) // 2)

        self.digits = [
            _Digit(parent, offset + x, 0, digit_w, height, thickness)
            for x in xs
        ]

        self.dots = []
        for dot_y in (int(height * 0.30), int(height * 0.62)):
            dot = lv.obj(parent)
            dot.set_pos(offset + colon_x, dot_y)
            dot.set_size(colon_w, thickness)
            dot.set_style_border_width(0, 0)
            dot.set_style_radius(1, 0)
            dot.set_style_pad_all(0, 0)
            dot.set_scrollbar_mode(SCROLL_OFF)
            self.dots.append(dot)
        self.dots_state = None

    def set_time(self, text, color, dots_lit=True):
        for digit, char in zip(self.digits, text[:2] + text[3:5]):
            digit.set(char, color)
        state = (color, bool(dots_lit))
        if state != self.dots_state:
            self.dots_state = state
            shade = lv.color_hex(color)
            for dot in self.dots:
                dot.set_style_bg_color(shade, 0)
                dot.set_style_bg_opa(
                    SEGMENT_ON_OPA if dots_lit else SEGMENT_GHOST_OPA, 0)


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
        self.time_text = "--:--"
        self._shown = -1
        self._dots = None
        self._flash_until = 0
        self._led_state = None
        self._led_last = 0
        self._led_count = None
        self._ticking = False
        self._durations = None
        self._buzzer_out = False   # False = not looked up yet
        # Keep exactly one bound method: in MicroPython `self.update_frame`
        # yields a new object each time it is read, and removing a different
        # object than the one registered leaves the callback running.
        self._frame_cb = self.update_frame
        # The badge's S button, polled in the frame callback. It is the one
        # control you can hit without looking at the screen, so it gets the
        # action you reach for most: start and pause.
        self._start_pin = _find_start_button()
        self._start_was_down = False
        self._start_last = 0

    # ---------------------------------------------------------------- lifecycle

    def onCreate(self):
        self._load()
        self._build()
        self._set_phase(WORK)
        self.setContentView(self.root)

    def onResume(self, screen):
        super().onResume(screen)
        if self.running:
            # Nothing ticked while we were away, so catch the clock up first.
            self.remaining_ms = max(0, time.ticks_diff(self.deadline, time.ticks_ms()))
        changed = self._load()
        if changed and not self.running:
            self._set_phase(self.phase)
        else:
            if changed and self.running:
                # A shortened phase must not leave more time on the clock than
                # the phase now lasts, or the LEDs would overflow the strip.
                cap = self._phase_ms()
                if self.remaining_ms > cap:
                    self.remaining_ms = cap
                    self.deadline = time.ticks_add(time.ticks_ms(), cap)
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
        prefs = SharedPreferences(APP_ID)
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
            editor = SharedPreferences(APP_ID).edit()
            editor.put_string("day", self.day)
            editor.put_int("done_today", self.done_today)
            editor.put_int("round", self.round)
            editor.commit()
        except Exception as exc:
            print("pomodoro: could not save state:", exc)

    # ------------------------------------------------------------------ interface

    def _screen_size(self):
        try:
            active = lv.screen_active()
            width, height = active.get_width(), active.get_height()
            if width and height:
                return width, height
        except Exception:
            pass
        return 320, 240

    def _build(self):
        width, height = self._screen_size()

        self.root = lv.obj()
        self.root.set_style_pad_all(0, 0)
        self.root.set_style_border_width(0, 0)
        self.root.set_style_radius(0, 0)
        self.root.set_scrollbar_mode(SCROLL_OFF)

        self.phase_label = lv.label(self.root)
        self.phase_label.set_text(TITLES[WORK])
        self.phase_label.align(lv.ALIGN.TOP_MID, 0, 4)

        clock_h = max(48, int(height * 0.44))
        clock_w = width - 16
        holder = lv.obj(self.root)
        holder.set_size(clock_w, clock_h)
        holder.align(lv.ALIGN.TOP_MID, 0, 26)
        holder.set_style_border_width(0, 0)
        holder.set_style_bg_opa(OPA_TRANSP, 0)
        holder.set_style_pad_all(0, 0)
        holder.set_scrollbar_mode(SCROLL_OFF)
        self.clock = _Clock(holder, clock_w, clock_h)

        self.bar = lv.bar(self.root)
        self.bar.set_size(width - 40, 6)
        self.bar.align(lv.ALIGN.TOP_MID, 0, 30 + clock_h)
        self.bar.set_range(0, 1000)
        self.bar.set_value(0, ANIM_OFF)

        self.status_label = lv.label(self.root)
        self.status_label.set_text("")
        self.status_label.align(lv.ALIGN.TOP_MID, 0, 42 + clock_h)

        row = lv.obj(self.root)
        row.set_size(width, 48)
        row.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        row.set_style_border_width(0, 0)
        row.set_style_bg_opa(OPA_TRANSP, 0)
        row.set_style_pad_all(2, 0)
        row.set_style_pad_column(4, 0)
        row.set_scrollbar_mode(SCROLL_OFF)
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
        btn.set_style_pad_hor(6, 0)
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
        color = COLORS[self.phase]
        self.phase_label.set_text(TITLES[self.phase])
        self.phase_label.set_style_text_color(lv.color_hex(color), 0)
        try:
            self.bar.set_style_bg_color(lv.color_hex(color), PART_INDICATOR)
        except Exception:
            pass
        self.start_lbl.set_text("Pause" if self.running else "Start")
        rounds = max(1, self.cfg["rounds"])
        self.status_label.set_text("Round %d/%d    Today %d" % (
            (self.round % rounds) + 1, rounds, self.done_today))
        self._shown = -1
        self._dots = None
        self._update_time()

    def _update_time(self):
        secs = (self.remaining_ms + 999) // 1000
        dots = (not self.running) or (secs % 2 == 0)
        if secs == self._shown and dots == self._dots:
            return
        self._shown = secs
        self._dots = dots
        self.time_text = "%02d:%02d" % (secs // 60, secs % 60)
        self.clock.set_time(self.time_text, COLORS[self.phase], dots)
        total = self._phase_ms()
        if total > 0:
            done = 1000 - (self.remaining_ms * 1000 // total)
            self.bar.set_value(max(0, min(1000, done)), ANIM_OFF)

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
            mpos.ui.task_handler.add_event_cb(self._frame_cb, 1)
            self._ticking = True
        except Exception as exc:
            print("pomodoro: no frame callback available:", exc)

    def _tick_off(self):
        if not self._ticking:
            return
        try:
            mpos.ui.task_handler.remove_event_cb(self._frame_cb)
        except Exception:
            pass
        self._ticking = False

    def _poll_start_button(self, now):
        if self._start_pin is None:
            return
        try:
            down = self._start_pin.value() == 0
        except Exception as exc:
            print("pomodoro: start button unreadable, ignoring it:", exc)
            self._start_pin = None
            return
        if down and not self._start_was_down:
            if time.ticks_diff(now, self._start_last) > START_DEBOUNCE_MS:
                self._start_last = now
                self._start_was_down = True
                self._toggle()
                return
        if not down:
            self._start_was_down = False

    def update_frame(self, a, b):
        now = time.ticks_ms()
        self._poll_start_button(now)
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
            if finished_phase == WORK:
                self._play(CHIME_END_WORK)
            elif finished_phase == SHORT:
                self._play(CHIME_END_SHORT)
            else:
                self._play(CHIME_END_LONG)
        if self.cfg["leds"]:
            self._flash_until = time.ticks_add(time.ticks_ms(), FLASH_MS)

    def _buzzer(self):
        """The badge buzzer, not the headset, which is the default output."""
        if self._buzzer_out is not False:
            return self._buzzer_out
        self._buzzer_out = None
        try:
            for out in AudioManager.get_outputs():
                if getattr(out, "kind", None) == "buzzer" or "kind=buzzer" in repr(out):
                    self._buzzer_out = out
                    break
        except Exception as exc:
            print("pomodoro: could not list audio outputs:", exc)
        return self._buzzer_out

    def _play(self, rtttl):
        if AudioManager is None:
            return
        options = {"stream_type": AudioManager.STREAM_ALARM}
        buzzer = self._buzzer()
        if buzzer is not None:
            options["output"] = buzzer
        volume = self.cfg.get("volume")
        try:
            AudioManager.rtttl_player(rtttl, volume=volume, **options).start()
            return
        except Exception:
            pass
        try:
            AudioManager.rtttl_player(rtttl, **options).start()
        except Exception as exc:
            print("pomodoro: could not play chime:", exc)

    def _leds_ok(self):
        try:
            return LightsManager is not None and LightsManager.is_available()
        except Exception:
            return False

    def _leds_n(self):
        if self._led_count is None:
            try:
                self._led_count = max(1, LightsManager.get_led_count())
            except Exception:
                self._led_count = 1
        return self._led_count

    def _dim(self, rgb, factor=1.0):
        """Scale a colour by the brightness setting, clamped to a valid range."""
        level = max(1, min(100, self.cfg.get("brightness", 10))) / 100.0 * factor
        return tuple(max(0, min(255, int(channel * level))) for channel in rgb)

    def _led_colors(self, now):
        """One (r, g, b) per LED, before brightness is applied."""
        count = self._leds_n()
        off = (0, 0, 0)

        if time.ticks_diff(self._flash_until, now) > 0:
            # Brighter than the steady glow so it registers, but still scaled by
            # the brightness setting: this is a desk lamp, not a strobe.
            lit = (now // FLASH_PERIOD_MS) % 2 == 0
            return [self._dim(LED_RGB[self.phase], 4.0) if lit else off] * count

        if self.running:
            total = self._phase_ms()
            # One LED per 1/count of the configured phase, so a five minute
            # focus and a fifty minute one both start with the strip full.
            fraction = 1.0 if total <= 0 else self.remaining_ms / total
            fraction = max(0.0, min(1.0, fraction))
            # Round up, so the strip is full until the first fifth has actually
            # gone by, and the last LED stays lit through the final fifth.
            exact = fraction * count
            remaining = int(exact)
            if remaining < exact:
                remaining += 1
            remaining = max(0, min(count, remaining))
            steady = self._dim(LED_RGB[self.phase])
            colors = [steady] * remaining + [off] * (count - remaining)
            if remaining:
                # The last one breathes, so the end of the phase is felt coming.
                span = PULSE_PERIOD_MS
                position = (now % span) * 2.0 / span
                wave = position if position < 1.0 else 2.0 - position
                colors[remaining - 1] = self._dim(LED_RGB[self.phase],
                                                  0.25 + 0.75 * wave)
            return colors

        if self.remaining_ms < self._phase_ms():
            # Paused, which should look different from switched off.
            span = PULSE_PERIOD_MS * 2
            position = (now % span) * 2.0 / span
            wave = position if position < 1.0 else 2.0 - position
            colors = [off] * count
            colors[count // 2] = self._dim(AMBER, 0.3 + 0.7 * wave)
            return colors

        # Idle at the top of a phase: show which phase is waiting.
        colors = [off] * count
        colors[0] = self._dim(LED_RGB[self.phase], 0.6)
        return colors

    def _leds_update(self, now):
        if not self.cfg["leds"] or not self._leds_ok():
            if self._led_state is not None:
                self._leds_clear()
            return
        if self._led_state is not None and time.ticks_diff(now, self._led_last) < LED_INTERVAL_MS:
            return
        self._led_last = now

        colors = self._led_colors(now)
        if colors == self._led_state:
            return
        self._led_state = colors
        try:
            for index, (red, green, blue) in enumerate(colors):
                LightsManager.set_led(index, red, green, blue)
            LightsManager.write()
        except Exception as exc:
            print("pomodoro: LED update failed:", exc)

    def _leds_clear(self):
        self._flash_until = 0
        self._led_state = None
        if self._leds_ok():
            try:
                LightsManager.clear()
                LightsManager.write()
            except Exception:
                pass

    # ------------------------------------------------------------------ settings

    def _open_settings(self):
        # Nothing meaningful to show while the durations are being edited, and
        # animating through the change looks like a fault.
        self._tick_off()
        self._leds_clear()
        self.startActivity(Intent(activity_class=PomodoroSettings))
