from matrixbox.fonts import MINI, Font


class Align:
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    TOP = "top"
    MIDDLE = "middle"
    BOTTOM = "bottom"


def align_x(content_w: int, box_w: int, align: str = Align.CENTER) -> int:
    if align == Align.LEFT:
        return 0

    if align == Align.RIGHT:
        return max(box_w - content_w, 0)

    return max((box_w - content_w) // 2, 0)


def align_y(content_h: int, box_h: int, align: str = Align.MIDDLE) -> int:
    if align == Align.TOP:
        return 0

    if align == Align.BOTTOM:
        return max(box_h - content_h, 0)

    return max((box_h - content_h) // 2, 0)


def fit_scale(
    content_w: int, content_h: int, box_w: int, box_h: int, max_scale: int = 8
) -> int:
    scale = max_scale
    while scale > 1 and (content_w * scale > box_w or content_h * scale > box_h):
        scale -= 1

    return max(scale, 1)


class TextGrid:
    def __init__(self, canvas, font: Font = MINI, row_height: int = None):
        self.canvas = canvas
        self.font = font
        self.row_height = row_height or (font.height + 1)

    def row_y(self, row: int) -> int:
        # Negative row counts back from the last row that fits, Python-index style.
        if row < 0:
            row += self.canvas.height // self.row_height

        return row * self.row_height

    def line(
        self,
        text: str,
        row: int,
        *,
        color=5,
        align: str = Align.LEFT,
        clear: bool = True,
    ) -> int:
        y = self.row_y(row)
        w, _ = self.canvas.text_size(text, self.font)
        if clear:
            self.canvas.fill_rect(0, y, self.canvas.width, self.row_height, 0)

        x = align_x(w, self.canvas.width, align)
        self.canvas.text(text, x, y, font=self.font, color=color)

        return w
