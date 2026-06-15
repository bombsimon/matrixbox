from __main__ import *
import sys

EFFECTS = []

for directory in os.listdir():
    if not "." in directory:
        print("Found effect:", directory)
        EFFECTS.append(directory)

#EFFECTS = ["aquarium", "fireworks", "rain", "space", "starcloud"]

# Load saved choice
try:
    with open("sv_settings.json") as f:
        _sv_cfg = json.loads(f.read())
except:
    _sv_cfg = {"effect": "starcloud"}

def _save_sv():
    try:
        with open("sv_settings.json", "w") as f:
            f.write(json.dumps(_sv_cfg))
    except:
        pass  # Read-only filesystem — effect change still works in memory

# Global switch flag (True = switch effect, False = exit app)
_sv_switch = False

# Web UI
@ampule.route("/", method="GET")
def sv_index(request):
    try:
        opts = ""
        for e in EFFECTS:
            sel = " selected" if e == _sv_cfg["effect"] else ""
            opts += "<option value='" + e + "'" + sel + ">" + e[0].upper() + e[1:] + "</option>"
        cur = _sv_cfg["effect"]
        cfg_link = ("<p><a href='/settings' style='color:#aaa;font-size:.9rem'>&#9881; " + cur[0].upper() + cur[1:] + " settings</a></p>") if cur in ("aquarium", "fireworks") else ""
        return (200, {}, """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{background:#0d0d12;color:#eee;font-family:sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;gap:12px;margin:0;text-align:center}select{font-size:1.1rem;padding:8px 12px;border-radius:8px;background:#1a1a2e;color:#eee;border:1px solid #444;width:200px}a{color:#ff6060;text-decoration:none;font-size:.9rem}</style></head>
<body><h2 style="color:#f0c800;margin-bottom:4px">Screensaver</h2>
<select onchange="fetch('/?effect='+this.value,{method:'POST'}).then(()=>setTimeout(()=>location.reload(),1500))">""" + opts + """</select>
""" + cfg_link + """<a href="/exit">&#x274C; Exit</a></body></html>""")
    except Exception as e:
        return (200, {}, "ERR: " + str(e))

@ampule.route("/", method="POST")
def sv_post(request):
    global _sv_switch
    if request.params and "effect" in request.params:
        e = request.params["effect"]
        if e in EFFECTS:
            _sv_cfg["effect"] = e
            _save_sv()
            _sv_switch = True
            load_settings.app_running = False
    return (200, {}, "{}")

@ampule.route("/exit", method="GET")
def sv_exit(request):
    load_settings.app_running = False
    return (200, {}, """<meta http-equiv="refresh" content="0; url=../" />""")

# Run the selected effect; loop to support live switching
while True:
    _sv_switch = False
    load_settings.app_running = True

    effect = _sv_cfg.get("effect", "starcloud")
    if effect not in EFFECTS:
        effect = "starcloud"

    # Remove cached modules so re-import re-runs their code
    for _m in EFFECTS:
        if _m in sys.modules:
            del sys.modules[_m]

    if effect == "aquarium":
        import aquarium
    elif effect == "fireworks":
        import fireworks
    elif effect == "rain":
        import rain
    elif effect == "space":
        import space
    else:
        import starcloud

    if not _sv_switch:
        break  # Normal exit (button press or /exit)
