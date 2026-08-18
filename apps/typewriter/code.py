import json

from matrixbox.app import App
from matrixbox.display import display
from matrixbox.fonts import font_by_name

# Matches the color swatches in template.html — see docs/ARCHITECTURE.md
# (PaletteAllocator: always re-allocate, never hardcode a slot number).
_COLOR_RGB = {
    "yellow": (204, 204, 0),
    "white": (204, 204, 204),
    "brightwhite": (255, 255, 255),
    "blue": (0, 136, 255),
    "red": (255, 34, 34),
    "green": (0, 221, 0),
    "orange": (255, 136, 0),
    "pink": (255, 102, 170),
    "light_blue": (102, 170, 255),
}
_AVG_CHAR_WIDTH = {"mini": 4, "small": 6, "large": 8}


class TypewriterApp(App):
    title = "Typewriter"

    def on_start(self):
        with open("template.html") as f:
            self.html_body = f.read()

        self.color_slots = {
            name: display.palette_allocator.allocate(rgb)
            for name, rgb in _COLOR_RGB.items()
        }
        self.font_name = "mini"
        self.lines = []

        @self.router.route("/tw/info")
        def _info(request):
            return (200, {}, self._info_json())

        @self.router.route("/tw/render", method="POST")
        def _render_route(request):
            if "font" in request.params:
                self.font_name = request.params["font"]

            try:
                self.lines = json.loads(request.body or "[]")
                self._render()
            except ValueError as e:
                print(f"typewriter: bad render payload: {e}")

            return (200, {}, self._info_json())

        self._render()

    def render(self) -> str:
        return self.html_body

    def _info_json(self) -> str:
        font = font_by_name(self.font_name)
        avg_cw = _AVG_CHAR_WIDTH.get(self.font_name, 6)

        return json.dumps(
            {
                "w": display.width,
                "h": display.height,
                "rows": display.height // font.height,
                "cols": display.width // avg_cw,
                "font": self.font_name,
            }
        )

    def _render(self):
        font = font_by_name(self.font_name)
        row_h = font.height
        max_rows = display.height // row_h

        display.canvas.fill(0)
        for row, segments in enumerate(self.lines[:max_rows]):
            x = 1
            y = row * row_h + 1
            for segment in segments:
                text = segment.get("t", "")
                slot = self.color_slots.get(segment.get("c"), self.color_slots["white"])
                x += display.canvas.text(text, x, y, font=font, color=slot)

        display.refresh()


TypewriterApp().run()
