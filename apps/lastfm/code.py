import gc
import sys
import time

import bitmaptools
import displayio

from __main__ import (
    ampule,
    footer,
    header,
    json,
    load_settings,
    palette,
    requests,
    settings,
    socket,
    url_decoder,
)
from check_button import check_if_button_pressed
from load_screen import font_large, pprint, refresh, strlen, window

SETTINGS_FILE = "lastfm_settings.json"
POLL_INTERVAL = 5

SCROLL_GAP = 16  # px between marquee repeats
SCROLL_SPEED = 1  # px advanced per frame while scrolling
LINE_GAP = 2  # px between the two lines in double layout

LAYOUT_SINGLE = "single"  # one scrolling line: "artist - track"
LAYOUT_DOUBLE = "double"  # two lines: artist / track

API_URL = (
    "https://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks"
    "&user={user}&api_key={key}&format=json&limit=1"
)

DEFAULTS = {
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

# Palette slots reused for the text colors; __init__.py restores them on exit.
# apply_colors() sets their RGB; pprint takes the slot index directly as color.
ARTIST_SLOT = 5
SONG_SLOT = 7
DASH_SLOT = 8
SHADOW_SLOT = 9

DISP_W = settings["width"]
DISP_H = settings["height"]
FONT_H = font_large["fontheight"]
LINE_H = FONT_H + 1  # one extra row for the 1px drop shadow

with open("lastfm.html") as f:
    html_body = f.read()


def hex_to_rgb(value: str) -> tuple:
    value = value.lstrip("#")
    if len(value) != 6:
        return (255, 255, 255)

    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return (255, 255, 255)


def load_config() -> dict:
    config = dict(DEFAULTS)

    try:
        with open(SETTINGS_FILE) as f:
            config.update(json.loads(f.read()))
    except (OSError, ValueError):
        pass

    return config


def save_config(config: dict) -> bool:
    try:
        with open(SETTINGS_FILE, "w") as f:
            f.write(json.dumps(config))

        return True
    except OSError:
        return False


def apply_colors() -> None:
    palette[ARTIST_SLOT] = hex_to_rgb(config["artist_color"])
    palette[SONG_SLOT] = hex_to_rgb(config["song_color"])
    palette[DASH_SLOT] = hex_to_rgb(config["dash_color"])
    palette[SHADOW_SLOT] = hex_to_rgb(config["shadow_color"])


def fetch_now_playing() -> tuple:
    """Return (artist, song, playing). Only a live now-playing track is playing;
    every other state (unconfigured, no tracks, paused) reports playing=False so
    the idle timer keeps counting."""
    if not config["username"] or not config["api_key"]:
        return ("Last.fm", "set user & key", False)

    url = API_URL.format(user=config["username"], key=config["api_key"])
    r = requests.get(url)

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


def _text_bitmap(text: str, color: int):
    """Render text into a tight bitmap holding palette indices, return (bmp, w)."""
    w = max(strlen(text, font_large), 1) + 2
    bmp = displayio.Bitmap(w, LINE_H, 16)
    pprint(
        text,
        line=0,
        color=color,
        font=font_large,
        top_offset=-1,
        clear=False,
        _refresh=False,
        _clearscreen=False,
        window=bmp,
        block=True,
        shadow_color=SHADOW_SLOT,
    )

    return bmp, w


def _compose_single(artist: str, song: str):
    """One bitmap: artist, " - ", and track each in their own color."""
    a, aw = _text_bitmap(artist, ARTIST_SLOT)
    d, dw = _text_bitmap(" - ", DASH_SLOT)
    s, sw = _text_bitmap(song, SONG_SLOT)
    bmp = displayio.Bitmap(aw + dw + sw, LINE_H, 16)
    bitmaptools.blit(bmp, a, 0, 0)
    bitmaptools.blit(bmp, d, aw, 0)
    bitmaptools.blit(bmp, s, aw + dw, 0)

    return bmp, aw + dw + sw


def _make_line(bmp, w: int, y: int) -> dict:
    """Wrap a text bitmap with scroll state. Wide text gets a doubled marquee
    source so a DISP_W viewport never needs to wrap."""
    if w <= DISP_W:
        return {
            "bmp": bmp,
            "w": w,
            "y": y,
            "scroll": False,
            "off": 0,
            "cycle": 0,
        }

    src = displayio.Bitmap(2 * w + SCROLL_GAP, LINE_H, 16)
    bitmaptools.blit(src, bmp, 0, 0)
    bitmaptools.blit(src, bmp, w + SCROLL_GAP, 0)

    return {
        "bmp": src,
        "w": w,
        "y": y,
        "scroll": True,
        "off": 0,
        "cycle": w + SCROLL_GAP,
    }


def build_lines(artist: str, song: str) -> None:
    global lines
    if config["layout"] == LAYOUT_DOUBLE:
        top = max((DISP_H - (2 * LINE_H + LINE_GAP)) // 2, 0)
        ab, aw = _text_bitmap(artist, ARTIST_SLOT)
        sb, sw = _text_bitmap(song, SONG_SLOT)
        lines = [
            _make_line(ab, aw, top),
            _make_line(sb, sw, top + LINE_H + LINE_GAP),
        ]
    else:
        bmp, w = _compose_single(artist, song)
        lines = [_make_line(bmp, w, max((DISP_H - LINE_H) // 2, 0))]

    gc.collect()


def render() -> None:
    # Clear the buffer directly (no intermediate refresh) then blit + one
    # refresh, so the frame never flashes black mid-draw. clearscreen() would
    # refresh after filling, which is the flicker.
    window.fill(0)
    left = config["align"] == "left"
    for line in lines:
        if line["scroll"]:
            ox = line["off"]
            bitmaptools.blit(
                window,
                line["bmp"],
                0,
                line["y"],
                x1=ox,
                y1=0,
                x2=ox + DISP_W,
                y2=LINE_H,
            )
        else:
            x = 0 if left else max((DISP_W - line["w"]) // 2, 0)
            bitmaptools.blit(window, line["bmp"], x, line["y"])

    refresh()


config = load_config()
apply_colors()
lines = []
needs_rebuild = False  # layout change -> rebuild the bitmaps
needs_refresh = False  # color change -> repaint with the new palette


@ampule.route("/exit", method="GET")
def exit_app(request):
    load_settings.app_running = False
    return (200, {}, """<meta http-equiv="refresh" content="0; url=../" />""")


@ampule.route("/", method="GET")
def index(request):
    return (200, {}, header("Last.fm", app=True) + html_body + footer())


@ampule.route("/settings", method="GET")
def get_settings(request):
    return (200, {}, json.dumps(config))


@ampule.route("/", method="POST")
def update_settings(request):
    global needs_refresh, needs_rebuild
    p = request.params

    if "username" in p:
        config["username"] = url_decoder(p["username"])

    if "api_key" in p:
        config["api_key"] = url_decoder(p["api_key"])

    if "artist_color" in p:
        config["artist_color"] = "#" + p["artist_color"]
        apply_colors()
        needs_refresh = True

    if "song_color" in p:
        config["song_color"] = "#" + p["song_color"]
        apply_colors()
        needs_refresh = True

    if "dash_color" in p:
        config["dash_color"] = "#" + p["dash_color"]
        apply_colors()
        needs_refresh = True

    if "shadow_color" in p:
        config["shadow_color"] = "#" + p["shadow_color"]
        apply_colors()
        needs_refresh = True

    if "align" in p:
        config["align"] = p["align"]
        needs_refresh = True

    if "layout" in p:
        config["layout"] = p["layout"]
        needs_rebuild = True

    if "idle_timeout" in p:
        try:
            config["idle_timeout"] = int(p["idle_timeout"])
        except ValueError:
            config["idle_timeout"] = 0

    if "save" in p:
        save_config(config)

    return (200, {}, "ok")


build_lines("Last.fm", "loading")
render()
last_track = ("Last.fm", "loading")
last_poll = time.monotonic() - POLL_INTERVAL  # poll on the first iteration
last_active = time.monotonic()  # last time a song was playing; drives auto-exit

while load_settings.app_running:
    ampule.listen(socket)

    if check_if_button_pressed() == 2:
        sys.exit()

    redraw = False
    now = time.monotonic()

    if now - last_poll >= POLL_INTERVAL:
        last_poll = now
        try:
            artist, song, playing = fetch_now_playing()
            if playing:
                last_active = now
            track = (artist, song)
            if track != last_track:
                last_track = track
                build_lines(artist, song)
                redraw = True
        except Exception as e:
            print("lastfm fetch error:", e)

        gc.collect()

    timeout = config["idle_timeout"] * 60
    if timeout > 0 and now - last_active >= timeout:
        sys.exit()  # the kernel clears the screen and redraws the selector

    if needs_rebuild:
        needs_rebuild = False
        build_lines(last_track[0], last_track[1])
        redraw = True

    if needs_refresh:
        needs_refresh = False
        redraw = True

    scrolling = False
    for line in lines:
        if line["scroll"]:
            line["off"] = (line["off"] + SCROLL_SPEED) % line["cycle"]
            scrolling = True

    if scrolling or redraw:
        render()

    time.sleep(0.03 if scrolling else 0.1)
