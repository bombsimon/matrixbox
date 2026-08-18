import math
import random
import time

from matrixbox.app import App
from matrixbox.display import display

DISP_W = display.width
DISP_H = display.height

EFFECTS = ("aquarium", "fireworks", "rain", "space", "starcloud")


def _sp(canvas, x, y, color):
    if 0 <= x < canvas.width and 0 <= y < canvas.height:
        canvas.pixel(x, y, color)


# -- aquarium --

_FISH_KINDS = ("clown", "tang", "blue", "pink")


class _Fish:
    def __init__(self, w, sand_top, slots, allowed_kinds):
        self.facing = random.choice((-1, 1))
        self.x = float(3 if self.facing == 1 else w - 4)
        self.y = float(random.randint(2, min(sand_top) - 4))
        self.speed = random.uniform(0.3, 0.8)
        self.phase = random.uniform(0, 6.28)
        self.bob_speed = random.uniform(0.05, 0.1)
        self.bob_amp = random.uniform(0.3, 0.8)
        self.paused = False
        self.target = None
        kind = random.choice(allowed_kinds or _FISH_KINDS)
        # Body/stripe/size per kind — size 1 = bigger 5-wide fish, 0 = small.
        body_stripe_size = {
            "clown": (slots["clown"], slots["shine"], 1),
            "tang": (slots["gold"], slots["shine"], 1),
            "blue": (slots["blue_fish"], slots["gold"], 0),
            "pink": (slots["pink_fish"], slots["shine"], 0),
        }
        self.body, self.stripe, self.sz = body_stripe_size[kind]

    def update(self, w, sand_top, food_list):
        if food_list and self.target is None:
            best_d, best_f = 9999, None
            for fd in food_list:
                d = abs(fd.x - self.x) + abs(fd.y - self.y)
                if d < best_d:
                    best_d, best_f = d, fd

            if best_f and best_d < 60:
                self.target = best_f

        if self.target is not None:
            self.paused = False
            dx = self.target.x - self.x
            dy = self.target.y - self.y
            if dx > 1:
                self.facing = 1
            elif dx < -1:
                self.facing = -1

            self.x += self.speed * 1.5 * (1 if dx > 0 else -1)
            if abs(dy) > 0.5:
                self.y += 0.4 * (1 if dy > 0 else -1)

            if abs(dx) < 3 and abs(dy) < 3:
                if self.target in food_list:
                    food_list.remove(self.target)

                self.target = None
        else:
            r = random.random()
            if r < 0.005:
                self.facing = -self.facing
            elif r < 0.012:
                self.paused = not self.paused

            if not self.paused:
                self.x += self.speed * self.facing

            self.phase += self.bob_speed
            self.y += math.sin(self.phase) * self.bob_amp * 0.3

        if self.y < 1:
            self.y = 1.0

        ix = max(0, min(int(self.x), w - 1))
        max_y = sand_top[ix] - 3
        if self.y > max_y:
            self.y = float(max_y)

        margin = 3 if self.sz == 0 else 4
        if self.x >= w - margin:
            self.x = float(w - margin)
            self.facing = -1
        elif self.x <= margin:
            self.x = float(margin)
            self.facing = 1

    def draw(self, canvas, shine_slot):
        ix, iy, f = int(self.x), int(self.y), self.facing
        if self.sz == 1:
            _sp(canvas, ix, iy - 1, self.body)
            _sp(canvas, ix - 1 * f, iy, self.body)
            _sp(canvas, ix, iy, self.body)
            _sp(canvas, ix + 1 * f, iy, self.stripe)
            _sp(canvas, ix + 2 * f, iy, self.body)
            _sp(canvas, ix, iy + 1, self.body)
            _sp(canvas, ix - 2 * f, iy - 1, self.body)
            _sp(canvas, ix - 2 * f, iy, self.body)
            _sp(canvas, ix - 2 * f, iy + 1, self.body)
            _sp(canvas, ix + 2 * f, iy - 1, shine_slot)
        else:
            _sp(canvas, ix, iy, self.body)
            _sp(canvas, ix + 1 * f, iy, self.stripe)
            _sp(canvas, ix - 1 * f, iy - 1, self.body)
            _sp(canvas, ix - 1 * f, iy, self.body)
            _sp(canvas, ix - 1 * f, iy + 1, self.body)
            _sp(canvas, ix + 1 * f, iy - 1, shine_slot)


