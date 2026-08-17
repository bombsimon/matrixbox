import gc
import json
import time

from matrixbox.app import App
from matrixbox.display import display
from matrixbox.fonts import SMALL, font_by_name
from matrixbox.net import http
from matrixbox.scroll import Direction, Scroller

DISP_W = display.width
DISP_H = display.height

MODES = ("scroll", "list", "graph")
GRAPH_PARAMS = {"1d": ("1d", "5m"), "5d": ("5d", "15m"), "1mo": ("1mo", "1d")}
SPEED_TICK = {1: 0.06, 2: 0.03, 3: 0.015}

API_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?range={range}&interval={interval}"
)
HEADERS = {"User-Agent": "MatrixBox"}

_ARROW_UP = ((2, 0), (1, 1), (2, 1), (3, 1), (2, 2), (2, 3), (2, 4))
_ARROW_DOWN = ((2, 0), (2, 1), (2, 2), (1, 3), (2, 3), (3, 3), (2, 4))


def _draw_arrow(canvas, x, y, color, up):
    for dx, dy in _ARROW_UP if up else _ARROW_DOWN:
        canvas.pixel(x + dx, y + dy, color)


def _quote_text(symbol, price, change):
    text = str(price)
    if "." in text:
        whole, dec = text.split(".", 1)
        text = f"{whole}.{dec[:2]}"

    sign = "+" if change >= 0 else ""

    return symbol.upper(), text, f"{sign}{change:.1f}%", change >= 0


