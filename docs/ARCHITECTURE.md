# Design notes

Not deployed to the device (see `docs/` in `.gitignore`-style — kept out
of the flash payload deliberately; only `main.py`, `boot.py`, `safemode.py`,
`matrixbox/`, and `apps/` go on the device). This is the "why" behind
`matrixbox/`'s design, kept out of the source files themselves to save
flash — `README.md` covers the "how to use it" side and *is* worth
keeping in sync with these.

## boot.py — filesystem lock, auto-reload

Auto-reload (CircuitPython's default behavior of resetting and re-running
`main.py` on any write it sees over USB) is disabled unconditionally.
It reacts to a host OS's own background writes — Spotlight, `.DS_Store`,
backups — not just deliberate file edits, and combined with `dev_mode`
holding the filesystem mounted read-write indefinitely, that turns into
a reset loop unrelated to anything this project does. Nothing here
relies on auto-reload, so there's no downside to leaving it off.

`dev_mode`'s `storage.remount(..., disable_concurrent_write_protection=True)`
exists because the host (USB) and the running code need *separate* write
permissions, and every other lock/unlock path only ever grants one or
the other. The tradeoff — per CircuitPython's own docs — is a small risk
of corruption if both sides touch the same file at the same instant;
acceptable for active development, not for a shipped device.

## matrixbox/app.py — AppSession, App

`session.instance` (not just `session.current`, a name string) is what
lets `/exit` and `/app-settings` be registered exactly once, ever, and
still find whichever app is currently running — they read
`session.instance` at request time rather than closing over anything
app-specific. That's also why nothing needs to be cleared or restored on
the route table for the common case: the routes never reference a
particular app's state directly.

`App.needs_network()` (default `False`) is the generic version of
something the old codebase only had inside one app (`departures`): when
`True`, `run()` stops calling `on_update()` and shows the hotspot's
SSID/IP instead, for as long as Wi-Fi is down — without the user having
to exit the app to reach settings and fix the network. Nothing new here
actually *brings up* the hotspot; `WifiManager.maintain()` already does
that unconditionally, for the kernel and every app, whether or not
`needs_network()` is overridden — this only adds the on-screen prompt,
gated behind the flag so apps that don't need connectivity (or fetch
lazily/tolerate being offline) aren't interrupted by it.

## matrixbox/display.py — Canvas, Display

The only module (besides `matrixbox.boards`) that imports
`displayio`/`framebufferio`/`rgbmatrix`. `display` is a singleton built
once on first import and shared via the module cache — CircuitPython
runs `boot.py` and `main.py` in the same process, so the hardware is
only ever initialized once regardless of which one imports it first.

Every canvas (the root one and any `new_canvas()`) is built with the same
palette depth (20 values) as the full system palette, so a slot handed
out by `PaletteAllocator` is always safe to draw with on any canvas — no
per-app guessing about bitmap bit depth. The original code mixed 16- and
20-value bitmaps depending on which app wrote it, which was a real source
of subtle bugs.

`Display.__init__` refreshes once against an empty group before building
any real content. The RGB matrix's DMA buffer can still hold whatever
was last scanned out before this boot — garbage from a prior crash, or
noise from the panel's own power-up — so this guarantees the very first
thing ever driven onto the panel is off, not whatever was left over.

`apply_settings()` sets `reboot_pending = True` on a geometry change
(width/height/tiles/color correction) rather than calling
`microcontroller.reset()` itself — it used to, and that was a real bug:
`apply_settings()` runs inside the settings POST handler, right after
`settings.save()` and before the HTTP response is sent, so an immediate
reset() could both cut off `save()`'s write before it reached flash
(see `matrixbox/settings.py` above for what that actually did to a live
device) and kill the response before the browser ever saw it succeed.
`main()`'s loop checks `display.reboot_pending` (and
`updater.reboot_pending`, same reasoning) right after `router.listen()`
returns each tick — by then the response has gone out — with a short
sleep first as extra margin for the write to settle.

