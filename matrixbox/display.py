import os

import bitmaptools
import displayio
import framebufferio
import microcontroller
from rgbmatrix import RGBMatrix

from matrixbox.boards import detect_board
from matrixbox.color import Color, PaletteAllocator
from matrixbox.fonts import SMALL, Font
from matrixbox.settings import settings as _settings

displayio.release_displays()


class Canvas:
    def __init__(self, bitmap, palette):
        self.bitmap = bitmap
        self.palette = palette
        self.width = bitmap.width
        self.height = bitmap.height

    def pixel(self, x, y, color):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.bitmap[x, y] = color

    def get_pixel(self, x, y):
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.bitmap[x, y]

        return None

    def fill(self, color=0):
        self.bitmap.fill(color)

    def fill_rect(self, x, y, w, h, color):
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + w, self.width), min(y + h, self.height)
        if x1 > x0 and y1 > y0:
            bitmaptools.fill_region(self.bitmap, x0, y0, x1, y1, color)

    def rect(self, x, y, w, h, color):
        # Outline only — fill_rect() for a solid block.
        self.fill_rect(x, y, w, 1, color)
        self.fill_rect(x, y + h - 1, w, 1, color)
        self.fill_rect(x, y, 1, h, color)
        self.fill_rect(x + w - 1, y, 1, h, color)

    def line(self, x0, y0, x1, y1, color):
        bitmaptools.draw_line(self.bitmap, x0, y0, x1, y1, color)

    def blit(self, source: "Canvas", x, y, *, x1=0, y1=0, x2=None, y2=None, skip=0):
        x2 = source.width if x2 is None else x2
        y2 = source.height if y2 is None else y2
        bitmaptools.blit(
            self.bitmap,
            source.bitmap,
            x,
            y,
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
            skip_source_index=skip,
        )

    def text_size(self, text: str, font: Font = SMALL) -> tuple:
        return font.text_width(text), font.height

    def text(
        self, text: str, x: int, y: int, *, font: Font = SMALL, color=5, shadow=None
    ) -> int:
        # Returns the pixel width drawn. shadow is a palette slot for a 1px drop shadow.
        px = x
        for ch in text:
            glyph = font.glyph(ch)
            gw = glyph[0]
            if isinstance(glyph[1], int):
                for w in range(gw):
                    inv_w = gw - w
                    for h in range(font.height):
                        if not (glyph[h + 1] >> inv_w) & 1:
                            continue

                        if shadow is not None:
                            self.pixel(px + w + 1, y + h + 1, shadow)

                        self.pixel(px + w, y + h, color)
            else:
                # Shaded glyphs store literal palette indices, not a bitmask — see docs/ARCHITECTURE.md.
                for w in range(gw):
                    for h in range(font.height):
                        self.pixel(px + w, y + h, int(glyph[h + 1][w]))

            px += gw

        return px - x


class Display:
    def __init__(self, settings):
        self.settings = settings
        board_profile = detect_board(os.uname().machine)
        self._matrix = RGBMatrix(
            width=settings["width"],
            height=settings["height"],
            bit_depth=board_profile.bit_depth,
            rgb_pins=board_profile.resolve_rgb_pins(
                settings["height"], settings.get("color_correct")
            ),
            addr_pins=board_profile.resolve_addr_pins(settings["height"]),
            clock_pin=board_profile.clock_pin,
            latch_pin=board_profile.latch_pin,
            output_enable_pin=board_profile.output_enable_pin,
            tile=settings["tiles"],
            serpentine=False,
            doublebuffer=True,
        )
        try:
            microcontroller.cpu.frequency = 180_000_000
        except RuntimeError:
            pass

        self._hw = framebufferio.FramebufferDisplay(
            self._matrix, auto_refresh=False, rotation=settings["rotation"]
        )
        self.width = self._hw.width
        self.height = self._hw.height

        # Flush stale panel data before building real content — see docs/ARCHITECTURE.md.
        self._hw.root_group = displayio.Group()
        self._hw.refresh()

        self._value_count = 20  # see docs/ARCHITECTURE.md
        palette = displayio.Palette(self._value_count, dither=False)
        for slot, rgb in enumerate(Color.SYSTEM_PALETTE):
            palette[slot] = rgb

        self.palette = palette
        self.palette_allocator = PaletteAllocator(
            palette, size=len(palette), reserved=len(Color.SYSTEM_PALETTE)
        )

        bitmap = displayio.Bitmap(self.width, self.height, self._value_count)
        self._group = displayio.Group()
        self._group.append(displayio.TileGrid(bitmap, pixel_shader=palette))
        self._hw.root_group = self._group

        self.canvas = Canvas(bitmap, palette)

        # Pins/tile count are only ever read at RGBMatrix construction time
        # above, so a change to any of these needs a fresh boot to take
        # effect — apply_settings() compares against this snapshot rather
        # than the live hardware object, which doesn't expose tiles/color
        # correction for comparison — see docs/ARCHITECTURE.md.
        self._boot_geometry = (
            int(settings["width"]),
            int(settings["height"]),
            int(settings["tiles"]),
            bool(settings.get("color_correct")),
        )
        self.reboot_pending = False

    def refresh(self):
        self._hw.refresh()

    def set_visible(self, visible: bool):
        self._hw.root_group.hidden = not visible

    def set_root_group(self, group):
        self._hw.root_group = group  # restore_root_canvas() reverts this on app exit

    def restore_root_canvas(self):
        self._hw.root_group = self._group

    def new_canvas(self, width=None, height=None, palette=None) -> Canvas:
        bitmap = displayio.Bitmap(
            width or self.width, height or self.height, self._value_count
        )

        return Canvas(bitmap, palette or self.palette)

    def apply_settings(self):
        rotation = int(self.settings["rotation"])
        if self._hw.rotation != rotation:
            self._hw.rotation = rotation

        geometry = (
            int(self.settings["width"]),
            int(self.settings["height"]),
            int(self.settings["tiles"]),
            bool(self.settings.get("color_correct")),
        )
        if geometry != self._boot_geometry:
            # Not an immediate reset() — this runs inside the settings POST
            # handler, before settings.save()'s write is necessarily flushed
            # to flash and before the HTTP response is sent. main()'s loop
            # resets once both have safely happened — see docs/ARCHITECTURE.md.
            self.reboot_pending = True


display = Display(_settings)
