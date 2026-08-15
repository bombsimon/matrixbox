import time

import board
import digitalio

NONE = 0
SHORT_PRESS = 1
LONG_PRESS = 2


class Button:
    # Debounce logic: see docs/architecture.md.
    def __init__(
        self,
        pin,
        *,
        pull=digitalio.Pull.UP,
        active_low=True,
        long_press_seconds=2.0,
        debounce_seconds=0.1,
    ):
        self._io = digitalio.DigitalInOut(pin)
        self._io.direction = digitalio.Direction.INPUT
        self._io.pull = pull
        self._active_low = active_low
        self.long_press_seconds = long_press_seconds
        self.debounce_seconds = debounce_seconds

        self._stable_pressed = False
        self._raw_pressed = self.pressed
        self._last_change = time.monotonic()
        self._pressed_at = 0.0
        self._long_fired = False

    @property
    def pressed(self) -> bool:
        return (not self._io.value) if self._active_low else self._io.value

    def poll(self) -> int:
        # Call once per loop iteration; returns NONE / SHORT_PRESS / LONG_PRESS.
        now = time.monotonic()
        raw = self.pressed
        short_press = False

        if raw != self._raw_pressed:
            self._raw_pressed = raw
            self._last_change = now
        elif now - self._last_change >= self.debounce_seconds:
            # Raw has been stable long enough to trust as a real transition.
            if raw and not self._stable_pressed:
                self._stable_pressed = True
                self._pressed_at = now
                self._long_fired = False
            elif not raw and self._stable_pressed:
                self._stable_pressed = False
                short_press = not self._long_fired

        # Checked every poll, independent of the stability gate above — a
        # bouncy signal must never delay noticing that long_press_seconds
        # has genuinely elapsed since the press was confirmed, or elapsed
        # wall-clock time silently piles up until the bounce happens to
        # settle, at which point it fires immediately (see docs/architecture.md).
        if (
            self._stable_pressed
            and not self._long_fired
            and now - self._pressed_at >= self.long_press_seconds
        ):
            self._long_fired = True

            return LONG_PRESS

        return SHORT_PRESS if short_press else NONE


# TX companion pin: see docs/architecture.md. RX polarity is the standard
# pull-up default (idle high, pressed low) — confirmed via /console on
# 2026-08-17 with a clean, unambiguous trace (see docs/architecture.md);
# an earlier measurement, taken before matrixbox.display was fixed to
# import before matrixbox.button, found the opposite and is now stale.
_tx_companion = digitalio.DigitalInOut(board.TX)
_tx_companion.direction = digitalio.Direction.INPUT
_tx_companion.pull = digitalio.Pull.DOWN

button = Button(board.RX, pull=digitalio.Pull.UP)
