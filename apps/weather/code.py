import json
import math
import random
import time

from matrixbox.app import App
from matrixbox.display import display
from matrixbox.fonts import MINI
from matrixbox.net import http
from matrixbox.web import url_decode

DISP_W = display.width
DISP_H = display.height
TEXT_Y = DISP_H - MINI.height - 1
SKY_H = TEXT_Y

_WMO_DESC = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Icy fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Rain showers",
    81: "Heavy showers",
    82: "Violent showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Storm + hail",
    99: "Heavy storm",
}

_DEBUG_PRESETS = {
    "beach": ("clear", 28.0, 0, "day"),
    "winter": ("snow", -5.0, 73, None),
    "clear_day": ("clear", 18.0, 0, "day"),
    "clear_night": ("clear", 12.0, 0, "night"),
    "partly_cloudy": ("partly_cloudy", 15.0, 2, None),
    "cloudy": ("cloudy", 10.0, 3, None),
    "rain": ("rain", 8.0, 63, None),
    "storm": ("storm", 6.0, 95, None),
    "fog": ("fog", 4.0, 45, None),
    "snow": ("snow", 1.0, 73, None),
    "drizzle": ("drizzle", 9.0, 53, None),
}


def _wmo_to_cond(code):
    if code <= 1:
        return "clear"
    if code == 2:
        return "partly_cloudy"
    if code == 3:
        return "cloudy"
    if code in (45, 48):
        return "fog"
    if 51 <= code <= 55:
        return "drizzle"
    if (61 <= code <= 65) or (80 <= code <= 82):
        return "rain"
    if (71 <= code <= 77) or code in (85, 86):
        return "snow"
    if code >= 95:
        return "storm"

    return "clear"


def _parse_epoch(iso_datetime):
    # "YYYY-MM-DDTHH:MM" from the open-meteo API.
    date_part, time_part = iso_datetime.split("T")
    year, month, day = (int(v) for v in date_part.split("-"))
    hour, minute = (int(v) for v in time_part.split(":"))
    st = time.struct_time((year, month, day, hour, minute, 0, -1, -1, -1))

    return time.mktime(st)


