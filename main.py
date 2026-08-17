import gc
import json
import os
import sys
import time

import microcontroller
import wifi

from matrixbox import components, updater
from matrixbox.app import session
from matrixbox.button import LONG_PRESS, SHORT_PRESS, button
from matrixbox.display import display
from matrixbox.fonts import MINI
from matrixbox.layout import Align, TextGrid
from matrixbox.net import server_socket, wifi_manager
from matrixbox.scroll import Scroller
from matrixbox.settings import settings
from matrixbox.theme import FAVICON_SVG
from matrixbox.web import router, url_decode

APPS_DIR = "/apps"


def installed_apps() -> list:
    def has_code(name):
        try:
            return "code.py" in os.listdir(f"{APPS_DIR}/{name}")
        except OSError:
            return False

    try:
        names = os.listdir(APPS_DIR)
    except OSError:
        names = []

    apps = sorted(name for name in names if "." not in name and has_code(name))

    return apps or ["No apps found"]


@router.route("/favicon.svg")
def favicon(request):
    return (200, {"Content-Type": "image/svg+xml"}, FAVICON_SVG)


@router.route("/")
def home(request):
    if session.instance is not None:
        app = session.instance
        body = app.render()

        return (
            200,
            {},
            components.page(app.title or session.current, body, exit_href="/exit"),
        )

    if "run" in request.params:
        name = request.params["run"]
        session.launch(name)
        body = (
            f'<meta http-equiv="refresh" content="1" />Starting <b>{name}</b>&hellip;'
        )

        return (200, {}, components.page("MatrixBOX", body))

    items = "".join(
        f'<div class="app-item"><span class="app-name">{name}</span>'
        f'<a class="btn btn-sm" href="/?run={name}">Run</a></div>'
        for name in installed_apps()
    )
    body = (
        '<div class="logo"><h1>Matrix<span class="brand-yellow">BOX</span></h1>'
        f"<p>{components.wifi_ip()}</p></div>" + components.card("Apps", items)
    )

    return (200, {}, components.page("MatrixBOX", body))


def _option(value, label, current):
    selected = " selected" if value == current else ""
    return f'<option value="{value}"{selected}>{label}</option>'


def _rotation_button(deg, current):
    deg_str = str(deg)
    is_on = "on" if deg == current else ""
    arrow_style = "" if deg == 0 else "transform:rotate(" + deg_str + "deg)"

    return (
        '<button type="button" id="rot_'
        + deg_str
        + '" class="'
        + is_on
        + '" onclick="setRotation('
        + deg_str
        + ')"><span style="display:inline-block;'
        + arrow_style
        + '">&#8593;</span><br>'
        + deg_str
        + "&deg;</button>"
    )


def _switch(setting_id, label, checked):
    checked_attr = " checked" if checked else ""

    return (
        '<div class="switch-row"><span>'
        + label
        + '</span><label class="switch"><input type="checkbox" id="'
        + setting_id
        + '"'
        + checked_attr
        + '><span class="slider"></span></label></div>'
    )


