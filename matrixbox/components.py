import json
import os

import microcontroller
import wifi

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


_led_off = False


@router.route("/led", method="POST")
def _toggle_led(request):
    global _led_off
    _led_off = not _led_off
    display.set_visible(not _led_off)
    display.refresh()  # auto_refresh is off — see docs/architecture.md

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
    settings_link = (
        '<a class="nav-x" href="/settings" title="Settings">&#9881;&#xFE0F;</a>'
    )
    console_link = '<a class="nav-x" href="/console" title="Console">&#x1F4BB;</a>'
    files_link = '<a class="nav-x" href="/files" title="Files">&#x1F4C1;</a>'
    lock_icon = "&#x1F513;" if _unlocked() else "&#x1F512;"
    led_class = " led-off" if _led_off else ""
    # Plain strings + "+", no f-strings here — see docs/architecture.md.
    lock_button = (
        '<button class="nav-x" title="Toggle filesystem lock (reboots)" '
        "onclick=\"if(confirm('Reboot to toggle the filesystem lock?'))"
        "fetch('/lock',{method:'POST'})\">" + lock_icon + "</button>"
    )
    led_button = (
        '<button class="nav-led' + led_class + '" id="ledbtn" title="Toggle LED" '
        "onclick=\"fetch('/led',{method:'POST'}).then(function(r){return r.json()})"
        ".then(function(j){var b=document.getElementById('ledbtn');"
        "if(j.off){b.classList.add('led-off')}else{b.classList.remove('led-off')}})"
        ".catch(function(e){console.error('led toggle failed',e)})\">"
        "&#x1F4A1;</button>"
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
        + '</span><span class="nav-version">v'
        + _version()
        + update_dot
        + "</span></div>"
        + _signal_bars()
        + led_button
        + console_link
        + files_link
        + lock_button
        + settings_link
        + right
        + "</nav>"
        "<script>function _sig(){fetch('/rssi').then(function(r){return r.text()})"
        ".then(function(v){var s=document.getElementById('sig');if(!s)return;"
        "var r=parseInt(v),n=r>-45?5:r>-55?4:r>-65?3:r>-75?2:r>-85?1:0;"
        "s.title=r+' dBm';var b=s.querySelectorAll('i');"
        "for(var i=0;i<b.length;i++){if(i<n)b[i].classList.add('on');"
        "else b[i].classList.remove('on');}}).catch(function(){});}"
        "setInterval(_sig,30000);</script>"
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
    # Shared by the settings page and every app's template.html — see docs/architecture.md.
    return (
        '<button class="btn btn-full btn-save" onclick="'
        + onclick
        + '">\U0001f4be Save Settings</button>'
    )
