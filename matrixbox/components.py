import json
import os

import microcontroller
import wifi

from matrixbox import stats
from matrixbox.display import display
from matrixbox.theme import CSS, FAVICON_SVG
from matrixbox.updater import available as available_updates
from matrixbox.updater import local_version
from matrixbox.web import router

__all__ = ["CSS", "FAVICON_SVG", "card", "navbar", "page", "save_button", "wifi_ip"]


def wifi_ip() -> str:
    return str(wifi.radio.ipv4_address) if wifi.radio.ipv4_address else "OFFLINE"


def _version() -> str:
    return local_version("/") or "?"


def _unlocked() -> bool:
    return "dev_mode" in os.listdir("/")


def _rssi() -> int:
    try:
        info = wifi.radio.ap_info
        return info.rssi if info else -100
    except Exception:  # broad: Wi-Fi failure modes here aren't a small fixed set
        return -100


def _signal_bars() -> str:
    rssi = _rssi()
    lit = (
        5
        if rssi > -45
        else 4
        if rssi > -55
        else 3
        if rssi > -65
        else 2
        if rssi > -75
        else 1
        if rssi > -85
        else 0
    )
    dots = "".join(f'<i class="{"on" if i < lit else ""}"></i>' for i in range(5))

    return f'<span class="sig" id="sig" title="{rssi} dBm">{dots}</span>'


@router.route("/rssi")
def _rssi_route(request):
    return (200, {"Content-Type": "text/plain"}, str(_rssi()))


@router.route("/stats")
def _stats_route(request):
    body = json.dumps({"cpu": stats.cpu_percent(), "mem": stats.mem_percent()})

    return (200, {"Content-Type": "application/json"}, body)


_led_off = False


@router.route("/led", method="POST")
def _toggle_led(request):
    global _led_off
    _led_off = not _led_off
    display.set_visible(not _led_off)
    display.refresh()  # auto_refresh is off — see docs/ARCHITECTURE.md

    return (200, {"Content-Type": "application/json"}, json.dumps({"off": _led_off}))


@router.route("/lock", method="POST")
def _toggle_lock(request):
    # Takes effect next boot, not live — see boot.py.
    if _unlocked():
        try:
            os.remove("/dev_mode")
        except OSError:
            pass
    else:
        with open("/unlock", "w") as f:
            f.write("")

    microcontroller.reset()

    return (200, {}, "ok")  # unreachable — reset() doesn't return


def navbar(title: str = None, *, exit_href: str = None) -> str:
    title = title or ""  # "+" (unlike the f-string this replaced) can't concat None

    if exit_href:
        left = (
            '<a class="nav-x" href="'
            + exit_href
            + '" title="Exit" style="margin-left:0;margin-right:4px">&#8592;</a>'
            '<span class="nav-title">' + title + "</span>"
        )
    else:
        left = '<a class="nav-brand" href="/">Matrix<span class="brand-yellow">BOX</span></a>'

    right = (
        '<a class="nav-x" href="' + exit_href + '" title="Exit">&#x2715;</a>'
        if exit_href
        else ""
    )

    lock_icon = "&#x1F513;" if _unlocked() else "&#x1F512;"
    lock_label = "Filesystem: unlocked" if _unlocked() else "Filesystem: locked"
    led_label = "LED: off" if _led_off else "LED: on"

    # All the buttons that used to crowd the main row live in this dropdown
    # instead — the main row only has room for the essentials — see
    # docs/ARCHITECTURE.md. Plain strings + "+", no f-strings — same reason.
    hamburger_menu = (
        '<button onclick="toggleLed()"><span class="hm-icon">&#x1F4A1;</span>'
        '<span id="ledLabel">' + led_label + "</span></button>"
        '<a href="/console"><span class="hm-icon">&#x1F4BB;</span>Console</a>'
        '<a href="/files"><span class="hm-icon">&#x1F4C1;</span>Files</a>'
        "<button onclick=\"if(confirm('Reboot to toggle the filesystem lock?'))"
        "fetch('/lock',{method:'POST'})\"><span class=\"hm-icon\">"
        + lock_icon
        + "</span>"
        + lock_label
        + "</button>"
        '<a href="/settings"><span class="hm-icon">&#9881;&#xFE0F;</span>Settings</a>'
    )

    update_dot = (
        '<span class="update-dot" title="Update available"></span>'
        if available_updates
        else ""
    )

    return (
        '<nav class="navbar">' + left + '<div class="nav-spacer"></div>'
        '<div class="nav-info"><span>'
        + wifi_ip()
        + '</span><span class="nav-stats" id="navstats">CPU --% &middot; MEM --%</span>'
        '<span class="nav-version">v'
        + _version()
        + update_dot
        + "</span></div>"
        + _signal_bars()
        + '<div class="hamburger-wrap">'
        '<button class="hamburger-toggle" id="hamburgerToggle" '
        'title="Menu" onclick="toggleHamburger(event)">&#9776;</button>'
        '<div class="hamburger-menu" id="hamburgerMenu">' + hamburger_menu + "</div>"
        "</div>" + right + "</nav>"
        "<script>function _sig(){fetch('/rssi').then(function(r){return r.text()})"
        ".then(function(v){var s=document.getElementById('sig');if(!s)return;"
        "var r=parseInt(v),n=r>-45?5:r>-55?4:r>-65?3:r>-75?2:r>-85?1:0;"
        "s.title=r+' dBm';var b=s.querySelectorAll('i');"
        "for(var i=0;i<b.length;i++){if(i<n)b[i].classList.add('on');"
        "else b[i].classList.remove('on');}}).catch(function(){});}"
        "setInterval(_sig,30000);_sig();"
        "function _stats(){fetch('/stats').then(function(r){return r.json()})"
        ".then(function(d){var s=document.getElementById('navstats');if(!s)return;"
        "s.textContent='CPU '+d.cpu+'% \\u00b7 MEM '+d.mem+'%';})"
        ".catch(function(){});}"
        "setInterval(_stats,5000);_stats();"
        "function toggleHamburger(e){e.stopPropagation();"
        "document.getElementById('hamburgerMenu').classList.toggle('open');}"
        "document.addEventListener('click',function(e){"
        "var m=document.getElementById('hamburgerMenu');"
        "if(m&&m.classList.contains('open')&&!m.contains(e.target))"
        "m.classList.remove('open');});"
        "function toggleLed(){fetch('/led',{method:'POST'})"
        ".then(function(r){return r.json()})"
        ".then(function(j){document.getElementById('ledLabel').textContent="
        "j.off?'LED: off':'LED: on';})"
        ".catch(function(e){console.error('led toggle failed',e)});}"
        "</script>"
    )


def page(title: str, body: str, *, exit_href: str = None) -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<title>{title}</title>
<style>{CSS}</style>
</head><body>{navbar(title, exit_href=exit_href)}<div class="page">{body}</div></body></html>"""


def card(title: str, content: str) -> str:
    return f'<div class="card"><div class="section-title">{title}</div>{content}</div>'


def save_button(onclick: str = "save(this)") -> str:
    # Shared by the settings page and every app's template.html — see docs/ARCHITECTURE.md.
    return (
        '<button class="btn btn-full btn-save" onclick="'
        + onclick
        + '">\U0001f4be Save Settings</button>'
    )
