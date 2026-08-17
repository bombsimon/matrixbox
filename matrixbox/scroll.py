import time

from matrixbox.display import Canvas, display


class Direction:
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"


_HORIZONTAL = (Direction.LEFT, Direction.RIGHT)


class Scroller:
    def __init__(
        self,
        content: Canvas,
        viewport_w: int,
        viewport_h: int,
        *,
        direction: str = Direction.LEFT,
        speed: int = 1,
        hold_start: float = 0.0,
        hold_end: float = 0.0,
    ):
        self.content = content
        self.viewport_w = viewport_w
        self.viewport_h = viewport_h
        self.direction = direction
        self.speed = speed
        self.hold_start = hold_start
        self.hold_end = hold_end

        axis_size = content.width if direction in _HORIZONTAL else content.height
        viewport_size = viewport_w if direction in _HORIZONTAL else viewport_h
        self.max_offset = max(axis_size - viewport_size, 0)
        self.needs_scroll = self.max_offset > 0

        self.offset = 0
        self.phase = "start"
        self._phase_until = time.monotonic() + hold_start

    @classmethod
    def transition(
        cls,
        old: Canvas,
        new: Canvas,
        viewport_w: int,
        viewport_h: int,
        *,
        direction: str = Direction.LEFT,
        speed: int = 1,
    ) -> "Scroller":
        # One-shot old->new slide, never resets back — see docs/ARCHITECTURE.md.
        if direction in _HORIZONTAL:
            strip = display.new_canvas(
                old.width + new.width, max(old.height, new.height)
            )
            strip.blit(old, 0, 0)
            strip.blit(new, old.width, 0)
        else:
            strip = display.new_canvas(
                max(old.width, new.width), old.height + new.height
            )
            strip.blit(old, 0, 0)
            strip.blit(new, 0, old.height)

        return cls(
            strip,
            viewport_w,
            viewport_h,
            direction=direction,
            speed=speed,
            hold_end=60.0,  # long enough the caller's loop has stopped by then
        )

    def reset(self):
        self.offset = 0
        self.phase = "start"
        self._phase_until = time.monotonic() + self.hold_start

    @property
    def finished(self) -> bool:
        # See docs/ARCHITECTURE.md — not a useful loop-exit check on a looping Scroller.
        return self.phase == "end"

    def run_to_completion(self, draw):
        # Blocks; for a one-shot transition() only — a looping Scroller never finishes.
        while not self.finished:
            if self.update():
                draw()

    def update(self, now: float = None) -> bool:
        if not self.needs_scroll:
            return False

        now = time.monotonic() if now is None else now

        if self.phase == "start":
            if now >= self._phase_until:
                self.phase = "scroll"

            return False

        if self.phase == "scroll":
            self.offset = min(self.offset + self.speed, self.max_offset)
            if self.offset >= self.max_offset:
                self.phase = "end"
                self._phase_until = now + self.hold_end

            return True

        if self.phase == "end":
            if now >= self._phase_until:
                self.offset = 0
                self.phase = "start"
                self._phase_until = now + self.hold_start
                return True

            return False

        return False

    def draw(self, target: Canvas, x: int, y: int):
        if self.direction == Direction.LEFT:
            x1, y1 = self.offset, 0
        elif self.direction == Direction.RIGHT:
            x1, y1 = self.max_offset - self.offset, 0
        elif self.direction == Direction.UP:
            x1, y1 = 0, self.offset
        else:  # DOWN
            x1, y1 = 0, self.max_offset - self.offset

        x2 = (
            x1 + self.viewport_w
            if self.direction in _HORIZONTAL
            else self.content.width
        )
        y2 = (
            y1 + self.viewport_h
            if self.direction not in _HORIZONTAL
            else self.content.height
        )
        target.blit(self.content, x, y, x1=x1, y1=y1, x2=x2, y2=y2)