class _Bubble:
    def __init__(self, w, sand_top):
        sx = random.randint(3, w - 3)
        self.x = float(sx)
        self.y = float(sand_top[sx] - 1)
        r = random.random()
        self.size = 0 if r < 0.55 else (1 if r < 0.88 else 2)
        self.vy = {
            0: random.uniform(-0.45, -0.25),
            1: random.uniform(-0.3, -0.15),
            2: random.uniform(-0.2, -0.1),
        }[self.size]
        self.wobble = random.uniform(0.03, 0.08)
        self.phase = random.uniform(0, 6.28)

    def update(self):
        self.y += self.vy
        self.phase += self.wobble
        self.x += math.sin(self.phase) * 0.2

    def alive(self):
        return self.y > -2

    def draw(self, canvas, slots):
        ix, iy = int(self.x), int(self.y)
        if self.size == 0:
            _sp(canvas, ix, iy, slots["bubble"])
        elif self.size == 1:
            _sp(canvas, ix, iy, slots["bubble"])
            _sp(canvas, ix, iy - 1, slots["shine"])
        else:
            _sp(canvas, ix, iy, slots["bubble"])
            _sp(canvas, ix + 1, iy, slots["bubble"])
            _sp(canvas, ix, iy - 1, slots["bubble"])
            _sp(canvas, ix + 1, iy - 1, slots["shine"])


class _Seaweed:
    def __init__(self, x):
        self.x = x
        self.h = random.randint(4, 9)
        self.phase = random.uniform(0, 6.28)
        self.speed = random.uniform(0.02, 0.05)

    def draw(self, canvas, w, sand_top, slot):
        self.phase += self.speed
        base_y = sand_top[max(0, min(self.x, w - 1))] - 1
        for i in range(self.h):
            py = base_y - i
            sway = math.sin(self.phase + i * 0.5) * (i * 0.25)
            px = int(self.x + sway)
            _sp(canvas, px, py, slot)


class _Food:
    def __init__(self, w, sand_top):
        self.x = float(random.randint(5, w - 5))
        self.y = 0.0
        self.vy = random.uniform(0.15, 0.3)
        self.wobble = random.uniform(0.03, 0.06)
        self.phase = random.uniform(0, 6.28)

    def update(self, w, sand_top):
        self.y += self.vy
        self.phase += self.wobble
        self.x += math.sin(self.phase) * 0.15
        ix = max(0, min(int(self.x), w - 1))
        if self.y >= sand_top[ix] - 1:
            self.y = float(sand_top[ix] - 1)

    def alive(self, w, sand_top):
        ix = max(0, min(int(self.x), w - 1))
        return self.y < sand_top[ix] - 0.5

    def draw(self, canvas, slot):
        _sp(canvas, int(self.x), int(self.y), slot)


# -- effect settings fragments --

