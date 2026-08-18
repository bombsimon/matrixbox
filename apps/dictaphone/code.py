from matrixbox.app import App
from matrixbox.display import display
from matrixbox.fonts import font_by_name
from matrixbox.layout import TextGrid
from matrixbox.web import url_decode


class DictaphoneApp(App):
    title = "Dictaphone"

    def on_start(self):
        with open("template.html") as f:
            self.html_body = f.read()

        self.font = font_by_name("mini")
        self.grid = TextGrid(display.canvas, font=self.font)
        self.white_slot = display.palette_allocator.allocate((200, 200, 200))
        self.grey_slot = display.palette_allocator.allocate((100, 100, 100))
        self.max_lines = display.height // self.font.height
        self.lines = []  # [(text, color_slot), ...]
        self.sentence_count = 0

        display.canvas.fill(0)
        self.grid.line("dictaphone", 0, color=self.white_slot, clear=False)
        self.grid.line("open web ui", 1, color=self.white_slot, clear=False)
        self.grid.line("to start", 2, color=self.white_slot, clear=False)
        display.refresh()

        @self.router.route("/text")
        def _text_route(request):
            if "t" in request.params:
                self._add_text(url_decode(request.params["t"]))

            return (200, {}, "ok")

        @self.router.route("/clear")
        def _clear_route(request):
            self.lines = []
            self.sentence_count = 0
            self._show_lines()

            return (200, {}, "ok")

    def render(self) -> str:
        return self.html_body

    def on_button(self):
        # Matches the old app: any press exits, not just a long one.
        self.request_exit()

    def _wrap_text(self, text, max_w):
        result = []
        words = text.split(" ")
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            if self.font.text_width(test) <= max_w:
                current = test
                continue

            if current:
                result.append(current)

            current = word
            while self.font.text_width(current) > max_w and len(current) > 1:
                current = current[:-1]

        if current:
            result.append(current)

        return result

    def _add_text(self, text):
        text = text.strip()
        if text and text[-1] not in ".!?":
            text += "."

        slot = self.white_slot if self.sentence_count % 2 == 0 else self.grey_slot
        self.sentence_count += 1
        for wrapped in self._wrap_text(text, display.width - 2):
            self.lines.append((wrapped, slot))

        while len(self.lines) > self.max_lines:
            self.lines.pop(0)

        self._show_lines()

    def _show_lines(self):
        for row in range(self.max_lines):
            if row < len(self.lines):
                text, slot = self.lines[row]
            else:
                text, slot = "", self.white_slot

            self.grid.line(text, row, color=slot)

        display.refresh()


DictaphoneApp().run()
