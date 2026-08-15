import json
import os

from matrixbox import components
from matrixbox.web import router

_DIR_BIT = 0x4000  # os.stat()[0] mode bit

# CodeMirror 5, not 6 (ESM-only, no single-file CDN build) — pinned version, Python mode only.
_CODEMIRROR_HEAD = (
    '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.css">'
    '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/theme/dracula.min.css">'
    '<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.js"></script>'
    '<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/python/python.min.js"></script>'
)


def _normalize(path: str) -> str:
    parts = []
    for segment in path.replace("\\", "/").split("/"):
        if segment == "..":
            if parts:
                parts.pop()
        elif segment and segment != ".":
            parts.append(segment)

    return "/" + "/".join(parts)


def _is_dir(path: str) -> bool:
    return bool(os.stat(path)[0] & _DIR_BIT)


def _remove_recursive(path: str):
    for name in os.listdir(path):
        child = path.rstrip("/") + "/" + name
        if _is_dir(child):
            _remove_recursive(child)
        else:
            os.remove(child)

    os.rmdir(path)


def _list_dir(path: str) -> list:
    items = []
    for name in sorted(os.listdir(path)):
        child = path.rstrip("/") + "/" + name
        try:
            stat = os.stat(child)
            is_dir = bool(stat[0] & _DIR_BIT)
            items.append(
                {"name": name, "dir": is_dir, "size": 0 if is_dir else stat[6]}
            )
        except OSError:
            pass

    return items


@router.route("/files/ls", method="POST")
def _ls(request):
    path = _normalize(request.headers.get("x-path", "/"))
    try:
        return (200, {}, json.dumps({"path": path, "items": _list_dir(path)}))
    except OSError as e:
        return (200, {}, json.dumps({"error": str(e)}))


@router.route("/files/read", method="POST")
def _read(request):
    path = _normalize(request.headers.get("x-path", ""))
    try:
        with open(path) as f:
            return (200, {}, json.dumps({"path": path, "text": f.read()}))
    except OSError as e:
        return (200, {}, json.dumps({"error": str(e)}))


@router.route("/files/write", method="POST")
def _write(request):
    path = _normalize(request.headers.get("x-path", ""))
    try:
        with open(path, "w") as f:
            f.write(request.body or "")

        return (200, {}, json.dumps({"ok": True}))
    except OSError as e:
        return (200, {}, json.dumps({"error": str(e)}))


@router.route("/files/mkdir", method="POST")
def _mkdir(request):
    path = _normalize(request.headers.get("x-path", ""))
    try:
        os.mkdir(path)
        return (200, {}, json.dumps({"ok": True}))
    except OSError as e:
        return (200, {}, json.dumps({"error": str(e)}))


@router.route("/files/delete", method="POST")
def _delete(request):
    path = _normalize(request.headers.get("x-path", ""))
    if path == "/":
        return (200, {}, json.dumps({"error": "cannot delete root"}))

    try:
        if _is_dir(path):
            _remove_recursive(path)
        else:
            os.remove(path)

        return (200, {}, json.dumps({"ok": True}))
    except OSError as e:
        return (200, {}, json.dumps({"error": str(e)}))


