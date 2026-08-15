import board


class BoardProfile:
    def __init__(
        self,
        name,
        *,
        bit_depth,
        rgb_pins,
        addr_pins,
        addr_pin_64,
        clock_pin,
        latch_pin,
        output_enable_pin,
    ):
        self.name = name
        self.bit_depth = bit_depth
        self._rgb_pins = rgb_pins
        self._addr_pins = addr_pins
        self._addr_pin_64 = addr_pin_64
        self.clock_pin = clock_pin
        self.latch_pin = latch_pin
        self.output_enable_pin = output_enable_pin

    def resolve_addr_pins(self, height):
        pins = list(self._addr_pins)
        if height == 64 and self._addr_pin_64 is not None:
            pins.append(self._addr_pin_64)

        return pins

    def resolve_rgb_pins(self, height, color_correct=False):
        pins = (
            self._rgb_pins(height) if callable(self._rgb_pins) else list(self._rgb_pins)
        )
        if color_correct:
            pins = [pins[0], pins[2], pins[1], pins[3], pins[5], pins[4]]

        return pins


def _waveshare_rgb_pins(height):
    if height == 64:
        return [board.IO1, board.IO2, board.IO3, board.IO4, board.IO5, board.IO6]

    return [board.IO1, board.IO3, board.IO2, board.IO4, board.IO6, board.IO5]


def _waveshare_s3_zero():
    return BoardProfile(
        "Waveshare ESP32-S3-Zero",
        bit_depth=4,
        rgb_pins=_waveshare_rgb_pins,
        addr_pins=[board.IO7, board.IO8, board.IO9, board.IO10],
        addr_pin_64=board.IO17,
        clock_pin=board.IO11,
        latch_pin=board.IO12,
        output_enable_pin=board.IO13,
    )


def _n8r8():
    return BoardProfile(
        "N8R8",
        bit_depth=4,
        rgb_pins=[
            board.GPIO1,
            board.GPIO2,
            board.GPIO42,
            board.GPIO41,
            board.GPIO40,
            board.GPIO39,
        ],
        addr_pins=[board.GPIO3, board.GPIO8, board.GPIO18, board.GPIO17],
        addr_pin_64=board.GPIO21,
        clock_pin=board.GPIO12,
        latch_pin=board.GPIO13,
        output_enable_pin=board.GPIO14,
    )


def _esp32_s2_fk8f1():
    return BoardProfile(
        "ESP32-S2 (FK-8F1)",
        bit_depth=4,
        rgb_pins=[
            board.IO12,
            board.IO13,
            board.IO17,
            board.IO21,
            board.IO20,
            board.IO16,
        ],
        addr_pins=[board.IO38, board.IO37, board.IO36, board.IO35],
        addr_pin_64=board.IO34,
        clock_pin=board.IO10,
        latch_pin=board.IO33,
        output_enable_pin=board.IO11,
    )


# (match, factory) — match never touches board.*, so checking it is safe
# on any board; only the winning factory is ever called.
_BOARDS = (
    (
        lambda machine: machine == "Waveshare ESP32-S3-Zero with ESP32S3",
        _waveshare_s3_zero,
    ),
    (lambda machine: "N8R8" in machine, _n8r8),
    (lambda machine: "ESP32-S2" in machine, _esp32_s2_fk8f1),
)


def detect_board(machine: str) -> BoardProfile:
    for match, factory in _BOARDS:
        if match(machine):
            return factory()

    raise RuntimeError(f"no board profile for machine: {machine!r}")
