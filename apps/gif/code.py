import binascii
import os

import bitmaptools
import displayio
import gifio

from matrixbox.app import App
from matrixbox.display import display
from matrixbox.fonts import SMALL

IMAGES_DIR = "images"


class GifApp(App):
    title = "GIF Player"
    tick_seconds = 0.01
    default_settings = {"brightness": 0.25}

    def on_start(self):
        with open("template.html") as f:
            self.html_body = f.read()

        try:
            os.mkdir(IMAGES_DIR)
        except OSError:
            pass  # already exists

        self.files = sorted(os.listdir(IMAGES_DIR))
        self.index = 0
        self.odg = None
        self.black_bmp = None
        self.dim_bmp = None
        # displayio bypasses matrixbox.display's indexed Canvas entirely
        # here — a GIF needs full RGB565 color, not a 20-slot palette —
        # see docs/ARCHITECTURE.md. display.restore_root_canvas() in
        # run_app()'s finally block undoes this on exit; nothing here
        # needs to restore it itself.
        self.group = displayio.Group()

        @self.router.route("/next", method="POST")
        def _next(request):
            self._advance()

            return (200, {}, "ok")

        @self.router.route("/upload", method="POST")
        def _upload(request):
            try:
                raw = binascii.a2b_base64(request.body or "")
                with open(IMAGES_DIR + "/uploaded.gif", "wb") as f:
                    f.write(raw)
            except (ValueError, OSError) as e:
                print(f"gif: upload failed: {e}")

                return (500, {}, str(e))

            if "uploaded.gif" not in self.files:
                self.files.append("uploaded.gif")

            self.index = self.files.index("uploaded.gif")
            self._load_current()

            return (200, {}, "ok")

        if self.files:
            self._load_current()
        else:
            display.canvas.fill(0)
            display.canvas.text("Upload GIF", 0, 0, font=SMALL, color=5)
            display.refresh()

    def render(self) -> str:
        return self.html_body

    def on_button(self):
        self._advance()

    def on_settings_saved(self, values):
        if "brightness" in values and self.odg is not None:
            self._blend()
            display.refresh()

    def on_update(self, now):
        if self.odg is None:
            return

        self.odg.next_frame()
        self._blend()
        display.refresh()

    def _advance(self):
        if not self.files:
            return

        self.index = (self.index + 1) % len(self.files)
        self._load_current()

    def _load_current(self):
        self._load(IMAGES_DIR + "/" + self.files[self.index])

    def _blend(self):
        try:
            bitmaptools.alphablend(
                self.dim_bmp,
                self.odg.bitmap,
                self.black_bmp,
                displayio.Colorspace.RGB565_SWAPPED,
                factor_1=float(self.config["brightness"]),
            )
        except Exception as e:  # broad: unclear what alphablend can raise here
            print(f"gif: blend failed: {e}")

    def _load(self, path):
        self.odg = gifio.OnDiskGif(path)
        w, h = self.odg.bitmap.width, self.odg.bitmap.height
        self.black_bmp = displayio.Bitmap(w, h, 65536)
        self.dim_bmp = displayio.Bitmap(w, h, 65536)
        self.odg.next_frame()
        self._blend()

        while len(self.group) > 0:
            self.group.pop()

        face = displayio.TileGrid(
            self.dim_bmp,
            pixel_shader=displayio.ColorConverter(
                input_colorspace=displayio.Colorspace.RGB565_SWAPPED,
                dither=True,
            ),
        )
        self.group.append(face)
        display.set_root_group(self.group)
        display.refresh()


GifApp().run()
