class Color:
    BLACK = (0, 0, 0)
    WHITE = (140, 140, 140)
    BRIGHT_WHITE = (255, 255, 255)
    RED = (140, 0, 0)
    GREEN = (0, 140, 20)
    BLUE = (0, 60, 140)
    YELLOW = (140, 140, 0)
    CYAN = (0, 140, 140)
    MAGENTA = (140, 0, 140)
    ORANGE = (140, 80, 0)
    PINK = (140, 0, 60)
    GREY = (60, 60, 60)

    # Fixed order for palette slots 0-7 — see Display.__init__.
    SYSTEM_PALETTE = (BLACK, YELLOW, BRIGHT_WHITE, BLUE, RED, WHITE, GREEN, GREY)


def hex_to_rgb(value: str) -> tuple:
    value = value.lstrip("#")
    if len(value) != 6:
        return Color.WHITE

    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return Color.WHITE


def rgb_to_hex(rgb: tuple) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


class PaletteAllocator:
    # Always re-allocate, never hardcode a slot number — see docs/architecture.md.
    def __init__(self, palette, size, reserved=8):
        self._palette = palette
        self._size = size
        self.reserved = reserved
        self._next = reserved

    def allocate(self, rgb=Color.BLACK) -> int:
        if self._next >= self._size:
            raise RuntimeError("palette exhausted")

        slot = self._next
        self._next += 1
        self._palette[slot] = rgb

        return slot

    def set(self, slot, rgb):
        self._palette[slot] = rgb

    def reset(self):
        self._next = self.reserved
