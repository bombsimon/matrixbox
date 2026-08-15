# MatrixBOX

An ESP32-S3 (CircuitPython) LED matrix box. Connects to Wi-Fi, runs a
selectable set of small display apps, and serves a web UI (settings,
console, file manager) from the device itself.

## Wireless setup

1. Connect to the Wi-Fi hotspot shown on screen
2. Browse to 192.168.4.1
3. Select your network + password
4. Once online, the device gets a new IP from your router, it's shown
   in the navbar of any page it serves

## Offline setup

1. Hold the button _before_ plugging the device into a computer — the
   check happens once, instantly, at power-on, so pressing it after
   seeing anything on screen is already too late for that boot
2. Edit `settings.txt` directly (JSON — `ssid`, `password`, etc.)
3. The filesystem locks again on the next reboot

**While developing**, drop an empty `dev_mode` file at the root (over USB
once unlocked, or `open("/dev_mode", "w").close()` from the serial REPL)
to skip the button-timing dance entirely — the filesystem stays unlocked
on every boot until you delete that file. Remove it before handing off or
shipping a device.

**If the button-hold doesn't unlock it and you have no other way in**,
the serial console works even while the filesystem is locked (that only
hides the USB _drive_, not the serial port): connect with a serial
terminal (e.g. `screen /dev/tty.usbmodem* 115200` on macOS), press
Ctrl+C to get a `>>>` prompt, then:

```python
open("/unlock", "w").close()
import microcontroller
microcontroller.reset()
```

Changing files on disk — over USB, or remotely (see `AGENTS.md`) — never
takes effect on its own; the device only re-reads them on the next
reboot.

## The screen

Panel resolution, tiling, rotation, and RGB/color-correction are all
settings, editable from Settings → Advanced in the web UI without
touching `settings.txt` by hand. Changing any of them reboots the
device, since the matrix driver only reads them once at boot.

## Contributing

Instagram: @matrixbox.app · web: matrixbox.app · e-mail: info@matrixbox.app