_HEAD = (
    """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<title>Files</title>
"""
    + _CODEMIRROR_HEAD
    + """
<style>"""
    + components.CSS
    + """
body{background:#0c0c0c;color:#ccc;font-family:'Segoe UI',system-ui,sans-serif;height:100vh;display:flex;flex-direction:column;overflow:hidden}
#toolbar{background:#1a1a2e;padding:6px 12px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #333;flex-shrink:0}
.tbtn{color:#888;text-decoration:none;font-size:.78rem;padding:4px 10px;border-radius:6px;background:#222;border:1px solid #333;cursor:pointer}
.tbtn:hover{color:#fff;border-color:#7c7cff}
#path-bar{background:#111;padding:5px 12px;border-bottom:1px solid #292929;font-size:.8rem;color:#7c7cff;display:flex;align-items:center;gap:4px;flex-shrink:0;flex-wrap:wrap}
#path-bar span{cursor:pointer;padding:2px 4px;border-radius:4px}
#path-bar span:hover{background:#222}
#listing{flex:1;overflow-y:auto}
.row{display:flex;align-items:center;padding:8px 14px;border-bottom:1px solid #1a1a1a;cursor:pointer;gap:10px;font-size:.88rem}
.row:hover{background:#151528}
.row .icon{width:20px;text-align:center;flex-shrink:0;font-size:1rem}
.row .name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row .size{color:#666;font-size:.75rem;width:60px;text-align:right;flex-shrink:0}
.row .acts{display:flex;gap:4px;flex-shrink:0}
.abtn{background:#222;border:1px solid #333;color:#888;font-size:.7rem;padding:3px 8px;border-radius:5px;cursor:pointer}
.abtn:hover{color:#fff;border-color:#7c7cff}
.abtn.del:hover{color:#ff5050;border-color:#ff5050}
#editor{display:none;flex-direction:column;flex:1;overflow:hidden}
#editor-bar{background:#1a1a2e;padding:6px 12px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #333;flex-shrink:0}
#editor-bar span{color:#e8e8e8;font-size:.82rem;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#editor-area{flex:1;background:#0c0c0c;color:#e0e0e0;border:none;padding:10px 14px;font-family:'Cascadia Mono','Fira Code','Consolas',monospace;font-size:.84rem;resize:none;outline:none;tab-size:4;line-height:1.5}
.CodeMirror{flex:1;height:0;font-family:'Cascadia Mono','Fira Code','Consolas',monospace;font-size:.84rem}
#modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:100;align-items:center;justify-content:center}
#modal{background:#1a1a2e;border:1px solid #333;border-radius:10px;padding:18px;width:280px}
#modal h3{font-size:.9rem;color:#7c7cff;margin-bottom:12px}
#modal input{width:100%;background:#111;border:1px solid #333;color:#e8e8e8;padding:8px;border-radius:6px;font-size:.85rem;outline:none;margin-bottom:10px}
#modal input:focus{border-color:#7c7cff}
#modal-btns{display:flex;gap:8px;justify-content:flex-end}
</style>
</head><body>"""
)