@router.route("/settings")
def settings_page(request):
    apps = installed_apps()
    autostart_options = '<option value="">None</option>' + "".join(
        _option(name, name, settings.get("autostart")) for name in apps
    )
    screensaver_options = '<option value="">None</option>' + "".join(
        _option(name, name, settings.get("screensaver")) for name in apps
    )
    rotation_buttons = "".join(
        _rotation_button(deg, settings["rotation"]) for deg in (0, 90, 180, 270)
    )

    ssid = settings["ssid"]
    password = settings["password"]
    email = settings["email"]
    wifi_power = str(settings["wifi_power"])
    repository_source = settings["repository_source"]
    repository_branch = settings["repository_branch"]
    width = str(settings["width"])
    height = str(settings["height"])
    tiles = str(settings["tiles"])
    current_version = updater.local_version("/") or "?"

    body = (
        components.card(
            "Wi-Fi",
            # Plain strings + "+", no f-strings here — see docs/ARCHITECTURE.md.
            '<label>Network name</label><input type="text" id="ssid" value="'
            + ssid
            + '">'
            '<label>Password</label><div style="position:relative">'
            '<input type="password" id="password" value="'
            + password
            + '" style="padding-right:40px">'
            '<button type="button" class="pw-toggle" title="Show/hide password" '
            'onclick="togglePassword(this)">\U0001f441</button></div>'
            "<script>"
            "function togglePassword(btn){"
            "var p=document.getElementById('password');"
            "var hidden=p.type==='password';"
            "p.type=hidden?'text':'password';"
            "btn.textContent=hidden?'\U0001f648':'\U0001f441';"
            "}"
            "</script>"
            '<label>Transmit power (dBm)</label><div class="range-wrap">'
            '<input type="range" id="wifi_power" min="7" max="20" step="1" value="'
            + wifi_power
            + '" oninput="document.getElementById(\'v_wifi_power\').textContent=this.value">'
            '<span class="range-val" id="v_wifi_power">' + wifi_power + "</span></div>",
        )
        + components.card(
            "Account",
            '<label>Email</label><input type="text" id="email" value="' + email + '">',
        )
        + components.card(
            "Display rotation", f'<div class="seg">{rotation_buttons}</div>'
        )
        + components.card(
            "Autostart",
            f'<label>App to launch on boot</label><select id="autostart">{autostart_options}</select>',
        )
        + components.card(
            "Screensaver",
            f'<label>App to launch after 60s idle</label><select id="screensaver">{screensaver_options}</select>',
        )
        + '<div class="card">'
        '<div class="section-title collapsible-header" id="adv_header" onclick="toggleAdvanced()">'
        'Advanced<span class="caret">&#9656;</span></div>'
        '<div id="adv_body" style="display:none">'
        "<label>Repository source (owner/repo)</label>"
        '<input type="text" id="repository_source" value="' + repository_source + '">'
        "<label>Repository branch</label>"
        '<input type="text" id="repository_branch" value="' + repository_branch + '">'
        "<label>Panel width (px)</label>"
        '<input type="text" id="width" value="' + width + '">'
        "<label>Panel height (px)</label>"
        '<input type="text" id="height" value="' + height + '">'
        "<label>Tiles</label>"
        '<input type="text" id="tiles" value="'
        + tiles
        + '">'
        + _switch("color_correct", "Swap G/B LED pins", settings.get("color_correct"))
        + '<p style="font-size:.75rem;color:var(--muted);margin-top:6px">'
        "Changing panel width, height, tiles, or color correction reboots"
        " the device.</p></div></div>"
        + components.card(
            "Updates",
            '<p style="font-size:.85rem;color:var(--muted);margin-bottom:10px">'
            "Current version: v" + current_version + "</p>"
            '<button type="button" class="btn btn-full" onclick="checkUpdates(this)">'
            "&#x1F504; Check for updates</button>"
            '<div id="updates_list" style="margin-top:12px"></div>',
        )
        + components.save_button()
        + """<script>
var selectedRotation = """
        + str(settings["rotation"])
        + """;
function setRotation(deg) {
  selectedRotation = deg;
  document.querySelectorAll("[id^=rot_]").forEach(function(b) {
    b.classList.toggle("on", b.id === "rot_" + deg);
  });
}
function toggleAdvanced() {
  var body = document.getElementById("adv_body");
  var open = body.style.display !== "none";
  body.style.display = open ? "none" : "block";
  document.getElementById("adv_header").classList.toggle("open", !open);
}
function save(b){
  var q = "ssid=" + encodeURIComponent(document.getElementById("ssid").value)
    + "&password=" + encodeURIComponent(document.getElementById("password").value)
    + "&email=" + encodeURIComponent(document.getElementById("email").value)
    + "&wifi_power=" + document.getElementById("wifi_power").value
    + "&rotation=" + selectedRotation
    + "&autostart=" + document.getElementById("autostart").value
    + "&screensaver=" + document.getElementById("screensaver").value
    + "&repository_source=" + encodeURIComponent(document.getElementById("repository_source").value)
    + "&repository_branch=" + encodeURIComponent(document.getElementById("repository_branch").value)
    + "&width=" + document.getElementById("width").value
    + "&height=" + document.getElementById("height").value
    + "&tiles=" + document.getElementById("tiles").value
    + "&color_correct=" + document.getElementById("color_correct").checked;
  fetch("/settings?" + q, {method:"POST"}).then(function(){ b.textContent = "✓ Saved"; });
}
function checkUpdates(b){
  b.textContent = "Checking…";
  fetch("/updates/check", {method:"POST"}).then(function(r){ return r.json(); })
    .then(function(d){ b.textContent = "Check for updates"; renderUpdates(d); })
    .catch(function(){ b.textContent = "Check failed"; });
}
function renderUpdates(d){
  var el = document.getElementById("updates_list");
  var keys = Object.keys(d);
  if (!keys.length) {
    el.innerHTML = '<p style="color:var(--muted);font-size:.85rem">Up to date</p>';
    return;
  }
  var h = "";
  keys.forEach(function(k){
    var label = k === "/" ? "System" : k;
    h += '<div style="display:flex;justify-content:space-between;align-items:center;'
      + 'padding:6px 0"><span>' + label + ' &rarr; v' + d[k] + '</span>'
      + '<button type="button" class="btn btn-sm" onclick="applyUpdate(\\''
      + k + '\\', this)">Update</button></div>';
  });
  el.innerHTML = h;
}
function applyUpdate(name, b){
  b.textContent = "Updating…";
  fetch("/updates/apply?target=" + encodeURIComponent(name), {method:"POST"})
    .then(function(r){ return r.json(); })
    .then(function(d){
      if (d.ok) {
        b.textContent = name === "/" ? "Rebooting…" : "Done";
      } else {
        b.textContent = "Failed";
      }
    })
    .catch(function(){ b.textContent = "Failed"; });
}
</script>"""
    )

    return (200, {}, components.page("Settings", body, exit_href="/"))


