import json
import time

import bitmaptools

from matrixbox.app import App
from matrixbox.color import hex_to_rgb
from matrixbox.display import display
from matrixbox.fonts import LARGE

STOPPED = 0
RUNNING = 1
PAUSED = 2
FINISHED = 3


def _fmt(ms, tenths=True):
    ms = max(0, int(ms))
    total_s = ms // 1000
    tenth = (ms % 1000) // 100
    hours = total_s // 3600
    minutes = (total_s % 3600) // 60
    seconds = total_s % 60
    mm = ("0" + str(minutes))[-2:]
    ss = ("0" + str(seconds))[-2:]
    if hours > 0:
        return str(hours) + ":" + mm + ":" + ss

    if tenths:
        return mm + ":" + ss + "." + str(tenth)

    return mm + ":" + ss


class StopwatchApp(App):
    title = "Stopwatch"
    tick_seconds = 0.05
    default_settings = {
        "fg_hex": "#00ff88",
        "bg_hex": "#000000",
        "accent_hex": "#ff4400",
        "mode": "stopwatch",
        "preset_ms": 60000,
        "show_tenths": 1,
        "scale": 2,
    }

    def on_start(self):
        with open("template.html") as f:
            self.html_body = f.read()

        self.bg_slot = display.palette_allocator.allocate((0, 0, 0))
        self.digit_slot = display.palette_allocator.allocate((0, 255, 136))
        self.accent_slot = display.palette_allocator.allocate((255, 68, 0))
        self.track_slot = display.palette_allocator.allocate((20, 20, 20))

        self.state = STOPPED
        self.elapsed_ms = 0
        self.start_mono = 0.0
        self._last_draw = None
        self._apply_colors()

        @self.router.route("/state")
        def _state(request):
            ms = self._now_ms()
            disp = (
                max(0, int(self.config["preset_ms"]) - ms)
                if self.config["mode"] == "countdown"
                else ms
            )
            names = ("stopped", "running", "paused", "finished")

            return (
                200,
                {},
                json.dumps(
                    {
                        "state": names[self.state],
                        "ms": disp,
                        "mode": self.config["mode"],
                        "preset_ms": int(self.config["preset_ms"]),
                    }
                ),
            )

        @self.router.route("/action", method="POST")
        def _action(request):
            action = request.params.get("action", "")
            if action == "start":
                self._start()
            elif action == "pause":
                self._pause()
            elif action == "toggle":
                self._toggle()
            elif action == "reset":
                self._reset()

            return (200, {}, "ok")

        @self.router.route("/preset", method="POST")
        def _preset(request):
            raw = request.params.get("v", "").replace("%3A", ":").strip()
            try:
                if ":" in raw:
                    parts = raw.split(":")
                    if len(parts) == 2:
                        preset_ms = (int(parts[0]) * 60 + int(parts[1])) * 1000
                    elif len(parts) == 3:
                        preset_ms = (
                            int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                        ) * 1000
                    else:
                        return (400, {}, "bad preset")
                elif raw:
                    preset_ms = max(1000, int(float(raw) * 1000))
                else:
                    return (400, {}, "bad preset")
            except ValueError:
                return (400, {}, "bad preset")

            self.config.set("preset_ms", preset_ms)
            self._last_draw = None

            return (200, {}, "ok")

    def render(self) -> str:
        return self.html_body

    def on_settings_saved(self, values):
        if any(k in values for k in ("fg_hex", "bg_hex", "accent_hex")):
            self._apply_colors()

        self._last_draw = None

    def on_button(self):
        self._toggle()

    def on_update(self, now):
        ms = self._now_ms()

        if (
            self.config["mode"] == "countdown"
            and self.state == RUNNING
            and ms >= int(self.config["preset_ms"])
        ):
            self.elapsed_ms = int(self.config["preset_ms"])
            self.state = FINISHED

        flashing = self.state == FINISHED and int(now * 2) % 2
        display.palette_allocator.set(
            self.digit_slot, self.accent_rgb if flashing else self.fg_rgb
        )

        self._draw(ms)
        display.refresh()

    def _now_ms(self):
        if self.state == RUNNING:
            return int((time.monotonic() - self.start_mono) * 1000) + self.elapsed_ms

        return self.elapsed_ms

    def _start(self):
        if self.config["mode"] == "countdown" and self.elapsed_ms >= int(
            self.config["preset_ms"]
        ):
            self.elapsed_ms = 0

        self.state = RUNNING
        self.start_mono = time.monotonic()

    def _pause(self):
        if self.state == RUNNING:
            self.elapsed_ms = self._now_ms()
            self.state = PAUSED

    def _reset(self):
        self.state = STOPPED
        self.elapsed_ms = 0
        self.start_mono = 0.0
        display.palette_allocator.set(self.digit_slot, self.fg_rgb)
        self._last_draw = None

    def _toggle(self):
        if self.state == RUNNING:
            self._pause()
        elif self.state == FINISHED:
            self._reset()
        else:
            self._start()

    def _apply_colors(self):
        self.fg_rgb = hex_to_rgb(self.config["fg_hex"])
        self.accent_rgb = hex_to_rgb(self.config["accent_hex"])
        display.palette_allocator.set(self.bg_slot, hex_to_rgb(self.config["bg_hex"]))
        display.palette_allocator.set(self.accent_slot, self.accent_rgb)
        display.palette_allocator.set(self.digit_slot, self.fg_rgb)

    def _draw(self, ms):
        show_tenths = bool(int(self.config["show_tenths"]))
        countdown = self.config["mode"] == "countdown"
        disp_ms = max(0, int(self.config["preset_ms"]) - ms) if countdown else ms
        text = _fmt(disp_ms, show_tenths)
        tag = text + str(self.state)
        if tag == self._last_draw:
            return

        self._last_draw = tag

        scale = max(1, int(self.config["scale"]))
        text_w = LARGE.text_width(text)
        while scale > 1 and (
            text_w * scale > display.width - 2
            or LARGE.height * scale > display.height - 4
        ):
            scale -= 1

        glyphs = display.new_canvas(text_w + 2, LARGE.height + 2)
        glyphs.text(text, 0, 0, font=LARGE, color=self.digit_slot)

        progress_h = 3 if countdown and int(self.config["preset_ms"]) > 0 else 0
        display.canvas.fill_rect(0, 0, display.width, display.height, self.bg_slot)

        time_area_h = display.height - progress_h
        scaled_h = LARGE.height * scale
        time_y = max((time_area_h - scaled_h) // 2, 0)

        if scale == 1:
            text_x = max((display.width - text_w) // 2, 0)
            display.canvas.blit(glyphs, text_x, time_y, skip=0)
        else:
            bitmaptools.rotozoom(
                display.canvas.bitmap,
                glyphs.bitmap,
                ox=display.width // 2,
                oy=time_y + (glyphs.height // 2) * scale,
                px=glyphs.width // 2,
                py=glyphs.height // 2,
                angle=0.0,
                scale=float(scale),
                skip_index=0,
            )

        if progress_h:
            total = int(self.config["preset_ms"])
            remain = max(0, total - ms)
            bar_w = int(display.width * remain // total) if total > 0 else 0
            bar_y = display.height - progress_h
            display.canvas.fill_rect(
                0, bar_y, display.width, progress_h, self.track_slot
            )
            if bar_w > 0:
                display.canvas.fill_rect(0, bar_y, bar_w, progress_h, self.accent_slot)


StopwatchApp().run()
