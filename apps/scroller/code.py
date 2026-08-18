import wifi

from matrixbox.app import App
from matrixbox.color import hex_to_rgb
from matrixbox.display import display
from matrixbox.fonts import font_by_name
from matrixbox.scroll import Direction, Scroller

PADDING = 20

_SHADOW_COLORS = {
    "black": (0, 0, 0),
    "yellow": (140, 140, 0),
    "brightwhite": (255, 255, 255),
    "blue": (0, 60, 140),
    "red": (140, 0, 0),
    "white": (140, 140, 140),
    "light_blue": (100, 170, 255),
    "green": (0, 140, 20),
    "grey": (60, 60, 60),
    "black2": (30, 30, 30),
    "pink": (140, 0, 60),
    "orange": (140, 80, 0),
}


class ScrollerApp(App):
    title = "Scroller"
    default_settings = {
        "text": "",  # replaced with this device's own IP on first run
        "mode": "h",  # h(orizontal) / v(ertical) / s(tatic)
        "align": "center",  # static and vertical modes only
        "reverse": 1,
        "font": "large",
        "color_hex": "#ffffff",
        "shadow": "black",
        "offset": 0,
        "speed": 1,  # pixels per tick, 1-5 — see docs/ARCHITECTURE.md
    }

    def on_start(self):
        with open("template.html") as f:
            self.html_body = f.read()

        if not self.config["text"]:
            self.config.set("text", "http://" + str(wifi.radio.ipv4_address))

        self.text_slot = display.palette_allocator.allocate(
            hex_to_rgb(self.config["color_hex"])
        )
        self.shadow_slot = display.palette_allocator.allocate(
            _SHADOW_COLORS.get(self.config["shadow"], (0, 0, 0))
        )
        self.scroller = None
        self.static_canvas = None
        # Scratch buffer scrolling/static content is composited into before
        # the offset shift, so offset math never depends on Scroller.draw()'s
        # own dest-clipping behavior — see docs/ARCHITECTURE.md.
        self.viewport = display.new_canvas(display.width, display.height)

        self._rebuild()

    def render(self) -> str:
        return self.html_body

    def on_settings_saved(self, values):
        if "color_hex" in values:
            display.palette_allocator.set(
                self.text_slot, hex_to_rgb(self.config["color_hex"])
            )

        if "shadow" in values:
            display.palette_allocator.set(
                self.shadow_slot, _SHADOW_COLORS.get(self.config["shadow"], (0, 0, 0))
            )

        rebuild_keys = (
            "text",
            "mode",
            "align",
            "font",
            "reverse",
            "color_hex",
            "shadow",
            "speed",
        )
        if any(k in values for k in rebuild_keys):
            self._rebuild()
        elif "offset" in values:
            self._draw_frame()

    def on_button(self):
        modes = ("h", "v", "s")
        current = (
            modes.index(self.config["mode"]) if self.config["mode"] in modes else 0
        )
        self.config.set("mode", modes[(current + 1) % len(modes)])
        self._rebuild()

    def on_update(self, now):
        if self.scroller and self.scroller.update(now):
            self._draw_frame()

    def _rebuild(self):
        font = font_by_name(self.config["font"])
        lines = self.config["text"].replace("\r", "").split("\n")
        mode = self.config["mode"]
        reverse = int(self.config["reverse"])
        speed = max(1, min(int(self.config["speed"]), 5))

        self.scroller = None
        self.static_canvas = None

        if mode == "v":
            self._rebuild_vertical(font, lines, reverse, speed)
        elif mode == "s":
            self._rebuild_static(font, lines)
        else:
            self._rebuild_horizontal(font, lines, reverse, speed)

        # Content that fits the viewport with no scrolling needed (a single
        # short line, a static layout) would otherwise never get an initial
        # draw — Scroller.update() only returns True on an actual position
        # change, which never happens when nothing needs to scroll — see
        # docs/ARCHITECTURE.md.
        self._draw_frame()

    def _draw_frame(self):
        self.viewport.fill(0)
        if self.scroller:
            self.scroller.draw(self.viewport, 0, 0)
        elif self.static_canvas:
            self.viewport.blit(
                self.static_canvas,
                0,
                0,
                x2=min(self.static_canvas.width, display.width),
                y2=min(self.static_canvas.height, display.height),
            )

        offset = max(0, min(int(self.config["offset"]), display.height))
        visible_h = display.height - offset
        display.canvas.fill(0)
        if visible_h > 0:
            display.canvas.blit(self.viewport, 0, offset, y1=0, y2=visible_h)

        display.refresh()

    def _rebuild_vertical(self, font, lines, reverse, speed):
        # A full viewport-height cell per line meant a single line's canvas
        # was exactly viewport height — Scroller.needs_scroll stayed False
        # forever, so short text (the common case) never moved at all, only
        # multi-line text did — see docs/ARCHITECTURE.md. A viewport-height
        # blank pad above and below guarantees room to scroll regardless of
        # line count, mirroring how horizontal mode's PADDING spaces do the
        # same on that axis, and doubles as a seamless loop point — both
        # ends of the scroll range show nothing but blank pad, so the jump
        # back to the start is invisible.
        row_h = font.height + 2
        pad = display.height
        align = self.config["align"]
        canvas = display.new_canvas(display.width, max(len(lines), 1) * row_h + pad * 2)

        for i, line in enumerate(lines):
            if not line.strip():
                continue

            width = font.text_width(line)
            if align == "left":
                x = 1
            elif align == "right":
                x = canvas.width - width - 1
            else:
                x = max((canvas.width - width) // 2, 1)

            canvas.text(
                line,
                x,
                pad + i * row_h,
                font=font,
                color=self.text_slot,
                shadow=self.shadow_slot,
            )

        direction = Direction.UP if reverse else Direction.DOWN
        self.scroller = Scroller(
            canvas, display.width, display.height, direction=direction, speed=speed
        )

    def _rebuild_static(self, font, lines):
        row_h = font.height + 2
        widths = [font.text_width(line) for line in lines if line.strip()]
        max_w = max(widths) if widths else 1
        canvas = display.new_canvas(
            max(max_w + 2, display.width), max(len(lines) * row_h, display.height)
        )

        align = self.config["align"]
        for i, line in enumerate(lines):
            if not line.strip():
                continue

            width = font.text_width(line)
            if align == "left":
                x = 1
            elif align == "right":
                x = canvas.width - width - 1
            else:
                x = max((canvas.width - width) // 2, 1)

            canvas.text(
                line,
                x,
                i * row_h,
                font=font,
                color=self.text_slot,
                shadow=self.shadow_slot,
            )

        self.static_canvas = canvas

    def _rebuild_horizontal(self, font, lines, reverse, speed):
        gap = " " * PADDING
        text = " " * PADDING + gap.join(lines) + " " * PADDING
        width = max(font.text_width(text), 1)
        canvas = display.new_canvas(width, display.height)
        canvas.text(
            text, 0, 0, font=font, color=self.text_slot, shadow=self.shadow_slot
        )

        direction = Direction.LEFT if reverse else Direction.RIGHT
        self.scroller = Scroller(
            canvas, display.width, display.height, direction=direction, speed=speed
        )


ScrollerApp().run()
