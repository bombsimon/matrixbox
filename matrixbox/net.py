import time

# Adafruit's own libraries, unmodified, live in /lib not matrixbox/ — see docs/ARCHITECTURE.md.
import adafruit_connection_manager
import adafruit_requests
import socketpool
import wifi

from matrixbox.settings import settings

pool = socketpool.SocketPool(wifi.radio)
http = adafruit_requests.Session(
    pool, adafruit_connection_manager.get_radio_ssl_context(wifi.radio)
)


def _open_server_socket(port=80, backlog=5):
    sock = pool.socket()
    sock.setblocking(False)
    sock.setsockopt(pool.SOL_SOCKET, pool.SO_REUSEADDR, 1)
    sock.bind(("", port))
    sock.listen(backlog)

    return sock


server_socket = _open_server_socket()


class WifiManager:
    RETRY_INTERVAL = 30

    def __init__(self, settings):
        self.settings = settings
        self.status = ""
        self._last_retry = time.monotonic()
        wifi.radio.tx_power = float(settings["wifi_power"])

    @property
    def hotspot_ssid(self) -> str:
        mac = "".join(hex(b) for b in wifi.radio.mac_address).replace("0x", "")

        return f"matrixbox-{mac[:3]}"

    def connect(self, timeout=15, silent=False):
        self.status = ""
        self._last_retry = time.monotonic()
        ssid = str(self.settings["ssid"])
        password = str(self.settings["password"])
        channel = int(self.settings.get("channel", 0) or 0)
        try:
            if channel:
                wifi.radio.connect(ssid, password, channel=channel, timeout=timeout)
            else:
                wifi.radio.connect(ssid, password, timeout=timeout)
            self.settings.save()
        except Exception as e:
            # broad: Wi-Fi failure modes here aren't a small fixed set
            self.status = str(e)
            if not silent:
                print("wifi connect failed:", e)

    def start_hotspot(self):
        try:
            wifi.radio.start_ap(ssid=self.hotspot_ssid)
        except Exception as e:
            print("hotspot start failed:", e)

    def apply_settings(self):
        wifi.radio.tx_power = float(self.settings["wifi_power"])

    def maintain(self):
        if wifi.radio.connected:
            if wifi.radio.ap_active:
                wifi.radio.stop_ap()

            return

        if not wifi.radio.ap_active:
            self.start_hotspot()

        now = time.monotonic()
        if now - self._last_retry >= self.RETRY_INTERVAL:
            self.connect(timeout=3, silent=True)


wifi_manager = WifiManager(settings)
