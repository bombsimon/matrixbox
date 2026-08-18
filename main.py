import gc
import json
import os
import sys
import time

import microcontroller
import wifi

from matrixbox import components, stats, updater
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


def _installed_app_names() -> list:
    def has_code(name):
        try:
            return "code.py" in os.listdir(f"{APPS_DIR}/{name}")
        except OSError:
            return False

    try:
        names = os.listdir(APPS_DIR)
    except OSError:
        names = []

    return sorted(name for name in names if "." not in name and has_code(name))


def installed_apps() -> list:
    # Used by the physical button-cycling selector, which needs a non-empty
    # list — the app list page uses _installed_app_names() directly instead,
    # since a literal "No apps found" would otherwise get treated as an
    # app name — see docs/ARCHITECTURE.md.
    return _installed_app_names() or ["No apps found"]


def _format_size(n: int) -> str:
    if n < 1024:
        return str(n) + " B"

    if n < 1024 * 1024:
        return str(round(n / 1024, 1)) + " KB"

    return str(round(n / (1024 * 1024), 1)) + " MB"


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

    names = _installed_app_names()

    items = "".join(
        '<div class="app-item" id="app-' + name + '" data-name="' + name + '">'
        '<div class="app-item-main"><span class="app-name">'
        + name
        + '</span><span class="app-meta" id="meta-'
        + name
        + '"></span></div>'
        '<div class="app-actions" id="actions-' + name + '">'
        '<a class="btn btn-sm" href="/?run=' + name + '">Run</a>'
        "</div></div>"
        for name in names
    )
    if not items:
        items = '<p style="color:var(--muted);font-size:.85rem">No apps installed</p>'

    flash_used, flash_total = stats.flash_bytes()
    flash_line = (
        '<p class="flash-stat" id="flashStat">'
        + _format_size(flash_used)
        + " used of "
        + _format_size(flash_total)
        + " flash</p>"
    )

    body = (
        '<div class="logo"><h1>Matrix<span class="brand-yellow">BOX</span></h1>'
        f"<p>{components.wifi_ip()}</p></div>"
        + components.card(
            "Apps",
            flash_line
            + '<div id="appList">'
            + items
            + "</div>"
            + '<p class="catalog-status" id="catalogStatus"></p>',
        )
        + """<script>
function fmtSize(n){
  if(n<1024) return n+" B";
  if(n<1024*1024) return Math.round(n/1024*10)/10+" KB";
  return Math.round(n/1024/1024*10)/10+" MB";
}
function appRow(name){
  return '<div class="app-item" id="app-'+name+'" data-name="'+name+'">'
    +'<div class="app-item-main"><span class="app-name">'+name+'</span>'
    +'<span class="app-meta" id="meta-'+name+'"></span></div>'
    +'<div class="app-actions" id="actions-'+name+'"></div></div>';
}
function installBtn(name){
  return '<button class="btn btn-sm btn-save" onclick="doInstall(\\''+name+'\\',this)">Install</button>';
}
function renderActions(entry){
  var el=document.getElementById("actions-"+entry.name);
  if(!el) return;
  var h="";
  if(entry.installed){
    h+='<a class="btn btn-sm" href="/?run='+entry.name+'">Run</a>';
    if(entry.has_update)
      h+='<button class="btn btn-sm btn-save" onclick="doUpdate(\\''+entry.name+'\\',this)">Update</button>';
    h+='<button class="btn btn-sm btn-danger" onclick="doUninstall(\\''+entry.name+'\\',this)">Uninstall</button>';
  }else{
    h+=installBtn(entry.name);
  }
  el.innerHTML=h;
}
function renderMeta(entry){
  var el=document.getElementById("meta-"+entry.name);
  if(!el) return;
  var parts=[];
  if(entry.installed) parts.push("v"+(entry.local_version||"?"));
  if(entry.has_update) parts.push("&rarr; v"+entry.remote_version);
  else if(!entry.installed && entry.remote_version) parts.push("v"+entry.remote_version+" available");
  var size=entry.installed?entry.local_size:entry.remote_size;
  if(size) parts.push(fmtSize(size));
  el.innerHTML=parts.join(" &middot; ");
}
function loadCatalog(){
  var status=document.getElementById("catalogStatus");
  status.textContent="Checking upstream for apps\\u2026";
  fetch("/apps/catalog").then(function(r){return r.json()}).then(function(data){
    if(data.error){status.textContent="Couldn't reach upstream repo.";return;}
    status.textContent="";
    data.forEach(function(entry){
      if(!document.getElementById("app-"+entry.name)){
        document.getElementById("appList").insertAdjacentHTML("beforeend", appRow(entry.name));
      }
      renderMeta(entry);
      renderActions(entry);
    });
  }).catch(function(){status.textContent="Couldn't reach upstream repo.";});
}
function doInstall(name,b){
  b.textContent="Installing\\u2026";b.disabled=true;
  fetch("/updates/apply?target="+encodeURIComponent(name),{method:"POST"})
    .then(function(r){return r.json()})
    .then(function(d){ if(d.ok) location.reload(); else {b.textContent="Failed";b.disabled=false;} })
    .catch(function(){b.textContent="Failed";b.disabled=false;});
}
function doUpdate(name,b){
  b.textContent="Updating\\u2026";b.disabled=true;
  fetch("/updates/apply?target="+encodeURIComponent(name),{method:"POST"})
    .then(function(r){return r.json()})
    .then(function(d){ if(d.ok) location.reload(); else {b.textContent="Failed";b.disabled=false;} })
    .catch(function(){b.textContent="Failed";b.disabled=false;});
}
function doUninstall(name,b){
  if(!confirm("Delete "+name+" from the device? This can't be undone.")) return;
  b.textContent="Deleting\\u2026";b.disabled=true;
  fetch("/apps/uninstall?name="+encodeURIComponent(name),{method:"POST"})
    .then(function(r){return r.json()})
    .then(function(d){ if(d.ok) location.reload(); else {b.textContent="Failed";b.disabled=false;} })
    .catch(function(){b.textContent="Failed";b.disabled=false;});
}
loadCatalog();
</script>"""
    )

    return (200, {}, components.page("MatrixBOX", body))


