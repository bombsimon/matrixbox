import math
import time

import bitmaptools

from matrixbox.app import App
from matrixbox.color import hex_to_rgb
from matrixbox.display import display
from matrixbox.fonts import MINI, font_by_name
from matrixbox.net import http, pool

DISP_W = display.width
DISP_H = display.height


def _hsv_to_rgb(h):
    h = h % 360
    s = 6
    i = h // 60
    f = h - i * 60
    q = (60 - f) * 255 // 60
    t = f * 255 // 60
    table = {
        0: (255 // s, t // s, 0),
        1: (q // s, 255 // s, 0),
        2: (0, 255 // s, t // s),
        3: (0, q // s, 255 // s),
        4: (t // s, 0, 255 // s),
    }

    return table.get(i, (255 // s, 0, q // s))


def _angle(value, total):
    return (value / total) * (2.0 * math.pi) - math.pi / 2.0


def _draw_hand(canvas, cx, cy, angle, length, color, thick=False):
    ex = int(cx + math.cos(angle) * length + 0.5)
    ey = int(cy + math.sin(angle) * length + 0.5)
    canvas.line(cx, cy, ex, ey, color)
    if thick:
        dx = int(math.cos(angle + math.pi / 2.0) + 0.5)
        dy = int(math.sin(angle + math.pi / 2.0) + 0.5)
        canvas.line(cx + dx, cy + dy, ex, ey, color)
        canvas.line(cx - dx, cy - dy, ex, ey, color)


def _draw_circle_outline(canvas, cx, cy, r, color):
    x, y = 0, r
    d = 3 - 2 * r
    while x <= y:
        for px, py in (
            (cx + x, cy + y),
            (cx - x, cy + y),
            (cx + x, cy - y),
            (cx - x, cy - y),
            (cx + y, cy + x),
            (cx - y, cy + x),
            (cx + y, cy - x),
            (cx - y, cy - x),
        ):
            canvas.pixel(px, py, color)

        if d < 0:
            d += 4 * x + 6
        else:
            d += 4 * (x - y) + 10
            y -= 1

        x += 1


class ClockApp(App):
    title = "Clock"
    default_settings = {
        "show_date": 1,
        "show_day": 1,
        "show_seconds": 0,
        "show_temp": 0,
        "city": "",
        "f_hex": "#ffffff",
        "b_hex": "#000000",
        "scale": 1,
        "mode": "digital",
        "font": "large",
        "hour_hex": "#ffffff",
        "min_hex": "#4488ff",
        "sec_hex": "#ff4444",
        "show_border": 1,
        "h12": 0,
        "blink_colon": 1,
        "rainbow": 0,
        "accent": 0,
        "accent_hex": "#4488ff",
        "show_dots": 1,
        "dots_hex": "#ffffff",
        "shadow_hex": "",
        "frame_hex": "",
        "show_shadow": 1,
    }

    def on_start(self):
        with open("template.html") as f:
            self.html_body = f.read()

        self.slots = {
            name: display.palette_allocator.allocate((0, 0, 0))
            for name in (
                "fg",
                "bg",
                "shadow",
                "frame",
                "hour",
                "min",
                "sec",
                "dots",
                "accent",
            )
        }
        self._apply_colors()

        try:
            dt = self._fetch_datetime()
        except Exception as e:  # broad: network/socket failure modes vary
            print(f"clock: time sync failed: {e}")
            dt = ("00", "00", "00", "---", "--- --")

        self.hour, self.minute, self.second, self.day_name, self.date_str = dt
        self.temp_string = ""
        if int(self.config["show_temp"]) and self.config["city"]:
            self.temp_string = self._fetch_temperature()

        self.sync_epoch = (
            int(self.hour) * 3600 + int(self.minute) * 60 + int(self.second)
        )
        self.sync_mono = time.monotonic()
        self.last_resync = self.sync_mono
        self.weather_counter = 0
        self.colon_on = True
        self.rainbow_hue = 0
        self.prev_second = -1
        self.last_tstr = ""
        self.last_analog = ""

        display.canvas.fill(0)
        display.refresh()

    def render(self) -> str:
        return self.html_body

    def on_settings_saved(self, values):
        if any(
            k in values
            for k in (
                "f_hex",
                "b_hex",
                "hour_hex",
                "min_hex",
                "sec_hex",
                "accent_hex",
                "dots_hex",
                "shadow_hex",
                "frame_hex",
                "show_shadow",
            )
        ):
            self._apply_colors()

        if (
            ("city" in values or "show_temp" in values)
            and int(self.config["show_temp"])
            and self.config["city"]
        ):
            self.temp_string = self._fetch_temperature()

        self.last_tstr = ""
        self.last_analog = ""

    def on_update(self, now):
        elapsed = now - self.sync_mono
        epoch = int(self.sync_epoch + int(elapsed)) % 86400
        h, rem = divmod(epoch, 3600)
        m, s = divmod(rem, 60)

        self.hour = ("0" + str(h)) if h < 10 else str(h)
        self.minute = ("0" + str(m)) if m < 10 else str(m)
        self.second = ("0" + str(s)) if s < 10 else str(s)

        if now - self.last_resync > 300:
            try:
                dt = self._fetch_datetime()
                self.hour, self.minute, self.second, self.day_name, self.date_str = dt
                self.sync_epoch = (
                    int(self.hour) * 3600 + int(self.minute) * 60 + int(self.second)
                )
                self.sync_mono = now
            except Exception as e:  # broad: network/socket failure modes vary
                print(f"clock: resync failed: {e}")

            self.last_resync = now

        if int(self.config["show_temp"]) and int(elapsed) % 600 < 2 and s < 2:
            if self.weather_counter == 0:
                self.weather_counter = 1
                self.temp_string = self._fetch_temperature()
        elif s >= 2:
            self.weather_counter = 0

        if int(self.config["show_seconds"]):
            timestring = self.hour + ":" + self.minute + ":" + self.second
        else:
            timestring = self.hour + ":" + self.minute

        mode = self.config["mode"]
        if int(self.config["rainbow"]) and mode == "digital":
            self.rainbow_hue = (self.rainbow_hue + 3) % 360
            rgb = _hsv_to_rgb(self.rainbow_hue)
            display.palette_allocator.set(self.slots["fg"], rgb)
            display.palette_allocator.set(
                self.slots["shadow"], (rgb[0] // 4, rgb[1] // 4, rgb[2] // 4)
            )
            display.palette_allocator.set(
                self.slots["dots"], (rgb[0] // 3, rgb[1] // 3, rgb[2] // 3)
            )
            self.last_tstr = ""

        new_colon = int(now * 2) % 2 == 0
        colon_changed = new_colon != self.colon_on
        self.colon_on = new_colon
        second_changed = s != self.prev_second
        self.prev_second = s

        if mode == "analog":
            if second_changed:
                self._draw_analog(h, m, s)
                display.refresh()
        elif mode == "analog_rect":
            if second_changed:
                self._draw_analog_rect(h, m, s)
                display.refresh()
        elif second_changed or (int(self.config["blink_colon"]) and colon_changed):
            self._draw_digital(timestring, self.colon_on)
            display.refresh()

    def _apply_colors(self):
        s = self.slots
        fg = hex_to_rgb(self.config["f_hex"])
        display.palette_allocator.set(s["fg"], fg)
        display.palette_allocator.set(s["bg"], hex_to_rgb(self.config["b_hex"]))
        if int(self.config["show_shadow"]):
            shadow = (
                hex_to_rgb(self.config["shadow_hex"])
                if self.config["shadow_hex"]
                else (fg[0] // 4, fg[1] // 4, fg[2] // 4)
            )
        else:
            shadow = (0, 0, 0)

        display.palette_allocator.set(s["shadow"], shadow)
        frame = (
            hex_to_rgb(self.config["frame_hex"])
            if self.config["frame_hex"]
            else (fg[0] // 6, fg[1] // 6, fg[2] // 6)
        )
        display.palette_allocator.set(s["frame"], frame)
        display.palette_allocator.set(s["hour"], hex_to_rgb(self.config["hour_hex"]))
        display.palette_allocator.set(s["min"], hex_to_rgb(self.config["min_hex"]))
        display.palette_allocator.set(s["sec"], hex_to_rgb(self.config["sec_hex"]))
        display.palette_allocator.set(s["dots"], hex_to_rgb(self.config["dots_hex"]))
        display.palette_allocator.set(
            s["accent"], hex_to_rgb(self.config["accent_hex"])
        )

    def _fetch_datetime(self):
        # Same makeshift NTP-via-HTTP-Date-header approach as the old
        # code, against the same project-operated endpoint — see
        # docs/ARCHITECTURE.md.
        with pool.socket() as sock:
            sock.settimeout(5)
            sock.connect(("data.t-skylt.se", 89))
            sock.sendall(b"GET / HTTP/1.0\r\nHost: data.t-skylt.se\r\n\r\n")
            buf = bytearray(512)
            n = sock.recv_into(buf)
            raw = bytes(buf[:n]).decode("utf-8")

        datestr = raw.split("Date:", 1)[1].split("\r\n")[0].strip()
        day_name = datestr[0:3]
        day_num = datestr[5:7]
        month = datestr[8:11]
        time_str = datestr[17:25]
        hour = str(int(time_str[0:2]))
        minute = str(int(time_str[3:5]))
        second = str(int(time_str[6:8]))
        hour = ("0" + hour) if len(hour) == 1 else hour
        minute = ("0" + minute) if len(minute) == 1 else minute
        second = ("0" + second) if len(second) == 1 else second

        return (hour, minute, second, day_name, day_num + " " + month)

    def _fetch_temperature(self):
        city = self.config["city"]
        if not city:
            return ""

        try:
            r = http.get("http://wttr.in/" + city.replace(" ", "+") + "?format=%t")
            data = r.text
            r.close()
        except Exception as e:  # broad: network failure modes vary
            print(f"clock: weather fetch failed: {e}")

            return ""

        clean = "".join(c for c in data.strip() if c in "+-0123456789cf ")

        return clean.strip()

    def _render_dim(self, canvas, text, x, y):
        canvas.text(text, x, y, font=MINI, color=self.slots["dots"])

    def _draw_digital(self, timestring, colon_vis):
        s = self.slots
        font = font_by_name(self.config["font"])
        fh = font.height
        requested_scale = int(self.config["scale"])

        dstr = timestring
        colon_blank = "(" * font.glyph(":")[0]
        if int(self.config["blink_colon"]) and not colon_vis:
            dstr = dstr.replace(":", colon_blank)

        ampm = ""
        if int(self.config["h12"]):
            parts = timestring.split(":")
            h24 = int(parts[0])
            ampm = "am" if h24 < 12 else "pm"
            h12 = h24 % 12 or 12
            hstr = str(h12)
            sep = (
                colon_blank
                if (int(self.config["blink_colon"]) and not colon_vis)
                else ":"
            )
            dstr = sep.join([hstr] + parts[1:])
            ref = ":".join(["12"] + parts[1:])
        else:
            ref = timestring

        text_w = font.text_width(dstr)
        ref_w = font.text_width(ref)
        glyphs = display.new_canvas(text_w + 2, fh + 2)
        shadow_on = int(self.config["show_shadow"])
        glyphs.text(
            dstr,
            0,
            0,
            font=font,
            color=s["fg"],
            shadow=s["shadow"] if shadow_on else None,
        )

        info_parts = []
        if int(self.config["show_day"]):
            info_parts.append(self.day_name)

        if int(self.config["show_date"]):
            info_parts.append(self.date_str)

        if ampm:
            info_parts.append(ampm)

        if int(self.config["show_temp"]) and self.temp_string:
            info_parts.append(self.temp_string)

        info_str = " . ".join(info_parts)
        info_h = 6 if info_str else 0
        accent_gap = 3 if int(self.config["accent"]) else 0

        max_time_h = max(1, DISP_H - info_h - accent_gap - 2)
        scale = max(1, requested_scale)
        shadow_pad = scale if shadow_on else 0
        while scale > 1 and (
            ref_w * scale + shadow_pad > DISP_W or fh * scale + shadow_pad > max_time_h
        ):
            scale -= 1
            shadow_pad = scale if shadow_on else 0

        sw = ref_w * scale + shadow_pad
        sh = fh * scale + shadow_pad
        total_h = sh + info_h + accent_gap
        time_y = max((DISP_H - total_h) // 2, 0)

        display.canvas.fill_rect(0, 0, DISP_W, DISP_H, s["bg"])

        if scale == 1:
            tx = max((DISP_W - text_w) // 2, 0)
            display.canvas.blit(glyphs, tx, time_y, skip=0)
        else:
            bitmaptools.rotozoom(
                display.canvas.bitmap,
                glyphs.bitmap,
                ox=DISP_W // 2,
                oy=time_y + (glyphs.height // 2) * scale,
                px=glyphs.width // 2,
                py=glyphs.height // 2,
                angle=0.0,
                scale=float(scale),
                skip_index=0,
            )

        if int(self.config["accent"]):
            ay = time_y + sh + 1
            if ay < DISP_H:
                line_w = min(max(sw // 3, 8), DISP_W - 4)
                ax = (DISP_W - line_w) // 2
                display.canvas.fill_rect(ax, ay, line_w, 1, s["accent"])

        if info_str:
            iy = time_y + sh + accent_gap
            iw = MINI.text_width(info_str)
            ix = max((DISP_W - iw) // 2, 0)
            if iy + 5 <= DISP_H:
                self._render_dim(display.canvas, info_str, ix, iy)

        self.last_tstr = timestring

    def _draw_analog(self, h, m, s):
        tag = f"{h}:{m}:{s}" if int(self.config["show_seconds"]) else f"{h}:{m}"
        if tag == self.last_analog:
            return

        self.last_analog = tag
        slots = self.slots
        r = min(DISP_W, DISP_H) // 2 - 2
        if DISP_H <= 32 and DISP_W > DISP_H:
            cx = r + 2
        else:
            cx = DISP_W // 2

        cy = DISP_H // 2
        display.canvas.fill_rect(0, 0, DISP_W, DISP_H, slots["bg"])

        if int(self.config["show_border"]):
            _draw_circle_outline(display.canvas, cx, cy, r, slots["frame"])

        if int(self.config["show_dots"]):
            for i in range(12):
                a = _angle(i, 12)
                tx = int(cx + math.cos(a) * r + 0.5)
                ty = int(cy + math.sin(a) * r + 0.5)
                display.canvas.pixel(tx, ty, slots["dots"])

        h12 = (h % 12) + m / 60.0
        _draw_hand(
            display.canvas,
            cx,
            cy,
            _angle(h12, 12),
            int(r * 0.5),
            slots["hour"],
            thick=True,
        )
        _draw_hand(
            display.canvas,
            cx,
            cy,
            _angle(m, 60),
            int(r * 0.8),
            slots["min"],
            thick=True,
        )
        if int(self.config["show_seconds"]):
            _draw_hand(
                display.canvas, cx, cy, _angle(s, 60), int(r * 0.85), slots["sec"]
            )

        display.canvas.pixel(cx, cy, slots["fg"])

        if DISP_H <= 32 and DISP_W > DISP_H:
            if int(self.config["accent"]):
                sep_x = cx + r + 3
                if 0 <= sep_x < DISP_W:
                    display.canvas.line(sep_x, 1, sep_x, DISP_H - 2, slots["accent"])

                text_x = sep_x + 3
            else:
                text_x = cx + r + 4

            info_parts = []
            if int(self.config["show_day"]):
                info_parts.append(self.day_name)

            if int(self.config["show_date"]):
                info_parts.append(self.date_str)

            if int(self.config["show_temp"]) and self.temp_string:
                info_parts.append(self.temp_string)

            ty = 2
            for part in info_parts:
                if text_x < DISP_W and ty + 5 <= DISP_H:
                    self._render_dim(display.canvas, part, text_x, ty)
                    ty += 8

    def _draw_analog_rect(self, h, m, s):
        tag = f"{h}:{m}:{s}" if int(self.config["show_seconds"]) else f"{h}:{m}"
        if tag == self.last_analog:
            return

        self.last_analog = tag
        slots = self.slots
        pad = 2
        cx, cy = DISP_W // 2, DISP_H // 2
        hw, hh = DISP_W // 2 - pad, DISP_H // 2 - pad
        display.canvas.fill_rect(0, 0, DISP_W, DISP_H, slots["bg"])

        if int(self.config["show_border"]):
            display.canvas.rect(
                pad, pad, DISP_W - 2 * pad, DISP_H - 2 * pad, slots["frame"]
            )

        if int(self.config["show_dots"]):
            for i in range(12):
                a = _angle(i, 12)
                cos_a, sin_a = math.cos(a), math.sin(a)
                tx = hw / abs(cos_a) if abs(cos_a) > 0.001 else 9999
                ty = hh / abs(sin_a) if abs(sin_a) > 0.001 else 9999
                t = min(tx, ty)
                dx = max(0, min(DISP_W - 1, int(cx + cos_a * t + 0.5)))
                dy = max(0, min(DISP_H - 1, int(cy + sin_a * t + 0.5)))
                display.canvas.pixel(dx, dy, slots["dots"])

        r = min(hw, hh)
        h12 = (h % 12) + m / 60.0
        _draw_hand(
            display.canvas,
            cx,
            cy,
            _angle(h12, 12),
            int(r * 0.5),
            slots["hour"],
            thick=True,
        )
        _draw_hand(
            display.canvas,
            cx,
            cy,
            _angle(m, 60),
            int(r * 0.8),
            slots["min"],
            thick=True,
        )
        if int(self.config["show_seconds"]):
            _draw_hand(
                display.canvas, cx, cy, _angle(s, 60), int(r * 0.9), slots["sec"]
            )

        display.canvas.pixel(cx, cy, slots["fg"])


ClockApp().run()
