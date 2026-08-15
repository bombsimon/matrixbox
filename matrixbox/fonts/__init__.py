from matrixbox.fonts.large import font_large as _LARGE_DATA
from matrixbox.fonts.mini import font_mini as _MINI_DATA
from matrixbox.fonts.small import font_small as _SMALL_DATA


class Font:
    def __init__(self, name, data, lowercase_only=False):
        self.name = name
        self.data = data
        self.height = data["fontheight"]
        self.lowercase_only = lowercase_only

    def glyph(self, char):
        if self.lowercase_only:
            char = char.lower()

        return self.data.get(char) or self.data["_"]

    def text_width(self, text: str) -> int:
        if self.lowercase_only:
            text = text.lower()

        return sum(self.data[c][0] for c in text if c in self.data)


MINI = Font("mini", _MINI_DATA, lowercase_only=True)
SMALL = Font("small", _SMALL_DATA)
LARGE = Font("large", _LARGE_DATA)

BY_NAME = {"mini": MINI, "small": SMALL, "large": LARGE}


def font_by_name(name: str, default: Font = SMALL) -> Font:
    return BY_NAME.get(name, default)