@router.route("/apps/catalog")
def apps_catalog(request):
    try:
        catalog = updater.build_catalog(_installed_app_names())
    except Exception as e:  # broad: network/GitHub API failure modes vary
        print(f"catalog fetch failed: {e}")

        return (
            200,
            {"Content-Type": "application/json"},
            json.dumps({"error": str(e)}),
        )

    return (200, {"Content-Type": "application/json"}, json.dumps(catalog))


@router.route("/apps/uninstall", method="POST")
def uninstall_app_route(request):
    name = request.params.get("name", "")
    if name not in _installed_app_names():
        return (
            200,
            {"Content-Type": "application/json"},
            json.dumps({"ok": False, "error": "not installed"}),
        )

    try:
        updater.uninstall_app(name)
    except OSError as e:
        return (
            200,
            {"Content-Type": "application/json"},
            json.dumps({"ok": False, "error": str(e)}),
        )

    changed = False
    if settings.get("autostart") == name:
        settings["autostart"] = ""
        changed = True

    if settings.get("screensaver") == name:
        settings["screensaver"] = ""
        changed = True

    if changed:
        settings.save()

    return (200, {"Content-Type": "application/json"}, json.dumps({"ok": True}))


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
    static_ip = settings["static_ip"]
    static_netmask = settings["static_netmask"]
    static_gateway = settings["static_gateway"]
    static_dns = settings["static_dns"]
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
            '<label>Network name</label><div style="display:flex;gap:8px">'
            '<input type="text" id="ssid" value="' + ssid + '" style="flex:1">'
            '<button type="button" class="btn btn-sm" onclick="scanWifi(this)">Scan</button>'
            "</div>"
            '<select id="ssid_found" style="display:none;margin-top:8px" onchange="pickScanned()"></select>'
            '<p id="scan_status" style="font-size:.75rem;color:var(--muted);margin-top:6px;min-height:14px"></p>'
            "<script>"
            "function scanWifi(b){"
            "b.textContent='Scanning\\u2026';b.disabled=true;"
            "var status=document.getElementById('scan_status');"
            "status.textContent='Scanning for networks (a few seconds)\\u2026';"
            "fetch('/wifi/scan',{method:'POST'}).then(function(r){return r.json()})"
            ".then(function(list){"
            "b.textContent='Scan';b.disabled=false;"
            "if(list.error){status.textContent='Scan failed.';return;}"
            "var sel=document.getElementById('ssid_found');"
            "sel.innerHTML='';"
            "var blank=document.createElement('option');"
            "blank.value='';blank.textContent='Select a network\\u2026';"
            "sel.appendChild(blank);"
            "list.forEach(function(n){"
            "var opt=document.createElement('option');"
            "opt.value=n.ssid;"
            "opt.textContent=n.ssid+' ('+n.rssi+' dBm, ch '+n.channel+')';"
            "sel.appendChild(opt);"
            "});"
            "sel.style.display=list.length?'':'none';"
            "status.textContent=list.length?"
            "(list.length+' network'+(list.length===1?'':'s')+' found \\u2014 pick one or keep typing above'):"
            "'No networks found.';"
            "})"
            ".catch(function(){"
            "b.textContent='Scan';b.disabled=false;"
            "status.textContent='Scan failed.';"
            "});"
            "}"
            "function pickScanned(){"
            "var sel=document.getElementById('ssid_found');"
            "if(sel.value)document.getElementById('ssid').value=sel.value;"
            "}"
            "</script>"
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
        "<label>Static IP (leave blank for DHCP)</label>"
        '<input type="text" id="static_ip" placeholder="e.g. 192.168.1.50" value="'
        + static_ip
        + '">'
        "<label>Netmask</label>"
        '<input type="text" id="static_netmask" placeholder="255.255.255.0" value="'
        + static_netmask
        + '">'
        "<label>Gateway</label>"
        '<input type="text" id="static_gateway" placeholder="e.g. 192.168.1.1" value="'
        + static_gateway
        + '">'
        "<label>DNS (optional)</label>"
        '<input type="text" id="static_dns" placeholder="e.g. 8.8.8.8" value="'
        + static_dns
        + '">'
        '<p style="font-size:.75rem;color:var(--muted);margin-top:6px">'
        "IP, netmask, and gateway are all required together for a static"
        " address — reconnect (or reboot) to apply.</p>"
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
    + "&static_ip=" + encodeURIComponent(document.getElementById("static_ip").value)
    + "&static_netmask=" + encodeURIComponent(document.getElementById("static_netmask").value)
    + "&static_gateway=" + encodeURIComponent(document.getElementById("static_gateway").value)
    + "&static_dns=" + encodeURIComponent(document.getElementById("static_dns").value)
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

    if "static_ip" in p:
        settings["static_ip"] = url_decode(p["static_ip"])

    if "static_netmask" in p:
        settings["static_netmask"] = url_decode(p["static_netmask"])

    if "static_gateway" in p:
        settings["static_gateway"] = url_decode(p["static_gateway"])

    if "static_dns" in p:
        settings["static_dns"] = url_decode(p["static_dns"])

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


@router.route("/wifi/scan", method="POST")
def wifi_scan(request):
    # Blocking for a few seconds — a manual, explicit action, not something
    # that runs in the background — see docs/ARCHITECTURE.md.
    found = {}
    try:
        for network in wifi.radio.start_scanning_networks(
            start_channel=1, stop_channel=14
        ):
            ssid = network.ssid
            if not ssid:
                continue

            if ssid not in found or network.rssi > found[ssid]["rssi"]:
                found[ssid] = {
                    "ssid": ssid,
                    "rssi": network.rssi,
                    "channel": network.channel,
                }

        wifi.radio.stop_scanning_networks()
    except Exception as e:  # broad: radio failure modes here aren't a small fixed set
        print(f"wifi scan failed: {e}")

        return (
            200,
            {"Content-Type": "application/json"},
            json.dumps({"error": str(e)}),
        )

    networks = sorted(found.values(), key=lambda n: -n["rssi"])

    return (200, {"Content-Type": "application/json"}, json.dumps(networks))


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
        stats.record_tick(0.01)


main()
