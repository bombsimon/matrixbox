from matrixbox.display import display
from matrixbox.fonts import SMALL, Font
from matrixbox.scroll import Direction, Scroller


class Span:
    def __init__(self, text: str, *, font: Font = SMALL, color=5, shadow=None):
        self.text = text
        self.font = font
        self.color = color
        self.shadow = shadow

    @property
    def width(self) -> int:
        return max(self.font.text_width(self.text), 1)


def compose(*spans: Span, height: int = None):
    # Renders spans side by side into one Canvas; returns (canvas, width).
    has_shadow = any(s.shadow is not None for s in spans)
    height = height or max(s.font.height for s in spans) + (1 if has_shadow else 0)
    widths = [s.width for s in spans]
    canvas = display.new_canvas(sum(widths) + 2, height)

    x = 1
    for span, width in zip(spans, widths):
        canvas.text(
            span.text, x, 0, font=span.font, color=span.color, shadow=span.shadow
        )
        x += width

    return canvas, sum(widths) + 2


class ScrollingLine:
    MARGIN = 4  # blank px kept before/after the text once it scrolls

    def __init__(
        self,
        *spans: Span,
        viewport_w: int,
        height: int = None,
        direction: str = Direction.LEFT,
        speed: int = 1,
        hold_start: float = 0.0,
        hold_end: float = 0.0,
    ):
        canvas, width = compose(*spans, height=height)
        self.width = width
        self.height = canvas.height
        self.scroller = None

        if width > viewport_w:
            padded = display.new_canvas(width + 2 * self.MARGIN, canvas.height)
            padded.blit(canvas, self.MARGIN, 0)
            canvas = padded
            self.scroller = Scroller(
                canvas,
                viewport_w,
                canvas.height,
                direction=direction,
                speed=speed,
                hold_start=hold_start,
                hold_end=hold_end,
            )

        self.canvas = canvas

    @property
    def scrolling(self) -> bool:
        return bool(self.scroller and self.scroller.phase == "scroll")

    def update(self, now: float = None) -> bool:
        return self.scroller.update(now) if self.scroller else False

    def draw(self, target, x: int, y: int):
        if self.scroller:
            self.scroller.draw(target, x, y)
        else:
            target.blit(self.canvas, x, y)