@router.route("/settings", method="POST")
def save_settings(request):
    p = request.params
    if "ssid" in p:
        settings["ssid"] = url_decode(p["ssid"])

    if "password" in p:
        settings["password"] = url_decode(p["password"])

    if "email" in p:
        settings["email"] = url_decode(p["email"])

    if "wifi_power" in p:
        settings["wifi_power"] = p["wifi_power"]

    if "rotation" in p:
        settings["rotation"] = p["rotation"]

    if "autostart" in p:
        settings["autostart"] = url_decode(p["autostart"])

    if "screensaver" in p:
        settings["screensaver"] = url_decode(p["screensaver"])

    if "repository_source" in p:
        settings["repository_source"] = url_decode(p["repository_source"])

    if "repository_branch" in p:
        settings["repository_branch"] = url_decode(p["repository_branch"])

    if "width" in p:
        settings["width"] = p["width"]

    if "height" in p:
        settings["height"] = p["height"]

    if "tiles" in p:
        settings["tiles"] = p["tiles"]

    if "color_correct" in p:
        settings["color_correct"] = p["color_correct"]

    settings.save()
    display.apply_settings()
    wifi_manager.apply_settings()

    return (200, {}, "ok")


@router.route("/updates/check", method="POST")
def check_updates(request):
    updates = updater.check_all(installed_apps())

    return (200, {"Content-Type": "application/json"}, json.dumps(updates))


@router.route("/updates/apply", method="POST")
def apply_update(request):
    target = request.params.get("target", "")
    try:
        if target == "/":
            updater.update_system()
        else:
            updater.update_app(target)

        ok = True
    except Exception as e:
        print(f"update failed for {target!r}: {e}")
        ok = False

    return (200, {"Content-Type": "application/json"}, json.dumps({"ok": ok}))


_selector_grid = TextGrid(display.canvas, font=MINI)


def _network_status() -> tuple:
    # (label, value) — label in white, value in yellow, see show_selector().
    if wifi.radio.connected:
        return "IP: ", str(wifi.radio.ipv4_address)

    if wifi.radio.ap_active:
        return "AP: ", wifi_manager.hotspot_ssid

    return "OFFLINE", ""


def show_status(text):
    display.canvas.fill(0)
    _selector_grid.line(text, 0, color=1, align=Align.LEFT, clear=False)
    display.refresh()


def show_selector(apps, index):
    display.canvas.fill(0)
    x = display.canvas.text("Matrix", 0, 0, font=MINI, color=5)
    display.canvas.text("BOX", x, 0, font=MINI, color=1)

    label, value = _network_status()
    y = _selector_grid.row_y(1)
    x = display.canvas.text(label, 0, y, font=MINI, color=5)
    display.canvas.text(value, x, y, font=MINI, color=1)

    _selector_grid.line("Select app:", 2, color=5, align=Align.LEFT, clear=False)
    _selector_grid.line(apps[index], -1, color=1, align=Align.LEFT, clear=False)
    display.refresh()