Font glyph data (`mini.py`/`small.py`/`large.py`) is one dict per font,
`char -> (width, *rows)`. `Canvas.text()` supports two formats: most
glyphs are an on/off bitmask, but it also understands rows stored as
digit strings, which it reads as literal per-pixel palette indices —
for shading a plain bitmask can't express, ignoring `color`/`shadow`
since the digits already are the color. `#` and `^` still use that
format (unused by any current app, so harmless), but `%` used to as
well, hardcoded to system palette slots 3/5 (blue/white) — invisible
under the old codebase, which never implemented the shaded-glyph format
at all and silently skipped these characters. Once this codebase added
real support for the format, `%` started rendering exactly as authored:
a large blue-and-white blob overriding whatever color the caller asked
for, wherever a string contained `%` (e.g. every row of the stocks
app). Replaced with an ordinary bitmask glyph sized like the surrounding
digits, in all three fonts.

## matrixbox/web.py — Router, router

`router` is a single shared singleton — the kernel and every app register
onto the same route table and poll the same one via `.listen()`. That's
what lets routes like the kernel's own `/settings` stay reachable no
matter what's running: whoever is currently looping (the kernel when
idle, an app while it runs) services the whole table, not just the routes
that owner happens to care about. See `main.py`'s module docstring for
the full lifecycle.

