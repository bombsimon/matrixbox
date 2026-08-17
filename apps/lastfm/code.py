import gc
import time

from matrixbox.app import App
from matrixbox.color import hex_to_rgb
from matrixbox.display import display
from matrixbox.fonts import LARGE
from matrixbox.layout import Align, align_x
from matrixbox.net import http
from matrixbox.text import ScrollingLine, Span

POLL_INTERVAL = 5  # seconds between now-playing checks
HOLD_START = 1.2  # seconds frozen at the start of a scroll cycle
HOLD_END = 1.2  # seconds frozen at the end
TOP_MARGIN = 2  # px above the top line in double layout (capped at freed space)
LINE_GAP = 0  # px between the two lines in double layout

LAYOUT_SINGLE = "single"  # one scrolling line: "artist - track"
LAYOUT_DOUBLE = "double"  # two lines: artist / track

API_URL = (
    "https://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks"
    "&user={user}&api_key={key}&format=json&limit=1"
)

DISP_W = display.width
DISP_H = display.height


class LastFmApp(App):
    title = "Last.fm"
    default_settings = {
        "username": "",
        "api_key": "",
        "artist_color": "#ffffff",
        "song_color": "#ffffff",
        "dash_color": "#ffffff",
        "shadow_color": "#380000",
        "layout": LAYOUT_SINGLE,
        "align": "center",  # "center" or "left" (applies to non-scrolling lines)
        "idle_timeout": 10,  # minutes of no music before auto-exit; 0 = never
    }

    def needs_network(self) -> bool:
        return True

    def on_start(self):
        with open("template.html") as f:
            self.html_body = f.read()

        # Palette slots re-allocated fresh every launch — see docs/ARCHITECTURE.md.
        self.artist_slot = display.palette_allocator.allocate()
        self.song_slot = display.palette_allocator.allocate()
        self.dash_slot = display.palette_allocator.allocate()
        self.shadow_slot = display.palette_allocator.allocate()
        self._apply_colors()

        self.lines = []
        self._build_lines("Last.fm", "loading")
        self._render()

        self.last_track = ("Last.fm", "loading")
        self.last_active = (
            time.monotonic()
        )  # last time a song was playing; drives auto-exit
        self.last_poll = time.monotonic()
        if self._poll():  # fetch real data immediately instead of waiting a cycle
            self._render()

    def render(self) -> str:
        return self.html_body

    def on_settings_saved(self, values):
        self._apply_colors()
        self._build_lines(*self.last_track)
        self._render()

    def on_update(self, now):
        redraw = False

        scrolling = False
        for line, _y in self.lines:
            if line.update(now):
                redraw = True

            scrolling = scrolling or line.scrolling

        # Fetching mid-scroll would stutter the animation, so only poll
        # while everything is holding still (at the start or end of a cycle).
        if not scrolling and now - self.last_poll >= POLL_INTERVAL and self._poll():
            redraw = True

        timeout = self.config["idle_timeout"] * 60
        if timeout > 0 and now - self.last_active >= timeout:
            self.request_exit()  # the kernel clears the screen and redraws the selector

        if redraw:
            self._render()

        self.tick_seconds = 0.03 if scrolling else 0.1

    def _apply_colors(self):
        display.palette_allocator.set(
            self.artist_slot, hex_to_rgb(self.config["artist_color"])
        )
        display.palette_allocator.set(
            self.song_slot, hex_to_rgb(self.config["song_color"])
        )
        display.palette_allocator.set(
            self.dash_slot, hex_to_rgb(self.config["dash_color"])
        )
        display.palette_allocator.set(
            self.shadow_slot, hex_to_rgb(self.config["shadow_color"])
        )

    def _fetch_now_playing(self) -> tuple:
        if not self.config["username"] or not self.config["api_key"]:
            return ("Last.fm", "set user & key", False)

        url = API_URL.format(user=self.config["username"], key=self.config["api_key"])
        r = http.get(url)

        try:
            tracks = r.json()["recenttracks"]["track"]
        finally:
            r.close()
            gc.collect()

        if not tracks:
            return ("Last.fm", "no tracks", False)

        # tracks[0] carries @attr.nowplaying only while something is actually
        # playing; otherwise it's the latest scrobble, which we don't show.
        track = tracks[0] if isinstance(tracks, list) else tracks
        if (track.get("@attr") or {}).get("nowplaying") != "true":
            return ("Last.fm", "nothing playing", False)

        return (track["artist"]["#text"], track["name"], True)

    def _build_lines(self, artist: str, song: str):
        shadow = self.shadow_slot
        if self.config["layout"] == LAYOUT_DOUBLE:
            artist_line = ScrollingLine(
                Span(artist, font=LARGE, color=self.artist_slot, shadow=shadow),
                viewport_w=DISP_W,
                hold_start=HOLD_START,
                hold_end=HOLD_END,
            )
            song_line = ScrollingLine(
                Span(song, font=LARGE, color=self.song_slot, shadow=shadow),
                viewport_w=DISP_W,
                hold_start=HOLD_START,
                hold_end=HOLD_END,
            )
            block_h = artist_line.height + song_line.height + LINE_GAP
            top = min(TOP_MARGIN, max(DISP_H - block_h, 0))
            self.lines = [
                (artist_line, top),
                (song_line, top + artist_line.height + LINE_GAP),
            ]
        else:
            combined = ScrollingLine(
                Span(artist, font=LARGE, color=self.artist_slot, shadow=shadow),
                Span(" - ", font=LARGE, color=self.dash_slot, shadow=shadow),
                Span(song, font=LARGE, color=self.song_slot, shadow=shadow),
                viewport_w=DISP_W,
                hold_start=HOLD_START,
                hold_end=HOLD_END,
            )
            self.lines = [(combined, max((DISP_H - combined.height) // 2, 0))]

        gc.collect()

    def _render(self):
        display.canvas.fill(0)
        align = Align.LEFT if self.config["align"] == "left" else Align.CENTER
        for line, y in self.lines:
            x = 0 if line.scroller else align_x(line.width, DISP_W, align)
            line.draw(display.canvas, x, y)

        display.refresh()

    def _poll(self) -> bool:
        # Returns True if the track changed and the display needs a redraw.
        self.last_poll = time.monotonic()
        changed = False

        try:
            artist, song, playing = self._fetch_now_playing()
            if playing:
                self.last_active = self.last_poll

            track = (artist, song)
            if track != self.last_track:
                self.last_track = track
                self._build_lines(artist, song)
                changed = True
        except Exception as e:
            print("lastfm fetch error:", e)
        finally:
            gc.collect()

        return changed


LastFmApp().run()