def _slide_to_next_app(old_name, new_name):
    row_height = _selector_grid.row_height
    y = _selector_grid.row_y(-1)

    old_canvas = display.new_canvas(display.width, row_height)
    old_canvas.text(old_name, 0, 0, font=MINI, color=1)
    new_canvas = display.new_canvas(display.width, row_height)
    new_canvas.text(new_name, 0, 0, font=MINI, color=1)

    speed = max(2, display.width // 16)  # ~16 frames to cross the row
    scroller = Scroller.transition(
        old_canvas, new_canvas, display.width, row_height, speed=speed
    )

    def draw():
        display.canvas.fill_rect(0, y, display.width, row_height, 0)
        scroller.draw(display.canvas, 0, y)
        display.refresh()

    scroller.run_to_completion(draw)


# Snapshot for run_app() to evict app-added modules only — see docs/ARCHITECTURE.md.
_kernel_modules = frozenset(sys.modules.keys())


def run_app(name):
    reserved = display.palette_allocator.reserved
    palette_backup = [display.palette[i] for i in range(reserved)]
    route_count = len(router.routes)
    session.current = name
    crashed = False

    try:
        display.canvas.fill(0)
        display.refresh()
        os.chdir(f"{APPS_DIR}/{name}")
        gc.collect()  # free whatever the selector/web UI left behind before the app's own imports need the room
        import code  # noqa: F401 -- the app itself; blocks until it exits
    except SystemExit:
        pass  # sys.exit() inside an app's loop is a normal way to leave
    except Exception as e:
        crashed = True
        print(f"app {name!r} crashed: {e}")
    finally:
        session.instance = None
        session.current = None
        # Drop anything the app added beyond the permanent routes.
        del router.routes[route_count:]
        for i, rgb in enumerate(palette_backup):
            display.palette[i] = rgb

        display.palette_allocator.reset()
        display.restore_root_canvas()
        for module_name in list(sys.modules):
            if module_name not in _kernel_modules:
                del sys.modules[module_name]

        os.chdir("/")
        gc.collect()

    if crashed:
        # A crashing autostart/screensaver app would otherwise relaunch
        # itself forever — disable whichever role pointed at it.
        disabled = False
        if settings.get("autostart") == name:
            settings["autostart"] = ""
            disabled = True

        if settings.get("screensaver") == name:
            settings["screensaver"] = ""
            disabled = True

        if disabled:
            settings.save()
            print(f"app {name!r} crashed — disabled as autostart/screensaver")


def main():
    show_status(f"Connecting: {settings['ssid'] or '(no ssid set)'}")
    wifi_manager.connect()

    apps = installed_apps()
    selected = 0
    show_selector(apps, selected)
    screensaver_at = time.monotonic()
    autostart_done = False  # fires once per boot, not once per return to idle

    while True:
        wifi_manager.maintain()
        router.listen(server_socket)

        if updater.reboot_pending or display.reboot_pending:
            # The response for the request that triggered this has already
            # been sent — router.listen() is synchronous — see docs/ARCHITECTURE.md.
            time.sleep(0.5)
            microcontroller.reset()

        press = button.poll()
        if press == SHORT_PRESS:
            next_selected = (selected + 1) % len(apps)
            _slide_to_next_app(apps[selected], apps[next_selected])
            selected = next_selected
            screensaver_at = time.monotonic()
        elif press == LONG_PRESS:
            session.launch(apps[selected])

        autostart = settings.get("autostart")
        if autostart and not autostart_done and not session.requested:
            session.launch(autostart)
            autostart_done = True

        if session.requested:
            name = session.requested
            session.requested = None
            run_app(name)
            apps = installed_apps()
            selected = 0
            show_selector(apps, selected)
            screensaver_at = time.monotonic()

        screensaver_app = settings.get("screensaver")
        if screensaver_app and time.monotonic() - screensaver_at > 60:
            session.launch(screensaver_app)

        time.sleep(0.01)


main()