The accept/parse/dispatch/respond loop handles ESP32 socket quirks that
are easy to miss: partial sends, `EAGAIN` on non-blocking sockets,
null-byte truncation on binary garbage in the request. The `EAGAIN`
retry-with-zero-bytes-sent case in `_send_response` is a known ESP32-S2
firmware quirk (adafruit/circuitpython#4420), not defensive paranoia.

`listen()`'s exception handler is the last line of defense for a single
request and must never itself raise, or one bad request takes down the
whole kernel loop — which is exactly what happened once: it called
`sys.print_exception()` for better diagnostics, which isn't implemented
on every CircuitPython build, and the resulting `AttributeError` escaped
uncaught and crashed everything. It now tries that and falls back to a
plain message on any failure.

## matrixbox/settings.py — JSONStore, Settings, AppSettings

Values are coerced to match the *type of their default* on load, so a
hand-edited or corrupted settings file can never hand an app a string
where it expects an int. This is also why `autostart`/`screensaver`
default to `""` rather than `0`/`False`: those two settings hold either
an empty "off" value or an app-name string, and an int/bool default would
make the coercion silently discard a real app name that got typed in.

`AppSettings` intentionally is *not* a shared file across apps — one JSON
file per app, loaded fresh on each launch, keeps memory small (an app
never has to load or even know about any other app's config) and matches
how the old per-app `*settings.json` files already worked.

`save()` writes to a `.tmp` sibling and `os.rename()`s it over the real
file rather than truncating the real file in place — found the hard way,
via a real device stuck offline with an unrecoverable-looking
`ssid length must be 1-32` error. The actual cause: `settings.txt` had
several stray bytes *after* its closing `}` (almost certainly a
`microcontroller.reset()` — see `matrixbox/display.py` below — firing
before the write it followed had been flushed to flash), which made
`json.loads()` raise on trailing data even though the JSON itself was
completely intact. `load()`'s except swallowed that `ValueError` and
silently kept blank defaults — `ssid=""` is valid JSON-store state, not
an error, so it looked like the device had simply never been configured,
with the real cause invisible. Two independent fixes went in together:
`load()` now prints when it falls back to defaults instead of failing
silently, and `save()` can no longer produce a half-written file for it
to choke on in the first place — a `rename()` either lands the fully
written new content or doesn't happen at all, nothing in between.

## matrixbox/color.py — Color, PaletteAllocator

Slots 0-7 are the fixed system palette (see `Display.__init__`) and are
never touched by `PaletteAllocator`. The kernel calls `reset()` (and
restores slots 0-7) after every app exits, so an allocated slot is only
ever meaningful within a single run — this replaced the old pattern where
apps hardcoded "spare" slot numbers by convention and hoped nothing else
used them.

## matrixbox/boards.py — BoardProfile, detect_board

This is the *only* file in the whole codebase that should know which GPIO
pin goes where on which board. Everything else — the kernel, every app —
is chip-agnostic. Supporting a new board means adding one `BoardProfile`
here; nothing else changes.

Each board's pins are built by a factory function, not a module-level
constant — a real bug on real hardware caught this: `board.GPIO1` (say)
only exists on boards that actually have a pin by that name, so a
module-level `BoardProfile(..., rgb_pins=[board.GPIO1, ...])` for *every*
board raises `AttributeError` on any board that doesn't happen to have
that pin, even though `detect_board()` would never have picked that
profile. `detect_board()` only calls the one factory whose match fires,
so the other boards' pin names are never referenced at all.

## matrixbox/scroll.py, matrixbox/text.py — Scroller, Span, ScrollingLine

A full scroll cycle is: hold at the start, scroll to the end, hold again,
then snap back to the start — the state machine behind a marquee-style
readout, implemented once for all four directions instead of per-app.
`ScrollingLine` only wraps itself in a `Scroller` when the composed
content is actually wider than its viewport; short text just draws once,
no scroll state at all.

`Scroller.transition(old, new, ...)` reuses that same state machine for a
different job: a one-shot swap from one piece of content to another
(e.g. the app selector sliding to the next app name) instead of an
abrupt redraw. It works by blitting `old` and `new` side by side into one
strip and scrolling exactly one viewport-width across it, then setting
`hold_end` long enough that it never loops back — `.finished` becomes
true once the destination has arrived and stays true, unlike a normal
looping `Scroller` where it's only briefly true each cycle.
`run_to_completion(draw)` drives that to blocking completion for the
one-shot case, hiding the update/draw split — a continuously-looping
`Scroller` still drives `update()`/`draw()` itself, per tick, interleaved
with everything else an app's loop does.

## matrixbox/button.py — Button

This button is electrically noisy well beyond normal mechanical-switch
bounce — bursts of raw transitions lasting hundreds of ms to multiple
seconds, not just a few ms around contact make/break, confirmed by
logging raw transitions from `/console` during real presses. Debouncing
new *transitions* (press starts, release starts) works by waiting for
the raw pin to hold one value for `debounce_seconds` before trusting it,
restarting that wait on every raw flip, bounce or not — this can't
misfire the way an earlier version did, which measured elapsed time from
the *first* edge of a press and let unrelated bounces after that edge
accumulate into a false long-press.

Checking *whether `long_press_seconds` has elapsed*, though, is
deliberately **not** gated behind that same stability wait — it's
evaluated on every poll, unconditionally, as long as a press is
confirmed. Gating it the same way new transitions are gated meant that
during a hold that kept bouncing the whole way through (not just at the
edges), the code could go a long time without ever landing on a moment
stable enough to even ask "has enough time passed?" — so a deliberate
hold could take far longer than the configured threshold to register,
and conversely, once the noise finally happened to settle, elapsed
wall-clock time had already piled up in the meantime and the long-press
would fire as if instantly. Decoupling the two — new-transition
detection stays gated on stability, elapsed-time-since-confirmed-press
does not — fixed both symptoms at once, since they were the same bug.

The physical button sits across two GPIO pins (not one pin and ground) —
one is read, but the other has to be held at a defined level too or the
read pin never changes state at all, even though nothing ever reads that
second pin's value directly.

Which hardware peripheral claims its pins *first*, at boot, matters too
— the RGB matrix driver has to finish initializing before
`matrixbox.button` ever touches the button's GPIO pins, or the button
reads noisy and unreliable. The old codebase always imported its display
driver fully before its button module for exactly this reason; this
port's alphabetically-sorted imports (`matrixbox.button` importing
before `matrixbox.display` inside `matrixbox.app`, itself the first
thing the package imports) inverted that order by accident, and the
auto-formatter wants to keep inverting it back — `matrixbox/app.py`
forces the correct order with a `noqa` on the import-sort check for
exactly that reason.

Before this ordering was fixed, a raw-pin trace from `/console` appeared
to show inverted polarity (idle low, pressed high) and the code was
briefly changed to match. That measurement was taken while the button
was still fighting the display driver for its pins and doesn't hold once
the order above is correct: with the RGB matrix initializing first, the
pin behaves as the standard pull-up/active-low default (idle high,
pressed low), confirmed by a clean guided trace from `/console` — a tap
producing a single short dip, a deliberate hold producing one dip
matching the hold duration. `Button` uses that default polarity
(`active_low=True`) and does not override it.

## matrixbox/net.py — WifiManager

`wifi_manager` is shared for the same reason `router` is: both the
kernel's idle loop and a running `App` call `maintain()` every tick, so
the device keeps retrying the configured network in the background (and
drops the fallback hotspot once it reconnects) regardless of what's
running — it never gets stuck on the hotspot until a reboot, which the
original code could do.

## matrixbox/updater.py — app and system updates

Boilerplate, not yet exercised against a real upstream — this codebase
has no public repo to point at yet, so `check_all()`/`update_app()`/
`update_system()` are written against the *shape* GitHub will present
once one exists, unverified end to end.

A version is a marker file — an app directory, or the filesystem root
for the system as a whole, contains exactly one file named `v<version>`
(content, if any, is just human-readable metadata; only the filename is
read). `repository_source` (`"owner/repo"`) and `repository_branch` are
two separate settings rather than one opaque URL specifically so both
the raw-content URL and the GitHub API tree URL can be *derived*,
instead of parsed back out of a stored URL string the way the original
code's `_repo_api_base()` did.

`fetch_remote_tree()` makes one recursive call to the GitHub tree API
(`git/trees/<branch>?recursive=1`) and buckets every file by top-level
app directory, plus a `"/"` entry for root files + `matrixbox/` (the
system). One call instead of one directory listing per app, because
`raw.githubusercontent.com` has no directory-listing endpoint at all —
the tree API is the only way to discover what files exist upstream
without already knowing their names.

`update_app()`/`update_system()` download every file for a target
before writing anything to disk (`_download_all()`), so a network
failure partway through never leaves an app — or worse, the system —
with half its files replaced. `update_system()` cannot safely call
`microcontroller.reset()` itself: it runs inside a request handler, and
`router.listen()` only sends the HTTP response *after* the handler
returns (see main.py's lifecycle below) — resetting from inside the
handler would kill the connection before the browser ever sees success.
It sets `updater.reboot_pending = True` instead; `main()`'s loop checks
that flag immediately after `router.listen()` returns each tick, by
which point the response for the request that set the flag has already
gone out, and only then resets.

`components.navbar()` shows a small dot next to the version number when
`updater.available` is non-empty. That dict is populated by an explicit
"Check for updates" click (`/updates/check`), never polled
automatically — there's no upstream yet to poll, and even once there is,
checking is a paid GitHub API call better left to explicit user action
than a background timer. `check_all()` mutates `available` in place
(`.clear()` + `.update()`) rather than rebinding the name, because
`components.py` does `from matrixbox.updater import available` — a
rebind in `updater.py` would leave that import pointing at the old,
now-stale dict forever.

## main.py — the full lifecycle

`autostart` fires once per boot, tracked by a local flag in `main()`,
not by re-reading the setting every loop tick — it names the app to
launch *at boot*, not "whenever the kernel is idle." Checking the
setting directly on every tick (an earlier version did) means the
instant that app exits, the very next tick sees `autostart` still set
and relaunches it immediately, making it look like the button is
broken (every exit attempt gets yanked straight back into the app)
when the actual bug is autostart re-firing underneath it.

Every app and the kernel share ONE `Router` and ONE listening socket.
Whoever is currently looping — the kernel when idle, an app's own
`App.run()` while one is active — services the whole route table, so
routes registered once stay reachable no matter what's running. Only `/`
is state-dependent: it renders the app list when idle, or delegates to
`session.instance.render()` while an app is running.

`run_app()` snapshots `len(router.routes)` before launching an app and
truncates back to it in `finally` — the same eviction pattern used for
`sys.modules` — so any one-off route an app registers via `self.router`
doesn't accumulate across launches. This is a full *handoff*, not
concurrency: only one loop is ever running, so there is no real
simultaneity to reason about, just "whoever owns the loop right now
services every registered route."

The `sys.modules` eviction (snapshot the kernel's own modules once at
boot, delete anything else after an app exits) exists for two reasons:
memory — there's no RAM to spare for keeping a previous app's imports
around — and correctness, since re-importing a stale cached module on
the next launch (rather than re-running its top-level code fresh) would
carry over whatever state it had when the last app exited.

Apps live under `/apps/<name>` on the device, same as in this repo — an
earlier version flattened them to the filesystem root on first boot
(`os.chdir("/" + name)` needed them there), which also meant every
top-level directory had to be checked against an exclusion list to avoid
being mistaken for an app (this is exactly what caused `matrixbox` itself
to briefly show up as a runnable app after the package was renamed).
`os.chdir(f"{APPS_DIR}/{name}")` and scanning `/apps` for `installed_apps()`
removed the need for both the migration step and the exclusion list.

## matrixbox/\_\_init\_\_.py — importing every submodule up front

CircuitPython's `sys.path` puts the empty string (current-directory-relative)
ahead of `/` (absolute root): `['', '/', '.frozen', '/lib']`. The first time
anything does `import matrixbox`, CircuitPython resolves the package via
whichever `sys.path` entry matches first *at that moment* — at kernel boot
that's still `cwd == "/"`, so it resolves through `''` and caches
`matrixbox.__path__` as the bare relative string `"matrixbox"` rather than an
absolute path. Submodules already imported by kernel-boot time reuse that
cached package object directly from `sys.modules` and are unaffected. But a
submodule nobody has imported yet gets searched for relative to
`matrixbox.__path__` at the moment it's *first* requested — and `run_app()`
calls `os.chdir(f"{APPS_DIR}/{name}")` before an app's own `code.py` runs, so
any matrixbox submodule an app is the first to use (`matrixbox.text`,
`matrixbox.scroll`, ...) gets searched for relative to the *app's* directory
instead of matrixbox's own, and fails with `no module named 'matrixbox.X'`
even though the file is right there.

The fix is for `matrixbox/__init__.py` to import every one of its own
sibling submodules, since `__init__.py` runs automatically — and completely,
before returning control — the moment anything does `import matrixbox` or
`from matrixbox import ...`, which `main.py` does immediately, while `cwd`
is still `/`. That guarantees every submodule is already resolved and
cached in `sys.modules` before any app gets a chance to `chdir()`, including
submodules only an app ever uses, not the kernel itself — so no individual
app or future submodule needs its own workaround.

## Building HTML/JS strings — no f-strings in a multi-segment literal group

**The rule, current and load-bearing:** when building a string out of many
adjacent literals — the shape every navbar/card/script block in
`matrixbox/components.py` and the settings pages in `main.py` take — none
of the segments are f-strings. Use plain strings joined with explicit
`+`, and drop any dynamic value in with `+ value +` (assign it to a
plain variable first if it's a subscript, e.g. `ssid = settings["ssid"]`
above the block). A single, standalone, one-line f-string is fine on its
own (`f"{symbol} {change:.1f}%"` in `apps/stocks/code.py` is untouched);
the danger is specifically an f-string sharing a multi-line adjacent
group with other literals.

This isn't a style preference — it's a scar. CircuitPython's parser has
at least two distinct, undocumented differences from CPython in exactly
this situation, both invisible to `python3 -m py_compile`/`ruff` and both
found by shipping broken code to the device:

1. CircuitPython merges adjacent string literals into one piece of
   source *before* parsing an f-string among them (CPython keeps each
   literal's own f/non-f parsing separate even when concatenated this
   way). A literal `{`/`}` meant to stay literal — JS object syntax, a
   function body — in a *plain* literal sharing a group with an f-string
   gets read as a format field instead, raising `KeyError` at request
   time, not at compile time. `matrixbox/components.py`'s `navbar()`
   shipped exactly this (`{method:'POST'}` in a plain string next to an
   f-string threw `KeyError: method` on every page load).
2. Even with every segment consistently an f-string and every literal
   brace doubled to `{{`/`}}` to escape it (the fix for #1), a `{expr}`
   containing a subscript with a quoted key — `{settings["ssid"]}` —
   raised a plain `SyntaxError` at *import* time, taking down all of
   `main.py` (black screen, dead web server) rather than just one route.
   The same expression, `f'foo="<{x["a"]}>"'`, evaluates correctly as a
   *standalone* one-line f-string (confirmed on-device via `/console`) —
   only the combination with #1's merged-group shape breaks.

Fixing #2 by switching to a bare-name reference inside the merged f-string
group did *not* fix it — the `SyntaxError` persisted at the same
statement. Whatever CircuitPython's parser is actually doing to a large
merged f-string group here isn't fully understood; rather than keep
finding its edges one broken deploy at a time, don't hand it a
multi-segment f-string at all. Plain `+` concatenation of strings and
names has no equivalent parsing magic to go wrong.

A literal's *substituted value* containing braces is always fine —
`"prefix" + content + "suffix"` where `content` is a string full of `{}`
works correctly regardless of any of this; both quirks above are about
literal `{`/`}`/subscript syntax in the *source text*, not about what a
variable's value happens to contain at runtime.

### A JS-quote-inside-a-JS-string needs `\\'`, not `\'`, inside `"""..."""`

`main.py`'s big inline `<script>` blocks are one `"""..."""` Python
string, and *Python's own* backslash-escape rules still apply inside a
triple-quoted string — only the "does a bare quote end the string"
question changes (it doesn't, for `'`/`"`; only `"""` does). That
distinction is exactly what broke `renderUpdates()`'s generated
`onclick="applyUpdate('...', this)"`: the JS source needs a literal
two-character `\'` (backslash, then apostrophe) so that *the browser's
JS parser* reads it as JS's own escaped-quote-within-a-single-quoted-
string. Writing `\'` in the Python source doesn't produce that — Python
consumes the backslash as its *own* escape for `'` before the string
ever leaves this file, emitting a bare apostrophe instead. Followed by
the next literal `'` in the source (harmless in a plain single-quoted
Python string, where it would just close the string — but a no-op here,
since only `"""` closes a triple-quoted one), the actual output was two
adjacent apostrophes: invalid at the point the browser tried to parse
it, which took the *entire* `<script>` block down with it — including
every other function declared later in the same block, since a parse
error prevents all of them from being hoisted, not just the one nearest
the mistake. `toggleAdvanced is not defined` was the resulting error,
even though `toggleAdvanced` itself had nothing wrong with it.

The fix is `\\'` (backslash-backslash, then a bare `'`) — `\\` is
Python's escape for a literal backslash, and the following `'` doesn't
need escaping at all in a triple-quoted string, so it passes through
untouched. Result: exactly the two characters, `\` then `'`, that the
*browser* needs to see. Verified by actually executing the generated
script in Node rather than re-reading it — reasoning about escape
layering in the abstract is exactly how the wrong fix got shipped the
first time.

## Porting apps from the old codebase — lessons from apps/paint

`str.isalnum()` is not implemented on this CircuitPython build —
confirmed via `/console` (`'a'.isalnum()` raises `AttributeError`). The
old code relied on it for sanitizing user-supplied save-file names; the
port checks membership in an explicit allowed-character string instead.
This bit *specifically* because the bug only showed up inside the real
route handler, never in an isolated `/console` script used to narrow it
down — the script had the save name hardcoded and never exercised the
sanitizer at all, so several rounds of "reproduce it standalone" kept
succeeding while the real thing kept failing for what looked like the
same code. Lesson: an isolated repro needs to exercise the *exact* same
call path, not a hand-simplified version of it — a diagonal shortcut
here is exactly where a diverging assumption hides.

A naive one-pixel-at-a-time flood fill (Python-level BFS, one native
pixel call per pixel) measured well over two minutes for a few thousand
pixels on real hardware — the old codebase had the same algorithm, so
this wasn't a regression, but it's bad enough to be worth fixing on
sight once measured. A scanline fill (`fill_rect()` for whole
contiguous runs, one queued seed point per run instead of per pixel)
brought the same operation to under 2 seconds.

Building a whole-canvas data structure (and its full JSON serialization)
in memory inside a request handler is a real crash risk here, even when
an equivalent top-level script handles the same data size fine — the
handler runs several stack frames deeper (inside `App.run()` →
`router.listen()` → the route closure), leaving less contiguous memory
available than a fresh script gets. Writing large saved state row by
row, streaming straight to the open file, avoids ever holding the whole
structure (or its serialized form) at once.

Syncing files to the device over USB is not synchronous — macOS buffers
mass-storage writes, and resetting the device immediately after
`tools/sync.sh` finishes can catch a write mid-flush and truncate a file
on the device (confirmed on real hardware: a font data file cut off
mid-statement, taking the whole kernel down with a `SyntaxError` at
boot, since `matrixbox/fonts` is imported eagerly). `sync.sh` calls
`sync` at the end now, but that's a floor, not a guarantee — give it a
few seconds of slack before rebooting regardless.

## The save-settings button — one convention, two rendering paths

`components.save_button()` is the only place the markup/class/icon for a
"Save Settings" button is written. `main.py`'s settings page calls it
directly, since that page is Python-generated. App `template.html` files
are static text read verbatim by `render()` — no templating, no way for
them to call into Python — so their button markup is hand-copied to match
`save_button()`'s output byte-for-byte (`btn btn-full btn-save`, the same
floppy-disk icon and label) rather than generated. Keep them in sync by
eye when either changes. The shared bits that *can* live in one place
already do: the `.btn-save` CSS (`matrixbox/theme.py`) and the
"call `save(this)`, set the button's text once the fetch resolves"
JS pattern, which every save button — system settings, stocks, lastfm —
follows.

## Fixing the scroller app — offset and the frozen vertical mode

Two real bugs found porting `apps/scroller`, both from the same root
cause: `on_update()` only redrew the display when `Scroller.update(now)`
returned `True` — which only happens on an actual scroll-position change.
Content that fits the viewport with nothing to scroll (a single line in
vertical mode, where each line's height already equals the display
height) never triggers that, so it never got an initial draw at all —
switching to vertical mode with short text just froze whatever was on
screen before. Static mode was also silently ignoring the offset
setting entirely — it had its own draw path that never read it.

Fixed by drawing every mode's content into a display-sized scratch
canvas (`self.viewport`) via a single `_draw_frame()` that always runs
once after every rebuild, then compositing that onto the real display
canvas with an explicitly clamped, explicitly clipped offset — not
relying on `bitmaptools.blit()`'s own dest-bounds clipping behavior for
correctness. `on_settings_saved()` now also calls `_draw_frame()`
directly when only `offset` changes, since that doesn't need a full
`_rebuild()`.

## The `/app-settings` POST body gotcha, twice

`Request.params` only ever comes from the URL query string —
`matrixbox/web.py`'s `Request._parse_params()` never looks at the POST
body. Every route in this codebase that takes POST data expects
`?key=val` in the URL, body-only POSTs silently produce empty params.
This bit weather's `/set-city` handler (JS sent the city as a POST body)
and, separately, one of my own live `/console` test scripts probing the
scroller bug — the fix in both cases was the same: send data as a query
string via the shared `post(qs)` JS helper pattern every other route
already uses, not a request body.

## Device stats — CPU load is an approximation, not a real metric

CircuitPython has no OS-level scheduler to ask "what's the load" — the
kernel and every app are each a single cooperative while-loop with a
fixed `time.sleep()` at the end. `matrixbox/stats.py`'s `record_tick()`
approximates load as an EWMA of "how much of each loop iteration wasn't
the known sleep call" — called once per iteration, right after that
iteration's `time.sleep()`, from both `main()`'s loop and `App.run()`'s
(never both at once, since only one loop is ever active). It's a rough
duty-cycle signal, not a real per-process CPU percentage — good enough
for "is something stuck/busy" at a glance in the navbar, nothing more.
Memory and flash stats (`mem_bytes()`, `flash_bytes()`) are exact,
straight from `gc.mem_free()`/`mem_alloc()` and `os.statvfs("/")`.

## App catalog — installed and not-yet-installed apps in one list

`updater.build_catalog()` merges `_installed_app_names()` with every app
name found in the upstream repo's `apps/` tree, so the home page's app
list can offer *not-yet-installed* upstream apps as installable, not
just show update badges on ones already present. Installing and
updating are the same backend call (`updater.update_app()` via the
existing `/updates/apply` route) — `_ensure_dir()` + `_download_all()`
don't care whether the target directory already existed, so "install"
needed no new download path, only a UI that offers it when
`installed=False`.

Remote file sizes come free from GitHub's tree API (`item["size"]` on
every blob) — `fetch_remote_tree()` captures per-app totals into a
module-level `_remote_sizes` dict as a side effect, read via
`remote_size()`, rather than costing a second tree fetch or changing
that function's existing return shape (several other functions already
depend on it being `{name: [file_paths]}`).

Uninstalling is a plain recursive directory delete
(`updater.uninstall_app()`), guarded by requiring the name to already be
in `_installed_app_names()` before touching the filesystem — that also
doubles as the path-traversal guard, since a crafted name can't match a
real installed directory. Confirmed working on real hardware — deleted
and then restored the weather app as a live test of the route itself.

## Settings saves blank the display too, same as sync.sh

The old codebase blanked the panel (`display.root_group.hidden = True`)
around every filesystem write it made from the web UI — not just big
ones — since even a small write can visibly disturb the panel while the
flash operation has the CPU's attention. `JSONStore.save()` (used by
both global settings and every app's own config) does the same now via
`display.set_visible()`, so this is automatic for every save — no route
handler needs to remember to wrap its own `.save()` call.

`matrixbox.display` is imported *inside* `save()`, not at module level —
`matrixbox.display` itself imports `matrixbox.settings` for the panel's
configured width/height/tiles, so a top-level import the other way would
be circular. By the time anything actually calls `.save()` (well after
boot), `matrixbox.display` is already fully imported and cached, so the
inline import just costs a `sys.modules` lookup.

## Static IP — ported from departures' `no_dhcp`, made a system setting

The old codebase's static-IP support (`apps/departures/functions.py`'s
`no_dhcp` file + `manual_dns()`) only existed inside the departures app,
gated behind an obscure hidden toggle (`varinit.dns`, flipped by visiting
`/dns`) most users would never find. It's genuinely a device-wide network
setting, not an app concern, so it's part of `Settings` (`static_ip`/
`static_netmask`/`static_gateway`/`static_dns` in `matrixbox/settings.py`'s
`DEFAULTS`) and applied by `WifiManager._apply_static_ip()` — always
visible in Settings → Advanced, not hidden behind a secret route.

A blank `static_ip` means DHCP, same "presence implies enabled" convention
the old `no_dhcp` file itself used, rather than a separate on/off flag
that could disagree with the address fields. `_apply_static_ip()` must run
*before* `wifi.radio.connect()` — CircuitPython only accepts
`set_ipv4_address()` while not yet associated to an AP, matching the old
code's own call order (`manual_dns()` before `wifi.radio.connect()`).

## WiFi network scan — a manual, blocking action

`wifi.radio.start_scanning_networks()` blocks for several seconds and
freezes everything else on the device while it runs (single cooperative
loop — no request handling, no app switching, no display refresh happens
until it returns). That's fine for what it's for: an explicit "Scan"
button click on the Settings page, not a background or automatic check.
`/wifi/scan` (`main.py`) dedupes by SSID (keeping the strongest of any
duplicate, since the same network can show up on multiple channels/APs)
and returns them sorted by signal strength. The result only ever *fills*
the existing SSID text input via a picker `<select>` — it never replaces
manual entry, since not every network being connected to will show up in
a scan (hidden SSIDs, being out of range at setup time, etc).
