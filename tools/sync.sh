#!/usr/bin/env bash
# Sync the kernel, libs, and apps to a MatrixBOX mounted as a USB drive.
# The device is fully mirrored to this repo — anything under the synced
# paths that isn't here gets deleted.
#
# Requires the filesystem to be unlocked first (hold the button before
# power-on, or an /unlock or /dev_mode file already dropped — see
# README.md "Offline setup") — a locked device never shows up as a drive.
#
# IMPORTANT: macOS buffers writes to a USB mass-storage drive; this
# script's own `sync` call at the end is necessary but on its own not
# always sufficient. Resetting the device (over the network or the
# button) *immediately* after this script exits can still catch a write
# mid-flush and truncate a file on the device — confirmed on real
# hardware, see docs/ARCHITECTURE.md. Give it a few seconds after this
# script finishes before rebooting the device.
#
# Set DEVICE_IP to the device's network address (shown in the navbar of
# any page it serves) to blank the display before writing and restore it
# after — the USB mass-storage write competing with the matrix's own
# refresh visibly flickers the panel otherwise. Best-effort: skipped
# entirely if DEVICE_IP is unset, and a failed request here never fails
# the sync itself.
#
# Usage:
#   tools/sync.sh [mount-path]
#   DEVICE_IP=10.0.0.5 tools/sync.sh

set -euo pipefail

MOUNT="${1:-/Volumes/CIRCUITPY}"
DEVICE_IP="${DEVICE_IP:-}"

if [ ! -d "$MOUNT" ]; then
    echo "error: $MOUNT not found — is the device unlocked and plugged in?" >&2
    exit 1
fi

blank_display() {
    local visible="$1"
    [ -n "$DEVICE_IP" ] || return 0

    curl -s -m 3 -X POST "http://$DEVICE_IP/console" \
        -d "from matrixbox.display import display; display.set_visible($visible); display.refresh()" \
        > /dev/null \
        || echo "  (couldn't reach $DEVICE_IP — continuing)"
}

cd "$(dirname "$0")/.."

VERSION_FILE=$(find . -maxdepth 1 -name 'v[0-9]*' -print -quit)
if [ -z "$VERSION_FILE" ]; then
    echo "error: no version marker file (v<version>) found at repo root" >&2
    exit 1
fi

if [ -n "$DEVICE_IP" ]; then
    echo "Blanking display on $DEVICE_IP..."
    blank_display False
fi

echo "Syncing -> $MOUNT (mirrored — anything not in this repo gets deleted)"
# --checksum: the device's FAT32 drive doesn't preserve mtimes precisely
# enough for rsync's normal size+time change detection to be reliable, so
# without this every file looks "changed" on every sync — see
# docs/ARCHITECTURE.md. Compares content, not timestamps, so it still
# only transfers files that actually changed (skipping unnecessary writes
# to slow flash) without the false-negative risk --size-only would have.
COPYFILE_DISABLE=1 rsync -av --delete --checksum \
    --exclude=.DS_Store --exclude='._*' --exclude=__pycache__/ --exclude='*.pyc' \
    matrixbox main.py boot.py safemode.py "${VERSION_FILE#./}" lib apps \
    "$MOUNT/"

# COPYFILE_DISABLE is supposed to stop macOS from writing AppleDouble
# sidecar files (._name) when copying to a filesystem that can't hold
# extended attributes/resource forks (FAT32, like CIRCUITPY) — in
# practice a few still slip through, plus Finder drops its own .Trashes/
# .fseventsd/.Spotlight-V100 on any removable volume it's touched. None
# of that belongs on the device (wastes flash, clutters the file
# browser), so sweep it up explicitly rather than trust the copy step.
echo "Removing macOS metadata files left on the device..."
find "$MOUNT" \( \
    -name '._*' -o -name '.DS_Store' -o -name '.Trashes' \
    -o -name '.fseventsd' -o -name '.Spotlight-V100' \
    \) -exec rm -rf {} + 2>/dev/null || true

# --delete only prunes inside the directories rsync actually syncs
# (matrixbox/, apps/, lib/) plus the handful of root files named above —
# it never sees a stray file sitting loose elsewhere at the mount root
# (e.g. a leftover /web.py from an old manual copy), so that kind of
# cruft survives forever unless swept up explicitly here too.
echo "Removing stray files at the device root..."
for f in "$MOUNT"/*.py; do
    [ -e "$f" ] || continue
    name="$(basename "$f")"
    case "$name" in
        main.py | boot.py | safemode.py) ;;
        *)
            echo "  removing /$name (not one of main.py/boot.py/safemode.py)"
            rm -f "$f"
            ;;
    esac
done

echo "Flushing writes to disk..."
sync

if [ -n "$DEVICE_IP" ]; then
    echo "Restoring display on $DEVICE_IP..."
    blank_display True
fi

echo "Done. Wait a few seconds before rebooting the device — see the note at the top of this script."