_AQUARIUM_FRAGMENT = """<div class="card">
<div class="section-title">Fish</div>
<label>Fish count</label>
<div class="range-wrap"><input type="range" id="max_fish" min="0" max="10" oninput="rangeLive(this)" onchange="post(this.id+'='+this.value)"><span class="range-val" id="v_max_fish"></span></div>
<label>Spawn rate</label>
<div class="seg" id="seg_fish_rate">
<button data-v="1" onclick="setSeg('seg_fish_rate',1);post('fish_rate=1')">Slow</button>
<button data-v="2" onclick="setSeg('seg_fish_rate',2);post('fish_rate=2')">Medium</button>
<button data-v="3" onclick="setSeg('seg_fish_rate',3);post('fish_rate=3')">Fast</button>
</div>
</div>
<div class="card">
<div class="section-title">Bubbles</div>
<div class="switch-row"><span>Enable bubbles</span><label class="switch"><input type="checkbox" id="bubbles" onchange="post('bubbles='+this.checked)"><span class="slider"></span></label></div>
<label>Max bubbles</label>
<div class="range-wrap"><input type="range" id="max_bubbles" min="0" max="12" oninput="rangeLive(this)" onchange="post(this.id+'='+this.value)"><span class="range-val" id="v_max_bubbles"></span></div>
</div>
<div class="card">
<div class="section-title">Lighting</div>
<div class="switch-row"><span>Caustic light effect</span><label class="switch"><input type="checkbox" id="caustics" onchange="post('caustics='+this.checked)"><span class="slider"></span></label></div>
</div>
<script>
loadRangeVals(["max_fish","max_bubbles"]);
loadChecks(["bubbles","caustics"]);
loadSeg("seg_fish_rate","fish_rate");
</script>"""

_FIREWORKS_FRAGMENT = """<div class="card">
<div class="section-title">Fireworks</div>
<label>Particles per burst</label>
<div class="range-wrap"><input type="range" id="fw_particles" min="20" max="150" step="5" oninput="rangeLive(this)" onchange="post(this.id+'='+this.value)"><span class="range-val" id="v_fw_particles"></span></div>
<label>Max simultaneous</label>
<div class="range-wrap"><input type="range" id="fw_max_active" min="1" max="8" oninput="rangeLive(this)" onchange="post(this.id+'='+this.value)"><span class="range-val" id="v_fw_max_active"></span></div>
<label>Gravity</label>
<div class="range-wrap"><input type="range" id="fw_gravity" min="0" max="30" oninput="rangeLive(this)" onchange="post(this.id+'='+this.value)"><span class="range-val" id="v_fw_gravity"></span></div>
<label>Speed</label>
<div class="range-wrap"><input type="range" id="fw_speed" min="5" max="50" oninput="rangeLive(this)" onchange="post(this.id+'='+this.value)"><span class="range-val" id="v_fw_speed"></span></div>
<label>Lifetime</label>
<div class="range-wrap"><input type="range" id="fw_lifetime" min="10" max="80" step="5" oninput="rangeLive(this)" onchange="post(this.id+'='+this.value)"><span class="range-val" id="v_fw_lifetime"></span></div>
<label>Launch delay</label>
<div class="range-wrap"><input type="range" id="fw_delay" min="1" max="30" oninput="rangeLive(this)" onchange="post(this.id+'='+this.value)"><span class="range-val" id="v_fw_delay"></span></div>
</div>
<script>
loadRangeVals(["fw_particles","fw_max_active","fw_gravity","fw_speed","fw_lifetime","fw_delay"]);
</script>"""

_SETTINGS_FRAGMENTS = {
    "aquarium": _AQUARIUM_FRAGMENT,
    "fireworks": _FIREWORKS_FRAGMENT,
}