class StocksApp(App):
    title = "Stocks"
    default_settings = {
        "symbols": "AAPL,MSFT,GOOG,AMZN,TSLA",
        "speed": 2,
        "interval": 60,
        "mode": "scroll",
        "graph_range": "1d",
        "font": "small",
        "graph_dwell": 8,
    }

    def needs_network(self) -> bool:
        return True

    def on_start(self):
        with open("template.html") as f:
            self.html_body = f.read()

        self.up_slot = display.palette_allocator.allocate((0, 180, 0))
        self.down_slot = display.palette_allocator.allocate((200, 0, 0))
        self.text_slot = display.palette_allocator.allocate((160, 160, 160))
        self.dim_slot = display.palette_allocator.allocate((60, 60, 60))

        @self.router.route("/quotes")
        def get_quotes(request):
            return (200, {}, json.dumps(self.quotes))

        self.quotes = []
        self.scroller = None
        self.symbol_index = 0
        self.graph_symbol = None
        self.graph_closes = []
        self.graph_advance_at = time.monotonic()

        self._fetch_quotes()
        self._rebuild()
        self.last_fetch = time.monotonic()

    def render(self) -> str:
        return self.html_body

    def on_button(self):
        current = self.config["mode"] if self.config["mode"] in MODES else "scroll"
        self.config["mode"] = MODES[(MODES.index(current) + 1) % len(MODES)]
        self._rebuild()

    def on_settings_saved(self, values):
        if "symbols" in values:
            self._fetch_quotes()

        if "graph_range" in values:
            self.graph_symbol = None  # force a refetch on the next graph build

        if any(key in values for key in ("symbols", "font", "mode", "graph_range")):
            self._rebuild()

    def on_update(self, now):
        mode = self.config["mode"]

        if mode == "graph":
            self.tick_seconds = 0.1
            if now - self.graph_advance_at >= self.config["graph_dwell"]:
                self.symbol_index += 1
                self.graph_symbol = None
                self._build_graph()
        else:
            self.tick_seconds = SPEED_TICK.get(self.config["speed"], 0.03)
            if self.scroller and self.scroller.update(now):
                self._draw_scroll_frame()

        if now - self.last_fetch > self.config["interval"]:
            self._fetch_quotes()
            if mode != "graph":
                self._rebuild()

            self.last_fetch = now
            gc.collect()

    # -- fetching --

    def _symbol_list(self):
        return [
            s.strip()
            for s in self.config["symbols"].replace(" ", "").split(",")
            if s.strip()
        ]

    def _fetch_quotes(self):
        quotes = []
        for symbol in self._symbol_list():
            quote = self._fetch_one(symbol)
            if quote is not None:
                quotes.append((symbol, quote[0], quote[1]))

            gc.collect()

        self.quotes = quotes

    def _fetch_one(self, symbol):
        try:
            url = API_URL.format(symbol=symbol, range="1d", interval="1d")
            r = http.get(url, headers=HEADERS)
            data = r.json()
            r.close()
            meta = data["chart"]["result"][0]["meta"]
            price = meta["regularMarketPrice"]
            previous = meta["chartPreviousClose"]
            change = ((price - previous) / previous) * 100 if previous else 0

            return (price, change)
        except Exception as e:
            print(f"stocks: fetch error for {symbol}: {e}")

            return None

    def _fetch_history(self, symbol):
        rng, interval = GRAPH_PARAMS.get(self.config["graph_range"], ("1d", "5m"))
        try:
            url = API_URL.format(symbol=symbol, range=rng, interval=interval)
            r = http.get(url, headers=HEADERS)
            data = r.json()
            r.close()
            closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]

            return [c for c in closes if c is not None]
        except Exception as e:
            print(f"stocks: history error for {symbol}: {e}")

            return []

    # -- rendering --

    def _rebuild(self):
        mode = self.config["mode"]
        if mode == "list":
            self._build_list()
        elif mode == "graph":
            self._build_graph()
        else:
            self._build_ticker()

    def _show_message(self, text):
        display.canvas.fill(0)
        display.canvas.text(text, 0, 0, font=SMALL, color=self.text_slot)
        display.refresh()

    def _draw_scroll_frame(self):
        display.canvas.fill(0)
        if self.scroller:
            self.scroller.draw(display.canvas, 0, 0)

        display.refresh()

    def _build_ticker(self):
        if not self.quotes:
            self.scroller = None
            self._show_message("no data")
            return

        font = font_by_name(self.config["font"])
        gap, arrow_w = 8, 6
        parts = [_quote_text(*q) for q in self.quotes]
        content_w = sum(
            font.text_width(f"{sym} {price} ") + arrow_w + font.text_width(pct) + gap
            for sym, price, pct, up in parts
        )

        canvas = display.new_canvas(DISP_W + content_w + DISP_W, DISP_H)
        y = max(0, (DISP_H - font.height) // 2)
        x = DISP_W
        for sym, price, pct, up in parts:
            color = self.up_slot if up else self.down_slot
            x += canvas.text(f"{sym} ", x, y, font=font, color=self.text_slot)
            x += canvas.text(f"{price} ", x, y, font=font, color=color)
            _draw_arrow(canvas, x, y, color, up)
            x += arrow_w
            x += canvas.text(pct, x, y, font=font, color=color)
            x += gap

        self.scroller = Scroller(
            canvas, DISP_W, DISP_H, direction=Direction.LEFT, speed=1
        )
        self._draw_scroll_frame()

    def _build_list(self):
        if not self.quotes:
            self.scroller = None
            self._show_message("no data")
            return

        font = font_by_name(self.config["font"])
        arrow_w = 6
        row_h = font.height + 1
        parts = [_quote_text(*q) for q in self.quotes]

        canvas = display.new_canvas(DISP_W, max(len(parts) * row_h, DISP_H))
        for i, (sym, price, pct, up) in enumerate(parts):
            y = i * row_h
            color = self.up_slot if up else self.down_slot
            x = 1 + canvas.text(sym, 1, y, font=font, color=self.text_slot)
            canvas.text(f" {price}", x, y, font=font, color=color)
            arrow_x = DISP_W - font.text_width(pct) - arrow_w - 1
            _draw_arrow(canvas, arrow_x, y, color, up)
            canvas.text(pct, arrow_x + arrow_w, y, font=font, color=color)

        self.scroller = Scroller(
            canvas, DISP_W, DISP_H, direction=Direction.UP, speed=1
        )
        self._draw_scroll_frame()

    def _build_graph(self):
        symbols = self._symbol_list()
        if not symbols:
            self.scroller = None
            self._show_message("no symbols")
            return

        self.scroller = None
        self.symbol_index %= len(symbols)
        symbol = symbols[self.symbol_index]
        if symbol != self.graph_symbol:
            self.graph_closes = self._fetch_history(symbol)
            self.graph_symbol = symbol

        self.graph_advance_at = time.monotonic()

        display.canvas.fill(0)
        closes = self.graph_closes
        label_h = SMALL.height + 1
        chart_y0 = label_h
        chart_h = DISP_H - label_h

        if len(closes) < 2:
            display.canvas.text(
                f"{symbol} no data", 1, 0, font=SMALL, color=self.text_slot
            )
        else:
            low, high = min(closes), max(closes)
            if high == low:
                high = low + 0.001

            up = closes[-1] >= closes[0]
            color = self.up_slot if up else self.down_slot
            change = ((closes[-1] - closes[0]) / closes[0]) * 100 if closes[0] else 0
            sign = "+" if change >= 0 else ""
            label = f"{symbol} {sign}{change:.1f}% {self.config['graph_range']}"
            display.canvas.text(label, 1, 0, font=SMALL, color=color)

            def y_for(price):
                return chart_y0 + int((high - price) / (high - low) * (chart_h - 1))

            baseline_y = y_for(closes[0])
            if chart_y0 <= baseline_y < DISP_H:
                for x in range(DISP_W):
                    if display.canvas.get_pixel(x, baseline_y) == 0:
                        display.canvas.pixel(x, baseline_y, self.dim_slot)

            n = len(closes)
            prev_y = None
            for x in range(DISP_W):
                y = y_for(closes[x * (n - 1) // max(DISP_W - 1, 1)])
                if prev_y is not None:
                    display.canvas.line(x, prev_y, x, y, color)
                else:
                    display.canvas.pixel(x, y, color)

                prev_y = y

        display.refresh()


StocksApp().run()
