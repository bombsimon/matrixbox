# Last.fm

This is an app that displays the currently playing song via [Last.fm]. This
means that any device and software that can [track music to Last.fm][track] will
work, e.g. Spotify, YouTube and Apple Music.

## Setup

The Last.fm API requires an API key which is free to generate via [Create API
account][create-api-account].

Once generated, start the app via the UI and fill in your Last.fm username and
the generated API key.

## Development notes

The code in this path is the human-readable code. It's compiled to `.mpy`
bytecode with [`mpy-cross`][mpy-cross] and copied to `apps/lastfm` to minimize
size on device; the HTML is minified for the same reason. See `build.py` in
`tools` for more info.

[Last.fm]: https://www.last.fm
[create-api-account]: https://www.last.fm/api/account/create
[mpy-cross]: https://github.com/adafruit/circuitpython/tree/main/mpy-cross
[track]: https://www.last.fm/about/trackmymusic
