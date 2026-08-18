import json
import os

from matrixbox.app import App
from matrixbox.color import Color
from matrixbox.display import display

SAVE_DIR = "saves"

# Slot 0 is always black (system palette) — everything else gets a fresh
# slot every launch, never hardcoded — see docs/ARCHITECTURE.md.
_PALETTE_COLORS = (
    Color.WHITE,
    Color.BRIGHT_WHITE,
    Color.RED,
    Color.GREEN,
    Color.BLUE,
    Color.YELLOW,
    Color.CYAN,
    Color.MAGENTA,
    Color.ORANGE,
    Color.PINK,
    Color.GREY,
)


# str.isalnum() isn't implemented on this CircuitPython build — confirmed
# via /console, see docs/ARCHITECTURE.md.
_SAFE_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"


def _safe_name(name: str) -> str:
    return "".join(c for c in name if c in _SAFE_CHARS)[:20]


class PaintApp(App):
    title = "Paint"

    def on_start(self):
        try:
            os.mkdir(SAVE_DIR)
        except OSError:
            pass  # already exists

        palette = {0: (0, 0, 0)}
        for rgb in _PALETTE_COLORS:
            slot = display.palette_allocator.allocate(rgb)
            palette[slot] = rgb

        default_slot = min(s for s in palette if s != 0)

        with open("template.html") as f:
            self.html_body = (
                f.read()
                .replace("__WIDTH__", str(display.width))
                .replace("__HEIGHT__", str(display.height))
                .replace("__PALETTE__", json.dumps(palette))
                .replace("__DEFAULT__", str(default_slot))
            )

        display.canvas.fill(0)
        display.refresh()

        @self.router.route("/px", method="POST")
        def _px(request):
            try:
                data = json.loads(request.body)
                color = int(data["c"])
                for x, y in data["pts"]:
                    display.canvas.pixel(int(x), int(y), color)

                display.refresh()
            except (ValueError, KeyError) as e:
                print(f"paint: bad /px payload: {e}")

            return (200, {}, "ok")

        @self.router.route("/fill", method="POST")
        def _fill(request):
            try:
                data = json.loads(request.body)
                self._flood_fill(int(data["x"]), int(data["y"]), int(data["c"]))
                display.refresh()
            except (ValueError, KeyError) as e:
                print(f"paint: bad /fill payload: {e}")

            return (200, {}, "ok")

        @self.router.route("/clear", method="POST")
        def _clear(request):
            display.canvas.fill(0)
            display.refresh()

            return (200, {}, "ok")

        @self.router.route("/saves")
        def _list_saves(request):
            try:
                names = [f[:-5] for f in os.listdir(SAVE_DIR) if f.endswith(".json")]
            except OSError:
                names = []

            return (200, {"Content-Type": "application/json"}, json.dumps(names))

        @self.router.route("/save", method="POST")
        def _save(request):
            try:
                data = json.loads(request.body)
                name = _safe_name(data["name"])
            except (ValueError, KeyError) as e:
                return (400, {}, f"bad request: {e}")

            if not name:
                return (400, {}, "bad name")

            # Written row by row rather than building the whole grid (and
            # its full JSON string) in memory at once — measured to run
            # this route out of memory on real hardware at full canvas
            # size, several stack frames deeper than a top-level script
            # — see docs/ARCHITECTURE.md.
            with open(SAVE_DIR + "/" + name + ".json", "w") as f:
                f.write(
                    '{"w":'
                    + str(display.width)
                    + ',"h":'
                    + str(display.height)
                    + ',"d":['
                )
                for y in range(display.height):
                    if y:
                        f.write(",")

                    row = [display.canvas.get_pixel(x, y) for x in range(display.width)]
                    f.write(json.dumps(row))

                f.write("]}")

            return (200, {}, "ok")

        @self.router.route("/load", method="POST")
        def _load(request):
            try:
                data = json.loads(request.body)
                name = _safe_name(data["name"])
                with open(SAVE_DIR + "/" + name + ".json") as f:
                    saved = json.load(f)
            except (ValueError, KeyError, OSError) as e:
                return (500, {}, str(e))

            rows = saved["d"]
            display.canvas.fill(0)
            for y in range(min(display.height, len(rows))):
                for x in range(min(display.width, len(rows[y]))):
                    display.canvas.pixel(x, y, rows[y][x])

            display.refresh()

            return (200, {"Content-Type": "application/json"}, json.dumps({"d": rows}))

        @self.router.route("/delete", method="POST")
        def _delete(request):
            try:
                data = json.loads(request.body)
                name = _safe_name(data["name"])
                os.remove(SAVE_DIR + "/" + name + ".json")
            except (ValueError, KeyError, OSError) as e:
                print(f"paint: delete failed: {e}")

            return (200, {}, "ok")

    def render(self) -> str:
        return self.html_body

    def _flood_fill(self, start_x, start_y, color):
        # Scanline fill, not a per-pixel BFS — a naive one-pixel-at-a-time
        # fill measured well over two minutes for a few thousand pixels on
        # real hardware (thousands of individual native pixel calls from
        # interpreted Python). This fills each contiguous horizontal run
        # with one fill_rect() call and queues one seed point per run
        # above/below instead of one per pixel — see docs/ARCHITECTURE.md.
        if not (0 <= start_x < display.width and 0 <= start_y < display.height):
            return

        target = display.canvas.get_pixel(start_x, start_y)
        if target == color:
            return

        stack = [(start_x, start_y)]
        while stack:
            x, y = stack.pop()
            if display.canvas.get_pixel(x, y) != target:
                continue

            left = x
            while left - 1 >= 0 and display.canvas.get_pixel(left - 1, y) == target:
                left -= 1

            right = x
            while (
                right + 1 < display.width
                and display.canvas.get_pixel(right + 1, y) == target
            ):
                right += 1

            display.canvas.fill_rect(left, y, right - left + 1, 1, color)

            for ny in (y - 1, y + 1):
                if not (0 <= ny < display.height):
                    continue

                nx = left
                while nx <= right:
                    if display.canvas.get_pixel(nx, ny) == target:
                        stack.append((nx, ny))
                        while (
                            nx <= right and display.canvas.get_pixel(nx, ny) == target
                        ):
                            nx += 1
                    else:
                        nx += 1


PaintApp().run()
