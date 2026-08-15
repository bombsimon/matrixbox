#!/usr/bin/env bash
# Sync the kernel, libs, and apps to a MatrixBOX mounted as a USB drive.
# The device is fully mirrored to this repo — anything under the synced
# paths that isn't here gets deleted (including apps not yet migrated to
# the App base class; see README.md "What's deferred").
#
# Requires the filesystem to be unlocked first (hold the button before
# power-on, or an /unlock or /dev_mode file already dropped — see
# README.md "Offline setup") — a locked device never shows up as a drive.
#
# Usage:
#   tools/sync.sh [mount-path]

set -euo pipefail

MOUNT="${1:-/Volumes/CIRCUITPY}"

if [ ! -d "$MOUNT" ]; then
    echo "error: $MOUNT not found — is the device unlocked and plugged in?" >&2
    exit 1
fi

cd "$(dirname "$0")/.."

VERSION_FILE=$(find . -maxdepth 1 -name 'v[0-9]*' -print -quit)
if [ -z "$VERSION_FILE" ]; then
    echo "error: no version marker file (v<version>) found at repo root" >&2
    exit 1
fi

echo "Syncing -> $MOUNT (mirrored — anything not in this repo gets deleted)"
COPYFILE_DISABLE=1 rsync -av --delete \
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

echo "Done."
