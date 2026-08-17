# AGENTS.md

Notes for an AI agent (or a human) working on this repo or a live
device. Everything here was verified against a running device, not
assumed — re-verify anything device-specific that seems off, hardware
facts drift.

## Device facts

- ESP32-S3 (Waveshare ESP32-S3-Zero), CircuitPython 10.1.4.
- Flash filesystem at `/`, roughly 940KB total, shared between the
  kernel, every app, and `settings.txt` — assume little headroom.
- `settings.txt` at root is the JSON-backed system config (Wi-Fi
  credentials, panel geometry, repository source/branch, etc).
- No public upstream repo yet. Update-checking exists as boilerplate
  (source/branch settings, GitHub tree API calls) but is unverified
  end to end until one exists.

## Deploying a change

`tools/sync.sh` copies this repo onto the mounted USB drive (macOS
metadata files excluded). `tools/push.py` is meant to do the same thing
over the network via `/console` and a file-write route, but currently
targets routes that no longer exist — don't rely on it until that's
fixed.

Syncing new files to the device has **no effect on its own** —
autoreload is deliberately disabled, so the device keeps running
whatever it last booted until it's actually rebooted. Sync, then
reboot, before concluding a change didn't work.

Before syncing: `ruff check`, `ruff format`, and `python3 -m py_compile`
on anything touched — cheap, catches most mistakes without needing
hardware.

## Remote access (verified working)

Two independent HTTP surfaces, both reachable at `http://<device-ip>/…`
once it's on Wi-Fi (shown in the navbar of any page it serves):

**`POST /console`** — raw Python, eval'd (falling back to exec for
statements), plain-text body in, plain-text output out:

```bash
curl -X POST http://<ip>/console -d '1+1'
curl -X POST http://<ip>/console -d 'import os; print(os.listdir("/"))'
```

**`/files/*`** — file manager API, JSON responses, target path in an
`X-Path` header:

```bash
curl -X POST http://<ip>/files/ls    -H 'X-Path: /'
curl -X POST http://<ip>/files/read  -H 'X-Path: /settings.txt'
curl -X POST http://<ip>/files/write -H 'X-Path: /some/file.py' -d '<contents>'
curl -X POST http://<ip>/files/mkdir -H 'X-Path: /some/dir'
curl -X POST http://<ip>/files/delete -H 'X-Path: /some/file.py'
```

Neither of these existed under this name before this rewrite — a much
earlier version of this project had a `/repl` endpoint driving a
base64/JSON tool-calling protocol for an on-device AI chat agent. That's
gone; don't reach for it.

**Serial REPL** still works independently of Wi-Fi/the web server —
connect over USB (`screen /dev/tty.usbmodem* 115200` on macOS), Ctrl+C
for a `>>>` prompt. The only way in if Wi-Fi is down or the filesystem
is locked (locking only hides the USB *drive*, not the serial port).

## The one styling gotcha that actually bites

HTML/JS built as adjacent Python string literals (the shape every
navbar/card/script block in this codebase takes) must not use f-strings
across that group — CircuitPython's parser handles merged adjacent
literals differently from CPython there, in ways that pass
`py_compile`/`ruff` and only surface on-device. A single standalone
f-string is fine; plain `+` concatenation is the safe default for
anything bigger. Full incident history in `docs/ARCHITECTURE.md`.

## Deeper internals

`docs/ARCHITECTURE.md` holds the "why" behind non-obvious decisions —
CircuitPython quirks found the hard way, hardware initialization
ordering, things that look like bugs but aren't. It's organized by file
name on purpose (source of truth for "where this lives") but never cites
line numbers, since those drift the moment a file changes.