class ScreensaverApp(App):
    title = "Screensaver"
    default_settings = {
        "effect": "starcloud",
        "max_fish": 5,
        "fish_types": "clown,tang,blue,pink",
        "bubbles": True,
        "max_bubbles": 6,
        "caustics": True,
        "bubble_rate": 2,
        "fish_rate": 2,
        "fw_particles": 75,
        "fw_max_active": 3,
        "fw_gravity": 10,
        "fw_speed": 20,
        "fw_lifetime": 30,
        "fw_delay": 10,
    }

    def on_start(self):
        with open("template.html") as f:
            self.html_template = f.read()

        self._load_effect(self.config["effect"])

    def render(self) -> str:
        effect = self.config["effect"]
        options = "".join(
            '<option value="'
            + name
            + '"'
            + (" selected" if name == effect else "")
            + ">"
            + name[0].upper()
            + name[1:]
            + "</option>"
            for name in EFFECTS
        )

        return self.html_template.replace("__OPTIONS__", options).replace(
            "__FRAGMENT__", _SETTINGS_FRAGMENTS.get(effect, "")
        )

    def on_settings_saved(self, values):
        if "effect" in values and self.config["effect"] in EFFECTS:
            self._load_effect(self.config["effect"])

    def on_button(self):
        if self.config["effect"] == "aquarium":
            for _ in range(random.randint(2, 4)):
                self._aq_food.append(_Food(DISP_W, self._aq_sand_top))

    def on_update(self, now):
        self._update(now)
        display.refresh()

    def _load_effect(self, name):
        if name not in EFFECTS:
            name = "starcloud"

        display.palette_allocator.reset()
        display.canvas.fill(0)
        getattr(self, "_init_" + name)()
        self._update = getattr(self, "_update_" + name)

    # -- starcloud --

    def _init_starcloud(self):
        self._sc_slots = [
            display.palette_allocator.allocate(c)
            for c in ((200, 200, 255), (255, 220, 120), (140, 255, 200))
        ]
        cx, cy = DISP_W // 2, DISP_H // 2
        self._sc_stars = []
        for _ in range(10):
            angle = random.uniform(0, 2 * math.pi)
            radius = random.uniform(5, min(cx, cy) - 2)
            speed = random.uniform(0.01, 0.05)
            color = random.choice(self._sc_slots)
            self._sc_stars.append([angle, radius, speed, color])

    def _update_starcloud(self, now):
        cx, cy = DISP_W // 2, DISP_H // 2
        display.canvas.fill(0)
        new_stars = []
        for angle, radius, speed, color in self._sc_stars:
            x = int(cx + math.cos(angle) * radius)
            y = int(cy + math.sin(angle) * radius)
            _sp(display.canvas, x, y, color)
            angle += speed
            radius += 0.05
            if radius < min(cx, cy):
                new_stars.append([angle, radius, speed, color])
            else:
                new_stars.append(
                    [
                        random.uniform(0, 2 * math.pi),
                        5,
                        random.uniform(0.01, 0.05),
                        random.choice(self._sc_slots),
                    ]
                )

        self._sc_stars = new_stars

    # -- rain --

    def _init_rain(self):
        s = {
            "dim": display.palette_allocator.allocate((20, 40, 80)),
            "mid": display.palette_allocator.allocate((40, 70, 130)),
            "bright": display.palette_allocator.allocate((90, 130, 200)),
            "splash_tip": display.palette_allocator.allocate((160, 200, 255)),
            "cloud_dim": display.palette_allocator.allocate((6, 10, 25)),
            "cloud_bright": display.palette_allocator.allocate((10, 20, 50)),
            "splash_bright": display.palette_allocator.allocate((200, 220, 255)),
        }
        self._rain_slots = s

        drops = []
        for _ in range(55):
            spd = random.uniform(0.5, 2.5)
            col = s["dim"] if spd < 1.0 else (s["mid"] if spd < 1.7 else s["bright"])
            ln = 1 if spd < 1.0 else (2 if spd < 1.7 else 3)
            drops.append(
                [
                    random.randint(0, DISP_W - 1),
                    random.uniform(-DISP_H, DISP_H - 1),
                    spd,
                    ln,
                    col,
                ]
            )

        self._rain_drops = drops
        self._rain_splashes = []
        self._rain_clouds = [
            (x, y, random.choice((s["cloud_dim"], s["cloud_dim"], s["cloud_bright"])))
            for x in range(DISP_W)
            for y in range(4)
            if random.random() < 0.35
        ]
        self._rain_frame = 0

    def _update_rain(self, now):
        s = self._rain_slots
        display.canvas.fill(0)

        for cx, cy, cc in self._rain_clouds:
            c = cc
            if self._rain_frame % 12 == 0 and random.random() < 0.08:
                c = s["cloud_bright"] if cc == s["cloud_dim"] else s["cloud_dim"]

            _sp(display.canvas, cx, cy, c)

        for d in self._rain_drops:
            d[1] += d[2]
            for t in range(d[3]):
                py = int(d[1]) - t
                _sp(display.canvas, d[0], py, d[4])

            ty = int(d[1])
            tip = s["splash_tip"] if d[4] == s["bright"] else s["splash_bright"]
            _sp(display.canvas, d[0], ty, tip)

            if d[1] >= DISP_H:
                if d[2] > 1.2:
                    self._rain_splashes.append(
                        [d[0], DISP_H - 1, 0, random.randint(3, 5)]
                    )

                d[0] = random.randint(0, DISP_W - 1)
                d[1] = random.uniform(-20, -1)
                d[2] = random.uniform(0.5, 2.5)
                d[4] = (
                    s["dim"]
                    if d[2] < 1.0
                    else (s["mid"] if d[2] < 1.7 else s["bright"])
                )
                d[3] = 1 if d[2] < 1.0 else (2 if d[2] < 1.7 else 3)

        alive = []
        for sh in self._rain_splashes:
            life, mx = sh[2], sh[3]
            spread = life + 1
            bright = s["splash_bright"] if life < mx // 2 else s["mid"]
            for dx in range(-spread, spread + 1):
                sy = sh[1] - abs(dx)
                sx = sh[0] + dx
                _sp(display.canvas, sx, sy, bright)

            sh[2] += 1
            if sh[2] < sh[3]:
                alive.append(sh)

        self._rain_splashes = alive
        self._rain_frame += 1

    # -- fireworks --

    def _init_fireworks(self):
        self._fw_slots = [
            display.palette_allocator.allocate(c)
            for c in (
                (255, 60, 60),
                (60, 255, 90),
                (80, 140, 255),
                (255, 220, 60),
                (255, 130, 220),
                (100, 230, 230),
                (255, 160, 60),
                (200, 120, 255),
            )
        ]
        self._fw_fireworks = []
        self._fw_last = 0.0

    def _spawn_firework(self, x, y):
        particles = []
        num = int(self.config["fw_particles"])
        colors = [random.choice(self._fw_slots) for _ in range(3)]
        spd = int(self.config["fw_speed"]) / 10.0
        lt = int(self.config["fw_lifetime"])
        for _ in range(num):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(0.3, spd)
            particles.append(
                {
                    "x": x,
                    "y": y,
                    "vx": speed * math.cos(angle),
                    "vy": speed * math.sin(angle),
                    "lifetime": random.randint(lt // 2, lt),
                    "color": random.choice(colors),
                }
            )

        return particles

    def _update_fireworks(self, now):
        display.canvas.fill(0)

        delay = int(self.config["fw_delay"]) / 10.0
        if now - self._fw_last > delay and len(self._fw_fireworks) < int(
            self.config["fw_max_active"]
        ):
            x = random.randint(10, DISP_W - 10)
            y = random.randint(DISP_H // 4, DISP_H // 2)
            self._fw_fireworks.append(self._spawn_firework(x, y))
            self._fw_last = now

        grav = int(self.config["fw_gravity"]) / 100.0
        new_fireworks = []
        for firework in self._fw_fireworks:
            active = []
            for p in firework:
                p["x"] += p["vx"]
                p["y"] += p["vy"]
                p["vy"] += grav
                p["lifetime"] -= 1
                if p["lifetime"] > 0:
                    _sp(display.canvas, int(p["x"]), int(p["y"]), p["color"])
                    active.append(p)

            if active:
                new_fireworks.append(active)

        self._fw_fireworks = new_fireworks

    # -- space --

    def _init_space(self):
        s = {
            "star_dim": display.palette_allocator.allocate((40, 40, 60)),
            "star_mid": display.palette_allocator.allocate((100, 100, 130)),
            "star_bright": display.palette_allocator.allocate((180, 180, 220)),
            "star_core": display.palette_allocator.allocate((255, 255, 255)),
            "mars": display.palette_allocator.allocate((180, 80, 40)),
            "neptune": display.palette_allocator.allocate((60, 100, 180)),
            "saturn": display.palette_allocator.allocate((200, 170, 100)),
            "green_planet": display.palette_allocator.allocate((100, 180, 100)),
            "shadow": display.palette_allocator.allocate((80, 60, 50)),
            "ring": display.palette_allocator.allocate((200, 160, 60)),
            "comet": display.palette_allocator.allocate((100, 140, 200)),
            "trail": display.palette_allocator.allocate((50, 70, 120)),
        }
        self._sp_slots = s
        self._sp_stars = [self._sp_new_star() for _ in range(20)]
        self._sp_planets = []
        self._sp_planet_timer = time.monotonic() + random.uniform(4, 8)
        self._sp_comets = []
        self._sp_comet_timer = time.monotonic() + random.uniform(6, 12)
        self._sp_frame = 0

    def _sp_new_star(self):
        return [
            random.randint(-DISP_W, DISP_W),
            random.randint(-DISP_H, DISP_H),
            random.randint(20, 200),
        ]

    def _sp_spawn_planet(self):
        s = self._sp_slots
        side = random.choice((-1, 1))
        return {
            "x": side * random.randint(DISP_W // 4, DISP_W),
            "y": random.randint(-DISP_H // 3, DISP_H // 3),
            "z": 240,
            "r": random.randint(3, 6),
            "col": random.choice(
                (s["mars"], s["neptune"], s["saturn"], s["green_planet"])
            ),
            "ring": random.random() < 0.35,
        }

    def _sp_draw_circle(self, px, py, r, col, shadow_col):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r:
                    c = shadow_col if dx > r // 2 else col
                    _sp(display.canvas, px + dx, py + dy, c)

    def _sp_draw_ring(self, px, py, r, col):
        ring_r = r + 2
        for ang in range(36):
            a = ang * 0.1745
            rx = int(px + math.cos(a) * ring_r)
            ry = int(py + math.sin(a) * (ring_r // 3))
            _sp(display.canvas, rx, ry, col)

    def _sp_spawn_comet(self):
        s = self._sp_slots
        if random.random() < 0.5:
            x, vx = -5, random.uniform(1.5, 3.0)
        else:
            x, vx = DISP_W + 5, random.uniform(-3.0, -1.5)

        return {
            "x": float(x),
            "y": float(random.randint(2, DISP_H // 2)),
            "vx": vx,
            "vy": random.uniform(0.2, 0.6),
            "life": 0,
            "col": s["comet"],
            "trail": [],
        }

    def _update_space(self, now):
        s = self._sp_slots
        cx, cy, focal = DISP_W // 2, DISP_H // 2, 64
        display.canvas.fill(0)

        for star in self._sp_stars:
            star[2] -= 3
            if star[2] <= 1:
                star[0], star[1], star[2] = self._sp_new_star()

            px = int(cx + (star[0] * focal) // star[2])
            py = int(cy + (star[1] * focal) // star[2])
            if 0 <= px < DISP_W and 0 <= py < DISP_H:
                depth_ratio = (200 - star[2]) * 10 // 200
                col = (
                    s["star_dim"]
                    if depth_ratio < 4
                    else (s["star_mid"] if depth_ratio < 7 else s["star_bright"])
                )
                if depth_ratio > 8:
                    col = s["star_core"]

                _sp(display.canvas, px, py, col)
            else:
                star[0], star[1], star[2] = self._sp_new_star()

        if now > self._sp_planet_timer and len(self._sp_planets) < 2:
            self._sp_planets.append(self._sp_spawn_planet())
            self._sp_planet_timer = now + random.uniform(8, 15)

        alive_planets = []
        for p in self._sp_planets:
            p["z"] -= 1
            if p["z"] < 5:
                continue

            px = int(cx + (p["x"] * focal) // p["z"])
            py = int(cy + (p["y"] * focal) // p["z"])
            vis_r = int(max(1, (p["r"] * focal) // p["z"]))
            if -vis_r < px < DISP_W + vis_r and -vis_r < py < DISP_H + vis_r:
                self._sp_draw_circle(px, py, min(vis_r, 8), p["col"], s["shadow"])
                if p["ring"] and vis_r > 2:
                    self._sp_draw_ring(px, py, min(vis_r, 8), s["ring"])

                alive_planets.append(p)

        self._sp_planets = alive_planets

        if now > self._sp_comet_timer and len(self._sp_comets) < 1:
            self._sp_comets.append(self._sp_spawn_comet())
            self._sp_comet_timer = now + random.uniform(8, 16)

        alive_comets = []
        for c in self._sp_comets:
            c["x"] += c["vx"]
            c["y"] += c["vy"]
            c["life"] += 1
            c["trail"].append((int(c["x"]), int(c["y"])))
            if len(c["trail"]) > 12:
                c["trail"].pop(0)

            for tx, ty in c["trail"]:
                _sp(display.canvas, tx, ty, s["trail"])

            _sp(display.canvas, int(c["x"]), int(c["y"]), s["star_core"])

            if -20 < c["x"] < DISP_W + 20 and -10 < c["y"] < DISP_H + 10:
                alive_comets.append(c)

        self._sp_comets = alive_comets
        self._sp_frame += 1

    # -- aquarium --

    def _init_aquarium(self):
        self._aq_slots = {
            "water": display.palette_allocator.allocate((8, 30, 60)),
            "bubble": display.palette_allocator.allocate((200, 200, 220)),
            "shine": display.palette_allocator.allocate((255, 255, 255)),
            "clown": display.palette_allocator.allocate((255, 100, 20)),
            "weed": display.palette_allocator.allocate((0, 160, 60)),
            "gold": display.palette_allocator.allocate((255, 220, 40)),
            "blue_fish": display.palette_allocator.allocate((80, 80, 220)),
            "pink_fish": display.palette_allocator.allocate((220, 60, 120)),
            "sand": display.palette_allocator.allocate((140, 90, 50)),
            "sand_hi": display.palette_allocator.allocate((180, 140, 80)),
            "dark": display.palette_allocator.allocate((100, 60, 35)),
            "coral": display.palette_allocator.allocate((200, 80, 80)),
        }

        self._aq_sand_top = [0] * DISP_W
        for x in range(DISP_W):
            h = 2.5 + math.sin(x * 0.12) * 1.2 + math.sin(x * 0.28 + 1.5) * 0.8
            self._aq_sand_top[x] = DISP_H - int(h)

        self._aq_fish = []
        self._aq_fish_timer = 0.0
        self._aq_bubbles = []
        self._aq_bubble_timer = 0.0
        self._aq_food = []
        self._aq_weeds = [_Seaweed(random.randint(3, DISP_W - 3)) for _ in range(5)]
        self._aq_rocks = [
            (rx, self._aq_sand_top[rx] - 1)
            for rx in (random.randint(2, DISP_W - 3) for _ in range(4))
        ]
        self._aq_corals = [random.randint(5, DISP_W - 5) for _ in range(3)]
        self._aq_chest_x = DISP_W // 3 + random.randint(-5, 5)
        self._aq_frame = 0

    def _aq_draw_chest(self):
        s = self._aq_slots
        cx = max(0, min(self._aq_chest_x, DISP_W - 1))
        by = self._aq_sand_top[cx]
        for i in range(6):
            _sp(display.canvas, cx + i, by - 1, s["dark"])

        for i, c in enumerate(
            (s["dark"], s["sand_hi"], s["gold"], s["gold"], s["sand_hi"], s["dark"])
        ):
            _sp(display.canvas, cx + i, by - 2, c)
            _sp(display.canvas, cx + i, by - 3, c)

        for i in range(6):
            _sp(display.canvas, cx + i, by - 4, s["dark"])

        for i, c in enumerate(
            (s["dark"], s["dark"], s["sand_hi"], s["sand_hi"], s["dark"], s["dark"])
        ):
            _sp(display.canvas, cx + i, by - 5, c)

        for i in (1, 2, 3, 4):
            _sp(display.canvas, cx + i, by - 6, s["dark"])

    def _update_aquarium(self, now):
        s = self._aq_slots
        display.canvas.fill(0)

        if self.config["caustics"]:
            for px in range(DISP_W):
                v = int(math.sin(self._aq_frame * 0.08 + px * 0.4) * 2)
                if v > 0:
                    _sp(display.canvas, px, v, s["water"])
                    _sp(display.canvas, px, v + 1, s["water"])

        for px in range(DISP_W):
            top = self._aq_sand_top[px]
            display.canvas.fill_rect(px, top, 1, DISP_H - top, s["sand_hi"])
            _sp(display.canvas, px, top, s["sand"])

        for rx, ry in self._aq_rocks:
            _sp(display.canvas, rx, ry, s["dark"])
            _sp(display.canvas, rx + 1, ry, s["dark"])
            _sp(display.canvas, rx, ry - 1, s["dark"])

        for ccx in self._aq_corals:
            cy = self._aq_sand_top[max(0, min(ccx, DISP_W - 1))] - 1
            _sp(display.canvas, ccx, cy, s["coral"])
            _sp(display.canvas, ccx + 1, cy, s["coral"])
            _sp(display.canvas, ccx, cy - 1, s["coral"])
            _sp(display.canvas, ccx - 1, cy - 1, s["coral"])

        self._aq_draw_chest()

        for weed in self._aq_weeds:
            weed.draw(display.canvas, DISP_W, self._aq_sand_top, s["weed"])

        fish_rate = int(self.config["fish_rate"])
        delay_lo, delay_hi = 5.5 - fish_rate * 1.5, 9.0 - fish_rate * 2.0
        max_fish = int(self.config["max_fish"])
        if now > self._aq_fish_timer and len(self._aq_fish) < max_fish and max_fish > 0:
            allowed = [
                k.strip()
                for k in self.config["fish_types"].split(",")
                if k.strip() in _FISH_KINDS
            ]
            self._aq_fish.append(_Fish(DISP_W, self._aq_sand_top, s, allowed))
            self._aq_fish_timer = now + random.uniform(delay_lo, delay_hi)

        for fish in self._aq_fish:
            fish.update(DISP_W, self._aq_sand_top, self._aq_food)
            fish.draw(display.canvas, s["shine"])

        max_bub = int(self.config["max_bubbles"])
        bub_rate = int(self.config["bubble_rate"])
        b_lo, b_hi = 3.5 - bub_rate * 1.0, 5.5 - bub_rate * 1.2
        if (
            self.config["bubbles"]
            and now > self._aq_bubble_timer
            and len(self._aq_bubbles) < max_bub
            and max_bub > 0
        ):
            self._aq_bubbles.append(_Bubble(DISP_W, self._aq_sand_top))
            self._aq_bubble_timer = now + random.uniform(b_lo, b_hi)

        alive_bubbles = []
        for bubble in self._aq_bubbles:
            bubble.update()
            bubble.draw(display.canvas, s)
            if bubble.alive():
                alive_bubbles.append(bubble)

        self._aq_bubbles = alive_bubbles

        alive_food = []
        for food in self._aq_food:
            food.update(DISP_W, self._aq_sand_top)
            food.draw(display.canvas, s["gold"])
            if food.alive(DISP_W, self._aq_sand_top):
                alive_food.append(food)

        self._aq_food = alive_food
        self._aq_frame += 1


ScreensaverApp().run()
