import json  # noqa: I001 -- ruff wants to re-merge/re-sort the import groups below; don't
import time

import wifi

# matrixbox.display must import (and initialize the RGBMatrix hardware)
# before matrixbox.button claims the button's GPIO pins — see docs/ARCHITECTURE.md.
from matrixbox.display import display

from matrixbox import stats
from matrixbox.button import LONG_PRESS, SHORT_PRESS, button
from matrixbox.fonts import MINI
from matrixbox.layout import Align, TextGrid
from matrixbox.net import server_socket, wifi_manager
from matrixbox.settings import AppSettings, settings
from matrixbox.web import router, url_decode


def _show_network_prompt():
    # WifiManager.maintain() already brought the hotspot up — see docs/ARCHITECTURE.md.
    grid = TextGrid(display.canvas, font=MINI)
    display.canvas.fill(0)
    grid.line("No network", 0, color=4, align=Align.LEFT, clear=False)
    grid.line("Connect to:", 1, color=5, align=Align.LEFT, clear=False)
    grid.line(wifi_manager.hotspot_ssid, 2, color=1, align=Align.LEFT, clear=False)
    ap_ip = wifi.radio.ipv4_address_ap
    grid.line(
        str(ap_ip) if ap_ip else "...", -1, color=2, align=Align.LEFT, clear=False
    )
    display.refresh()


class AppSession:
    def __init__(self):
        self.current = None  # directory name of the app the kernel is running
        self.requested = None  # directory name the kernel should launch next
        self.instance = None  # the live App object, or None while idle

    @property
    def running(self) -> bool:
        return self.instance is not None

    def launch(self, name: str):
        self.requested = name

    def exit(self):
        self.instance = None
        self.current = None


session = AppSession()


class App:
    """Base class for a MatrixBOX app — subclass it, override render() and
    on_update(now), then MyApp().run(). See README.md "Writing an app"."""

    title = None  # falls back to session.current (the app's directory name)
    default_settings = {}
    tick_seconds = 0.1

    def __init__(self):
        self.router = router
        self.settings = settings
        self.display = display
        self.config = AppSettings(
            f"{session.current}_settings.json", self.default_settings
        )
        session.instance = self

    @property
    def running(self) -> bool:
        return session.instance is self

    def request_exit(self):
        session.exit()

    def render(self) -> str:
        """Override: HTML body for "/"."""
        return ""

    def on_settings_saved(self, values: dict):
        """Override: react to a /app-settings write."""

    def on_start(self):
        """Override: one-time setup."""

    def on_update(self, now: float):
        """Override: called once per tick."""

    def on_button(self):
        """Override: short button press (long always exits)."""

    def on_stop(self):
        """Override: cleanup after the loop ends."""

    def needs_network(self) -> bool:
        """Override: True pauses on_update() and shows the hotspot's SSID/IP
        on the display instead, for as long as Wi-Fi is down."""
        return False

    def run(self):
        self.on_start()
        showing_network_prompt = False
        while self.running:
            wifi_manager.maintain()
            router.listen(server_socket)
            press = button.poll()
            if press == LONG_PRESS:
                self.request_exit()
            elif press == SHORT_PRESS:
                self.on_button()

            if self.needs_network() and not wifi.radio.connected:
                if not showing_network_prompt:
                    _show_network_prompt()
                    showing_network_prompt = True
            else:
                showing_network_prompt = False
                self.on_update(time.monotonic())

            time.sleep(self.tick_seconds)
            stats.record_tick(self.tick_seconds)

        self.on_stop()


@router.route("/exit")
def _exit_route(request):
    if session.instance is not None:
        session.exit()

    return (200, {}, '<meta http-equiv="refresh" content="0; url=/" />')


@router.route("/app-settings")
def _get_app_settings(request):
    if session.instance is None:
        return (404, {}, "no app running")

    return (200, {}, json.dumps(session.instance.config.as_dict()))


@router.route("/app-settings", method="POST")
def _write_app_settings(request):
    app = session.instance
    if app is None:
        return (404, {}, "no app running")

    for key, value in request.params.items():
        if key == "save":
            continue

        try:
            app.config.set(key, url_decode(value))
        except KeyError:
            pass  # unknown setting for this app

    if "save" in request.params:
        app.config.save()

    app.on_settings_saved(request.params)

    return (200, {}, "ok")