class WeatherApp(App):
    title = "Weather"
    default_settings = {
        "city": "",
        "lat": 0.0,
        "lon": 0.0,
        "unit": "C",
        "interval": 300,
        "clock": 0,
        "clockmode": "24",
    }

    def needs_network(self) -> bool:
        return True

    def on_start(self):
        with open("template.html") as f:
            self.html_body = f.read()

        self.slots = {
            name: display.palette_allocator.allocate((0, 0, 0))
            for name in (
                "sky",
                "cloud1",
                "cloud2",
                "sun_moon",
                "glow",
                "red",
                "warm",
                "cool",
                "brown",
                "drop",
                "window",
                "bird",
            )
        }

        self.weather_code = -1
        self.temperature = None
        self.condition = "clear"
        self.status_msg = "Set a city" if not self.config["city"] else ""
        self.server_epoch = 0
        self.server_mono = 0.0
        self.sunrise_epoch = 0
        self.sunset_epoch = 0

        self.frame = 0
        self.clouds = []
        self.particles = []
        self.birds = []
        self.bolt_path = []
        self.lightning_age = 9999
        self.next_lightning = 120

        self._init_scene(self.condition)

        @self.router.route("/set-city", method="POST")
        def _set_city(request):
            city = url_decode(request.params.get("city", ""))
            if not city:
                return (200, {}, json.dumps({"error": "No city given"}))

            try:
                lat, lon, name = self._geocode(city)
            except Exception as e:  # broad: network/parsing failure modes vary
                print(f"weather: geocode failed: {e}")

                return (200, {}, json.dumps({"error": "City not found"}))

            self.config.set("city", name)
            self.config.set("lat", lat)
            self.config.set("lon", lon)
            self._fetch_weather()
            self.last_fetch = time.monotonic()

            return (200, {}, json.dumps({"ok": True, "city": name}))

        @self.router.route("/weather-data", method="GET")
        def _weather_data(request):
            desc = (
                _WMO_DESC.get(self.weather_code, "No data")
                if self.weather_code >= 0
                else "No data"
            )

            return (
                200,
                {},
                json.dumps(
                    {
                        "temp": self.temperature,
                        "desc": desc,
                        "city": self.config["city"],
                        "unit": self.config["unit"],
                    }
                ),
            )

        @self.router.route("/debug", method="POST")
        def _debug(request):
            mode = request.params.get("mode", "")
            preset = _DEBUG_PRESETS.get(mode)
            if preset:
                self._apply_debug_preset(preset)

            return (200, {}, json.dumps({"ok": True, "mode": mode}))

        @self.router.route("/refresh", method="POST")
        def _refresh(request):
            self._fetch_weather()
            self.last_fetch = time.monotonic()

            return (200, {}, json.dumps({"ok": True}))

        display.canvas.fill(0)
        display.refresh()

        if self.config["lat"] or self.config["lon"]:
            self._fetch_weather()

        self.last_fetch = time.monotonic()

    def render(self) -> str:
        return self.html_body

    def on_button(self):
        self._fetch_weather()
        self.last_fetch = time.monotonic()

    def on_update(self, now):
        if now - self.last_fetch >= int(self.config["interval"]):
            self._fetch_weather()
            self.last_fetch = now

        self._draw_scene()
        self._draw_bottom_bar()
        display.refresh()
        self.frame += 1

    # ── State helpers ────────────────────────────────────────────────────

    def _is_night(self):
        if not self.server_epoch or not self.sunrise_epoch or not self.sunset_epoch:
            return False

        now = self.server_epoch + int(time.monotonic() - self.server_mono)

        return now < self.sunrise_epoch or now >= self.sunset_epoch

    def _is_beach(self):
        return (
            self.condition == "clear"
            and self.temperature is not None
            and self.temperature > 23
            and not self._is_night()
        )

    def _is_winter(self):
        return (
            self.condition == "snow"
            and self.temperature is not None
            and self.temperature < 0
        )

    # ── Weather API ──────────────────────────────────────────────────────

    def _geocode(self, city):
        url = (
            "https://geocoding-api.open-meteo.com/v1/search?name="
            + city.replace(" ", "+")
            + "&count=1&language=en&format=json"
        )
        r = http.get(url)
        data = json.loads(r.text)
        r.close()
        result = data["results"][0]

        return result["latitude"], result["longitude"], result["name"]

    def _fetch_weather(self):
        lat = self.config["lat"]
        lon = self.config["lon"]
        if not lat and not lon:
            self.status_msg = "Set a city"

            return

        try:
            url = (
                "https://api.open-meteo.com/v1/forecast?latitude="
                + str(lat)
                + "&longitude="
                + str(lon)
                + "&current=temperature_2m,weather_code"
                + "&daily=sunrise,sunset&temperature_unit=celsius&timezone=auto"
            )
            r = http.get(url)
            data = json.loads(r.text)
            r.close()

            current = data["current"]
            self.temperature = current["temperature_2m"]
            new_code = current["weather_code"]
            self.weather_code = new_code

            try:
                self.server_epoch = _parse_epoch(current["time"])
                self.server_mono = time.monotonic()
            except Exception as e:  # broad: unexpected API response shape
                print(f"weather: time parse failed: {e}")

            try:
                daily = data["daily"]
                self.sunrise_epoch = _parse_epoch(daily["sunrise"][0])
                self.sunset_epoch = _parse_epoch(daily["sunset"][0])
            except Exception as e:  # broad: unexpected API response shape
                print(f"weather: sun times parse failed: {e}")

            new_cond = _wmo_to_cond(new_code)
            if new_cond != self.condition:
                self.condition = new_cond
                self._init_scene(self.condition)

            self.status_msg = ""
        except Exception as e:  # broad: network failure modes vary
            self.status_msg = str(e)[:40]
            print(f"weather: fetch failed: {e}")

    def _apply_debug_preset(self, preset):
        condition, temperature, weather_code, daylight = preset
        self.condition = condition
        self.temperature = temperature
        self.weather_code = weather_code
        if daylight is not None:
            self.server_epoch = time.mktime(time.localtime())
            self.server_mono = time.monotonic()
            if daylight == "day":
                self.sunrise_epoch = self.server_epoch - 3600
                self.sunset_epoch = self.server_epoch + 3600
            else:
                self.sunrise_epoch = self.server_epoch + 3600
                self.sunset_epoch = self.server_epoch - 3600

        self._init_scene(self.condition)

    # ── Scene setup ──────────────────────────────────────────────────────

    def _init_scene(self, cond):
        self.particles = []
        self.clouds = []
        self.birds = []
        self.bolt_path = []
        self.lightning_age = 9999
        self.next_lightning = self.frame + random.randint(60, 120)

        if cond in ("clear", "partly_cloudy"):
            n_birds = 1 if self._is_night() else 3
            for _ in range(n_birds):
                self.birds.append(
                    [
                        float(random.randint(-DISP_W, DISP_W)),
                        float(random.randint(3, max(4, DISP_H // 2 - 8))),
                        random.uniform(0.0, 6.28),
                        random.uniform(0.25, 0.55),
                    ]
                )

            if cond == "partly_cloudy":
                self.clouds.append(
                    [float(random.randint(DISP_W // 3, DISP_W - 10)), 2.0, 12]
                )

        elif cond in ("cloudy", "fog"):
            for _ in range(4):
                self.clouds.append(
                    [
                        float(random.randint(-12, DISP_W)),
                        float(random.randint(1, DISP_H // 3)),
                        random.randint(10, 18),
                    ]
                )

        elif cond in ("drizzle", "rain", "storm"):
            for _ in range(3):
                self.clouds.append(
                    [
                        float(random.randint(0, max(1, DISP_W - 20))),
                        float(random.randint(0, 5)),
                        random.randint(16, 24),
                    ]
                )

            n_drops = (
                40
                if cond == "storm"
                else (22 if cond == "rain" else 5 if cond == "drizzle" else 10)
            )
            for _ in range(n_drops):
                vy = random.uniform(1.5, 2.8)
                vx = -vy * 0.18
                self.particles.append(
                    [
                        float(random.randint(0, DISP_W - 1)),
                        float(random.randint(-DISP_H, 0)),
                        vx,
                        vy,
                    ]
                )

        elif cond == "snow":
            self.clouds.append([float(random.randint(0, DISP_W - 16)), 0.0, 14])
            self.clouds.append([float(random.randint(0, DISP_W - 14)), 2.0, 12])
            for _ in range(20):
                self.particles.append(
                    [
                        float(random.randint(0, DISP_W - 1)),
                        float(random.randint(-DISP_H, 0)),
                        random.uniform(-0.35, 0.35),
                        random.uniform(0.2, 0.55),
                    ]
                )

    def _make_bolt(self):
        self.bolt_path = []
        x = random.randint(DISP_W // 5, 4 * DISP_W // 5)
        y = 0
        while y < TEXT_Y - 2:
            self.bolt_path.append((x, y))
            y += 1
            if y % 3 == 0:
                x += random.choice([-2, -1, 1, 2])
                x = max(2, min(DISP_W - 3, x))

    # ── Drawing helpers ──────────────────────────────────────────────────

    def _sp(self, x, y, color):
        display.canvas.pixel(int(x), int(y), color)

    def _draw_cloud(self, x, y, w, color):
        c = display.canvas
        bh = max(3, w // 5)
        c.fill_rect(x, y + 2, w, bh, color)
        hw = max(2, w // 3)
        c.fill_rect(x + 1, y + 1, hw, 2, color)
        c.fill_rect(x + w // 2 - 1, y, hw + 1, 2, color)
        c.fill_rect(x + w - hw - 1, y + 1, hw, 2, color)

    def _draw_moon(self):
        s = self.slots
        display.palette_allocator.set(s["sun_moon"], (200, 180, 90))
        r = min(5, DISP_H // 7)
        cx, cy = DISP_W - r - 4, r + 2
        sx, sy = cx - r // 3, cy - 1
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r:
                    ddx, ddy = (cx + dx) - sx, (cy + dy) - sy
                    if ddx * ddx + ddy * ddy <= r * r:
                        continue

                    self._sp(cx + dx, cy + dy, s["sun_moon"])

    def _draw_sun(self):
        s = self.slots
        display.palette_allocator.set(s["sun_moon"], (255, 210, 0))
        display.palette_allocator.set(s["glow"], (255, 130, 0))
        r = min(5, DISP_H // 7)
        cx, cy = DISP_W - r - 4, r + 2
        for dy in range(-r - 1, r + 2):
            for dx in range(-r - 1, r + 2):
                d2 = dx * dx + dy * dy
                if r * r < d2 <= (r + 1) * (r + 1):
                    self._sp(cx + dx, cy + dy, s["glow"])

        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r:
                    self._sp(cx + dx, cy + dy, s["sun_moon"])

        phase = (self.frame // 6) % 2
        for i, (rdx, rdy) in enumerate(
            [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]
        ):
            rl = 2 if (i + phase) % 2 == 0 else 1
            for length in range(1, rl + 1):
                self._sp(
                    cx + rdx * (r + 1 + length),
                    cy + rdy * (r + 1 + length),
                    s["glow"],
                )

    def _draw_bird(self, bx, by, phase):
        wy = -1 if int(phase * 2) % 4 < 2 else 0
        c = self.slots["bird"]
        self._sp(bx - 2, by + wy, c)
        self._sp(bx - 1, by, c)
        self._sp(bx, by + 1, c)
        self._sp(bx + 1, by, c)
        self._sp(bx + 2, by + wy, c)

    def _draw_pine(self, cx, ground_y, h, color):
        trunk_h = max(2, h // 4)
        canopy_h = h - trunk_h
        tree_top = ground_y - h
        for y in range(ground_y - trunk_h, ground_y):
            self._sp(cx, y, self.slots["brown"])

        for row in range(canopy_h):
            y = tree_top + row
            half_w = (row * (canopy_h // 3 + 2)) // canopy_h
            for dx in range(-half_w, half_w + 1):
                self._sp(cx + dx, y, color)

            if row < 2 or row % 3 == 0:
                self._sp(cx - half_w, y, 5)
                self._sp(cx + half_w, y, 5)

        self._sp(cx, tree_top, 5)
        self._sp(cx, tree_top + 1, 5)

    def _draw_beach(self):
        s = self.slots
        c = display.canvas
        display.palette_allocator.set(s["red"], (200, 30, 30))
        display.palette_allocator.set(s["warm"], (220, 180, 60))
        display.palette_allocator.set(s["cool"], (30, 100, 180))
        display.palette_allocator.set(s["brown"], (120, 60, 20))

        sea_y = SKY_H * 2 // 3
        sand_y = SKY_H - 3
        c.fill_rect(0, sea_y, DISP_W, sand_y - sea_y, s["cool"])

        for x in range(DISP_W):
            wv = int(math.sin(self.frame * 0.06 + x * 0.25) * 1.2)
            self._sp(x, sea_y + wv, 5)
            if wv < 0:
                self._sp(x, sea_y + wv + 1, s["cool"])

        c.fill_rect(0, sand_y, DISP_W, SKY_H - sand_y, s["warm"])

        px = DISP_W // 4
        pole_top = sand_y - 7
        pole_bot = sand_y
        pr = max(4, DISP_W // 10)
        for y in range(pole_top, pole_bot + 1):
            self._sp(px, y, s["brown"])

        for dy in range(pr + 1):
            for dx in range(-pr, pr + 1):
                if dx * dx + dy * dy <= pr * pr:
                    stripe = ((dx + pr) * 4) // (2 * pr + 1)
                    color = s["red"] if stripe % 2 == 0 else 5
                    self._sp(px + dx, pole_top - dy, color)

        for dx in range(-pr, pr + 1):
            if dx * dx <= pr * pr:
                self._sp(px + dx, pole_top, s["red"])

    def _draw_winter(self):
        s = self.slots
        c = display.canvas
        display.palette_allocator.set(s["red"], (170, 20, 20))
        display.palette_allocator.set(s["warm"], (15, 90, 20))
        display.palette_allocator.set(s["cool"], (35, 110, 35))
        display.palette_allocator.set(s["brown"], (90, 50, 15))
        display.palette_allocator.set(s["window"], (230, 190, 40))
        display.palette_allocator.set(s["sun_moon"], (220, 90, 0))

        ground_y = SKY_H - 2

        hx = DISP_W * 3 // 5
        hw = max(10, DISP_W // 5)
        hh = max(7, SKY_H // 4)
        hy = ground_y - hh
        roof_h = max(3, hh // 3)
        c.fill_rect(hx, hy, hw, hh, s["red"])

        cx_h = hx + hw // 2
        for row in range(roof_h):
            span = (row + 1) * hw // (2 * roof_h)
            ry = hy - roof_h + row
            for x in range(cx_h - span, cx_h + span + 1):
                self._sp(x, ry, 0)

        for row in range(min(2, roof_h)):
            span = (row + 1) * hw // (2 * roof_h)
            ry = hy - roof_h + row
            for x in range(cx_h - span, cx_h + span + 1):
                self._sp(x, ry, 5)

        ch_x = cx_h + hw // 4
        ch_top = hy - roof_h - max(2, roof_h // 2)
        ch_bot = hy - roof_h + roof_h // 2
        for cy in range(ch_top, ch_bot + 1):
            self._sp(ch_x, cy, 0)
            self._sp(ch_x + 1, cy, 0)

        wy = hy + hh // 3
        ww = max(2, hw // 5)
        wh = max(2, hh // 4)
        wx = hx + hw // 5
        c.fill_rect(wx, wy, ww, wh, s["window"])

        dw = max(2, hw // 6)
        dh = max(3, hh // 2)
        dx0 = hx + hw * 3 // 5
        c.fill_rect(dx0, ground_y - dh, dw, dh, s["brown"])

        self._draw_pine(DISP_W * 2 // 5, ground_y, max(8, SKY_H // 3), s["warm"])
        self._draw_pine(DISP_W // 7, ground_y, max(5, SKY_H // 5), s["cool"])

        sx = DISP_W // 4
        br = max(3, SKY_H // 10)
        by = ground_y - br
        for dy in range(-br, br + 1):
            for dx in range(-br, br + 1):
                if dx * dx + dy * dy <= br * br:
                    self._sp(sx + dx, by + dy, 5)

        hr = max(2, br * 2 // 3)
        head_y = by - br - hr
        for dy in range(-hr, hr + 1):
            for dx in range(-hr, hr + 1):
                if dx * dx + dy * dy <= hr * hr:
                    self._sp(sx + dx, head_y + dy, 5)

        self._sp(sx - 1, head_y - 1, 0)
        self._sp(sx + 1, head_y - 1, 0)
        self._sp(sx, head_y, s["sun_moon"])
        self._sp(sx + 1, head_y, s["sun_moon"])
        self._sp(sx, by - br // 2, 0)
        self._sp(sx, by, 0)
        self._sp(sx, by + br // 2, 0)
        for i in range(1, br + 1):
            self._sp(sx - br - i, by - br // 2 + i // 2, s["brown"])
            self._sp(sx + br + i, by - br // 2 + i // 2, s["brown"])

        c.fill_rect(0, ground_y, DISP_W, 2, s["cool"])
        for x in range(DISP_W):
            h = (x * 137 + 53) % 97
            if h % 5 < 2:
                self._sp(x, ground_y, 5)

            if h % 7 < 1:
                self._sp(x, ground_y + 1, 5)

    # ── Per-frame scene render ──────────────────────────────────────────

    def _draw_scene(self):
        s = self.slots
        c = display.canvas
        night = self._is_night()

        if self.condition == "clear":
            display.palette_allocator.set(
                s["sky"], (5, 15, 35) if night else (10, 25, 55)
            )
            c.fill(0)
            c.fill_rect(0, 0, DISP_W, SKY_H, s["sky"])
        elif self.condition == "partly_cloudy":
            display.palette_allocator.set(
                s["sky"], (5, 15, 35) if night else (8, 20, 45)
            )
            c.fill(0)
            c.fill_rect(0, 0, DISP_W, SKY_H, s["sky"])
        elif self.condition == "cloudy":
            display.palette_allocator.set(s["sky"], (8, 20, 40))
            display.palette_allocator.set(s["cloud1"], (90, 92, 100))
            c.fill(0)
            c.fill_rect(0, 0, DISP_W, SKY_H, s["sky"])
        elif self.condition == "fog":
            display.palette_allocator.set(s["sky"], (55, 55, 60))
            display.palette_allocator.set(s["cloud1"], (110, 110, 115))
            c.fill(0)
            c.fill_rect(0, 0, DISP_W, SKY_H, s["sky"])
        elif self.condition in ("drizzle", "rain"):
            display.palette_allocator.set(s["sky"], (5, 18, 40))
            display.palette_allocator.set(s["cloud1"], (35, 45, 65))
            c.fill(0)
            c.fill_rect(0, 0, DISP_W, SKY_H, s["sky"])
        elif self.condition == "snow":
            display.palette_allocator.set(s["sky"], (8, 20, 38))
            display.palette_allocator.set(s["cloud1"], (65, 70, 80))
            display.palette_allocator.set(s["cloud2"], (40, 42, 48))
            c.fill(0)
            c.fill_rect(0, 0, DISP_W, SKY_H, s["sky"])
        elif self.condition == "storm":
            display.palette_allocator.set(s["sky"], (3, 4, 7))
            display.palette_allocator.set(s["cloud1"], (25, 25, 30))
            c.fill(0)
            c.fill_rect(0, 0, DISP_W, SKY_H, s["sky"])

            if self.frame >= self.next_lightning:
                self.lightning_age = 0
                self.next_lightning = self.frame + random.randint(60, 140)
                self._make_bolt()

            if self.lightning_age < 3:
                display.palette_allocator.set(s["red"], (130, 130, 60))
                for bx, by in self.bolt_path:
                    for dx in range(-3, 4):
                        self._sp(bx + dx, by, s["red"])

            self.lightning_age += 1
        else:
            c.fill(0)

        if self.condition in ("clear", "partly_cloudy"):
            if night:
                self._draw_moon()
            else:
                self._draw_sun()

        if self.condition != "clear":
            for cl in self.clouds:
                cl[0] -= 0.07
                if cl[0] + cl[2] < -5:
                    cl[0] = float(DISP_W + 3)

                color = s["cloud2"] if self.condition == "storm" else s["cloud1"]
                self._draw_cloud(int(cl[0]), int(cl[1]), int(cl[2]), color)

        if self.condition in ("clear", "partly_cloudy"):
            for b in self.birds:
                b[0] += b[3]
                b[2] += 0.12
                if b[0] > DISP_W + 5:
                    b[0] = -5.0
                    b[1] = float(random.randint(3, max(4, DISP_H // 2 - 8)))

                self._draw_bird(int(b[0]), int(b[1]), b[2])

        if self._is_beach():
            self._draw_beach()

        if self._is_winter():
            self._draw_winter()

        if self.condition in ("rain", "drizzle", "storm"):
            display.palette_allocator.set(s["drop"], (100, 130, 200))
            new_particles = []
            for p in self.particles:
                p[0] += p[2]
                p[1] += p[3]
                xi, yi = int(p[0]), int(p[1])
                if yi < TEXT_Y:
                    self._sp(xi, yi, s["drop"])
                    self._sp(xi - 1, yi - 1, s["drop"])
                    new_particles.append(p)
                else:
                    new_particles.append(
                        [float(random.randint(0, DISP_W - 1)), -1.0, p[2], p[3]]
                    )

            self.particles = new_particles
        elif self.condition == "snow":
            display.palette_allocator.set(s["drop"], (220, 225, 235))
            new_particles = []
            for p in self.particles:
                p[0] = (
                    p[0] + p[2] + math.sin(self.frame * 0.04 + p[0] * 0.15) * 0.08
                ) % DISP_W
                p[1] += p[3]
                xi, yi = int(p[0]), int(p[1])
                if yi < TEXT_Y:
                    self._sp(xi, yi, s["drop"])
                    new_particles.append([p[0], p[1], p[2], p[3]])
                else:
                    new_particles.append(
                        [float(random.randint(0, DISP_W - 1)), -1.0, p[2], p[3]]
                    )

            self.particles = new_particles

        if self.condition == "storm":
            display.palette_allocator.set(s["red"], (130, 130, 60))
            if 3 <= self.lightning_age < 12:
                for bx, by in self.bolt_path:
                    self._sp(bx, by, s["red"])
                    self._sp(bx + 1, by, s["red"])

    def _draw_bottom_bar(self):
        c = display.canvas
        city = self.config["city"]
        if city:
            max_chars = DISP_W // 5
            c.text(city[:max_chars], 1, TEXT_Y, font=MINI, color=5)

        if self.temperature is not None:
            t = self.temperature
            if self.config["unit"] == "F":
                t = t * 9.0 / 5.0 + 32.0

            sign = "-" if t < 0 else ""
            unit_letter = "f" if self.config["unit"] == "F" else "c"
            text = sign + str(abs(int(t))) + unit_letter + "°"
            tw = MINI.text_width(text)
            c.text(text, DISP_W - tw - 1, TEXT_Y, font=MINI, color=5)
        elif self.status_msg:
            c.text(
                self.status_msg[: DISP_W // 4],
                2,
                TEXT_Y,
                font=MINI,
                color=5,
            )

        if int(self.config["clock"]) and self.server_epoch:
            now_epoch = self.server_epoch + int(time.monotonic() - self.server_mono)
            lt = time.localtime(now_epoch)
            hour = lt.tm_hour
            minute = ("0" + str(lt.tm_min)) if lt.tm_min < 10 else str(lt.tm_min)
            if self.config["clockmode"] == "12":
                suffix = "a" if hour < 12 else "p"
                hour = hour % 12 or 12
                text = str(hour) + ":" + minute + suffix
            else:
                text = str(hour) + ":" + minute

            cw = MINI.text_width(text)
            c.text(text, (DISP_W - cw) // 2, TEXT_Y, font=MINI, color=5)


WeatherApp().run()