_BODY = """
<div id="toolbar">
<button class="tbtn" onclick="newFile()">+ file</button>
<button class="tbtn" onclick="newDir()">+ dir</button>
</div>
<div id="path-bar"></div>
<div id="listing"></div>
<div id="editor">
<div id="editor-bar">
<span id="editor-name"></span>
<button class="tbtn" onclick="saveFile()" id="saveBtn">save</button>
<button class="tbtn" onclick="closeEditor()">close</button>
</div>
<textarea id="editor-area" spellcheck="false"></textarea>
</div>
<div id="modal-bg" onclick="closeModal()">
<div id="modal" onclick="event.stopPropagation()">
<h3 id="modal-title"></h3>
<input id="modal-input" autocomplete="off">
<div id="modal-btns">
<button class="tbtn" onclick="closeModal()">cancel</button>
<button class="tbtn" id="modal-ok" style="background:#7c7cff;color:#000;border-color:#7c7cff">ok</button>
</div>
</div>
</div>
<script>
var cwd = "/";
var cm = null;

function api(ep, path, body) {
  var opts = {method: "POST", headers: {"X-Path": path || "/"}};
  if (body !== undefined) opts.body = body;
  return fetch(ep, opts).then(function(r){ return r.json(); });
}

function fmtSize(b) {
  if (b < 1024) return b + " B";
  if (b < 1048576) return (b / 1024 | 0) + " KB";
  return (b / 1048576).toFixed(1) + " MB";
}

function modeFor(fp) { return /\\.py$/i.test(fp) ? "python" : null; }

function enc(p) { return p.split("/").map(encodeURIComponent).join("/"); }
function go(path) { location.hash = enc(path || "/"); }

function renderPath() {
  var el = document.getElementById("path-bar");
  var parts = cwd.split("/").filter(Boolean);
  var html = '<span onclick="go(\\'/\\')">/</span>';
  var p = "";
  for (var i = 0; i < parts.length; i++) {
    p += "/" + parts[i];
    html += ' / <span onclick="go(\\'' + p + '\\')">' + parts[i] + '</span>';
  }
  el.innerHTML = html;
}

function parentDir() {
  var p = cwd.replace(/\\/$/, "");
  var i = p.lastIndexOf("/");
  return i <= 0 ? "/" : p.substring(0, i);
}

function doList(path) {
  cwd = path || "/";
  document.getElementById("editor").style.display = "none";
  document.getElementById("listing").style.display = "block";
  renderPath();
  api("/files/ls", cwd).then(function(d) {
    if (d.error) { alert(d.error); return; }
    var el = document.getElementById("listing");
    var html = "";
    if (cwd !== "/") {
      html += '<div class="row" onclick="go(\\'' + parentDir() + '\\')">'
        + '<span class="icon">\U0001f4c2</span><span class="name" style="color:#7c7cff">..</span>'
        + '<span class="size"></span><span class="acts"></span></div>';
    }
    d.items.forEach(function(item) {
      var fp = (cwd === "/" ? "" : cwd) + "/" + item.name;
      if (item.dir) {
        html += '<div class="row" onclick="go(\\'' + fp + '\\')">'
          + '<span class="icon">\U0001f4c1</span><span class="name" style="color:#7c7cff">' + item.name + '</span>'
          + '<span class="size"></span><span class="acts">'
          + '<button class="abtn del" onclick="event.stopPropagation();del(\\'' + fp + '\\')">\U0001f5d1</button>'
          + '</span></div>';
      } else {
        html += '<div class="row" onclick="edit(\\'' + fp + '\\')">'
          + '<span class="icon">\U0001f4c4</span><span class="name">' + item.name + '</span>'
          + '<span class="size">' + fmtSize(item.size) + '</span><span class="acts">'
          + '<button class="abtn del" onclick="event.stopPropagation();del(\\'' + fp + '\\')">\U0001f5d1</button>'
          + '</span></div>';
      }
    });
    el.innerHTML = html;
  });
}

function edit(fp) { location.hash = "f:" + enc(fp); }

function openEditor(fp) {
  cwd = fp.substring(0, fp.lastIndexOf("/")) || "/";
  api("/files/read", fp).then(function(d) {
    if (d.error) { alert(d.error); return; }
    document.getElementById("listing").style.display = "none";
    document.getElementById("editor").style.display = "flex";
    document.getElementById("editor-name").textContent = fp;
    if (!cm) {
      cm = CodeMirror.fromTextArea(document.getElementById("editor-area"), {
        theme: "dracula",
        lineNumbers: true,
        tabSize: 4,
        indentUnit: 4
      });
    }
    cm.setOption("mode", modeFor(fp));
    cm.setValue(d.text);
    cm.currentPath = fp;
  });
}

function saveFile() {
  var btn = document.getElementById("saveBtn");
  btn.textContent = "saving...";
  api("/files/write", cm.currentPath, cm.getValue()).then(function(d) {
    if (d.error) { alert(d.error); btn.textContent = "save"; }
    else { btn.textContent = "saved"; setTimeout(function(){ btn.textContent = "save"; }, 1500); }
  });
}

function closeEditor() { go(cwd); }

function del(fp) {
  var name = fp.split("/").pop();
  if (!confirm("Delete " + name + "?")) return;
  api("/files/delete", fp).then(function(d) {
    if (d.error) alert(d.error);
    else doList(cwd);
  });
}

function showModal(title, cb) {
  document.getElementById("modal-title").textContent = title;
  var inp = document.getElementById("modal-input");
  inp.value = "";
  document.getElementById("modal-bg").style.display = "flex";
  inp.focus();
  document.getElementById("modal-ok").onclick = function() {
    var v = inp.value.trim();
    if (v) cb(v);
    closeModal();
  };
  inp.onkeydown = function(e) { if (e.key === "Enter") document.getElementById("modal-ok").click(); };
}

function closeModal() { document.getElementById("modal-bg").style.display = "none"; }

function newFile() {
  showModal("New file name:", function(name) {
    var fp = cwd.replace(/\\/$/, "") + "/" + name;
    api("/files/write", fp, "").then(function(d) {
      if (d.error) alert(d.error);
      else edit(fp);
    });
  });
}

function newDir() {
  showModal("New directory name:", function(name) {
    var fp = cwd.replace(/\\/$/, "") + "/" + name;
    api("/files/mkdir", fp).then(function(d) {
      if (d.error) alert(d.error);
      else doList(cwd);
    });
  });
}

document.addEventListener("keydown", function(e) {
  if (e.ctrlKey && e.key === "s") {
    e.preventDefault();
    if (document.getElementById("editor").style.display === "flex") saveFile();
  }
});

function route() {
  var h = decodeURIComponent(location.hash.slice(1));
  if (h.slice(0, 2) === "f:") openEditor(h.slice(2));
  else doList(h || "/");
}
window.addEventListener("hashchange", route);
if (location.hash.length > 1) route(); else go("/");
</script>
</body></html>"""


@router.route("/files")
def _files_page(request):
    return (200, {}, _HEAD + components.navbar() + _BODY)
