import __main__
from matrixbox import components
from matrixbox.web import router

_env = None  # built lazily — __main__'s globals aren't complete at import time


def _run(command: str) -> str:
    global _env
    if _env is None:
        _env = dict(__main__.__dict__)  # vars() isn't implemented on this build

    output = []
    _env["print"] = lambda *args, **kwargs: output.append(
        kwargs.get("sep", " ").join(str(a) for a in args)
    )

    try:
        result = eval(command, _env)
        if result is not None:
            output.append(repr(result))
    except SyntaxError:
        try:
            exec(command, _env)  # noqa: S102
        except Exception as e:
            output.append(str(e))
    except Exception as e:
        output.append(str(e))

    return "\n".join(output)


@router.route("/console", method="POST")
def _console_run(request):
    return (200, {"Content-Type": "text/plain"}, _run(request.body or ""))


_HEAD = (
    """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<title>Console</title>
<style>"""
    + components.CSS
    + """
body{background:#0c0c0c;color:#ccc;font-family:'Cascadia Mono','Fira Code','Consolas',monospace;height:100vh;display:flex;flex-direction:column;overflow:hidden}
#out{flex:1;overflow-y:auto;padding:10px 14px;font-size:.85rem;line-height:1.6;white-space:pre-wrap;word-break:break-all}
#row{display:flex;align-items:center;padding:6px 10px;background:#111;border-top:1px solid #333;flex-shrink:0;gap:6px}
#cmd{flex:1;background:transparent;border:none;outline:none;color:#e8e8e8;font-family:inherit;font-size:.88rem;caret-color:#7c7cff}
#run{background:#7c7cff;color:#000;border:none;padding:6px 14px;border-radius:6px;font-weight:700;font-size:.82rem;cursor:pointer}
</style>
</head><body>"""
)

_BODY = """
<div id="out">ready</div>
<div id="row">
<input id="cmd" type="text" placeholder="Python..." autocomplete="off" autofocus>
<button id="run">Run</button>
</div>
<script>
var out=document.getElementById("out"),cmd=document.getElementById("cmd");
function run(){
  var c=cmd.value;
  if(!c)return;
  var p=document.createElement("span");p.textContent="\\n>>> "+c;out.appendChild(p);
  cmd.value="";
  fetch("/console",{method:"POST",body:c}).then(function(r){return r.text()}).then(function(t){
    if(t){var e=document.createElement("span");e.textContent="\\n"+t;out.appendChild(e)}
    out.scrollTop=out.scrollHeight;
  });
}
document.getElementById("run").addEventListener("click",run);
cmd.addEventListener("keydown",function(e){if(e.key==="Enter")run()});
</script>
</body></html>"""


@router.route("/console")
def _console_page(request):
    return (200, {}, _HEAD + components.navbar() + _BODY)
