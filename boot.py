import os
import time

import storage
import supervisor

supervisor.runtime.autoreload = False  # see docs/architecture.md

from matrixbox.button import button
from matrixbox.display import display
from matrixbox.fonts import MINI
from matrixbox.layout import Align, TextGrid

_grid = TextGrid(display.canvas, font=MINI)


def _splash(text, color=4):
    display.canvas.fill(0)
    _grid.line(text, 0, color=color, align=Align.LEFT, clear=False)
    display.refresh()


def _lock_filesystem():
    storage.disable_usb_drive()
    storage.remount("/", False)


def _button_held_on_boot() -> bool:
    try:
        return button.pressed
    except Exception:
        return True  # can't read the button — fail toward unlocked


_splash("Booting...")

if "unlock" in os.listdir("/"):
    _lock_filesystem()
    try:
        os.remove("/unlock")
    except OSError:
        pass

    storage.enable_usb_drive()
    _splash("Unlocking filesystem")
elif "dev_mode" in os.listdir("/"):
    # disable_concurrent_write_protection: see docs/architecture.md.
    storage.remount("/", readonly=False, disable_concurrent_write_protection=True)
    _splash("Dev mode: unlocked")
elif _button_held_on_boot():
    _splash("Unlocking filesystem")
else:
    _lock_filesystem()
    _splash("Hold to unlock")
    time.sleep(1)

for stale_file in ("/code.py", "/reboot_required"):
    try:
        os.remove(stale_file)
    except OSError:
        pass

display.canvas.fill(0)
display.refresh()
