import os

from matrixbox.net import http
from matrixbox.settings import settings

HEADERS = {"User-Agent": "MatrixBox"}
BINARY_EXTENSIONS = ("mpy", "gif", "bmp", "png", "jpg", "bin", "raw")

# Set by update_system(), read by main.py's loop — a reset from inside the
# request handler that triggered it would kill the response before it's
# sent — see docs/architecture.md.
reboot_pending = False

# Populated by check_all(); {"/" or app_name: new_version}. Read by
# components.navbar() to show the update indicator, cheap because it's
# just a dict lookup — checking is the expensive/networked part.
available = {}


def _raw_url(path):
    return (
        "https://raw.githubusercontent.com/"
        + settings["repository_source"]
        + "/refs/heads/"
        + settings["repository_branch"]
        + "/"
        + path
    )


def _tree_url():
    return (
        "https://api.github.com/repos/"
        + settings["repository_source"]
        + "/git/trees/"
        + settings["repository_branch"]
        + "?recursive=1"
    )


def local_version(dir_path):
    # Version marker: a file named "v<version>" — see docs/architecture.md.
    try:
        names = os.listdir(dir_path)
    except OSError:
        return None

    for name in names:
        if name[:1] == "v" and name[1:2].isdigit():
            return name[1:]

    return None


def _remote_version(files):
    for path in files:
        name = path.rsplit("/", 1)[-1]
        if name[:1] == "v" and name[1:2].isdigit():
            return name[1:]

    return None


def _version_tuple(v):
    try:
        return tuple(int(part) for part in v.split("."))
    except ValueError:
        return (0,)


def is_newer(remote, local) -> bool:
    if not remote:
        return False

    return _version_tuple(remote) > _version_tuple(local or "0")


def fetch_remote_tree() -> dict:
    # One recursive tree call lists every file in the repo — cheaper than
    # a directory listing per app, and raw.githubusercontent.com has no
    # directory-listing endpoint at all — see docs/architecture.md.
    r = http.get(_tree_url(), headers=HEADERS)
    tree = r.json()["tree"]
    r.close()

    apps = {}
    root_files = []
    for item in tree:
        if item["type"] != "blob":
            continue

        parts = item["path"].split("/")
        if len(parts) == 1:
            root_files.append(parts[0])
            continue

        if parts[0] == "apps" and len(parts) > 2:
            dirname = parts[1]
            filename = "/".join(parts[2:])
        elif parts[0] == "matrixbox":
            dirname = "matrixbox"
            filename = "/".join(parts[1:])
        else:
            continue

        apps.setdefault(dirname, []).append(filename)

    system_files = root_files[:]
    if "matrixbox" in apps:
        system_files += ["matrixbox/" + f for f in apps.pop("matrixbox")]

    apps["/"] = system_files

    return apps


def check_app_update(name, tree=None):
    tree = tree if tree is not None else fetch_remote_tree()
    files = tree.get(name)
    if not files:
        return None

    remote = _remote_version(files)

    return remote if is_newer(remote, local_version("/apps/" + name)) else None


def check_system_update(tree=None):
    tree = tree if tree is not None else fetch_remote_tree()
    remote = _remote_version(tree.get("/", []))

    return remote if is_newer(remote, local_version("/")) else None


def check_all(installed_apps) -> dict:
    # One tree fetch covers every check, system included — see docs/architecture.md.
    # Mutates `available` in place rather than rebinding it, so a
    # `from matrixbox.updater import available` elsewhere (components.navbar())
    # keeps seeing updates — a rebind would leave that import stale.
    tree = fetch_remote_tree()
    updates = {}

    system_update = check_system_update(tree)
    if system_update:
        updates["/"] = system_update

    for name in installed_apps:
        app_update = check_app_update(name, tree)
        if app_update:
            updates[name] = app_update

    available.clear()
    available.update(updates)

    return available


def _ensure_dir(path):
    parts = path.split("/")
    current = ""
    for part in parts:
        if not part:
            continue

        current = current + "/" + part if current else part
        try:
            os.mkdir(current)
        except OSError:
            pass  # already exists


def _download_all(files, url_for, dest_for):
    # Two-pass: download everything into memory and confirm every file
    # succeeded before writing anything to disk, so a network failure
    # partway through never leaves an app (or the system) half-updated
    # — see docs/architecture.md.
    downloads = []
    for path in files:
        r = http.get(url_for(path), headers=HEADERS)
        if r.status_code != 200:
            r.close()
            raise RuntimeError(f"fetch failed for {path}: {r.status_code}")

        binary = path.rsplit(".", 1)[-1] in BINARY_EXTENSIONS
        data = r.content if binary else r.text
        r.close()
        downloads.append((dest_for(path), data, "wb" if binary else "w"))

    for dest, data, mode in downloads:
        _ensure_dir(dest.rsplit("/", 1)[0])
        with open(dest, mode) as f:
            f.write(data)


def _replace_version_marker(dir_path, new_version):
    for name in os.listdir(dir_path):
        if name[:1] == "v" and name[1:2].isdigit():
            os.remove(dir_path + "/" + name)

    with open(dir_path + "/v" + new_version, "w") as f:
        f.write("")


def update_app(name):
    tree = fetch_remote_tree()
    files = tree.get(name)
    if not files:
        raise RuntimeError(f"no upstream files for app {name!r}")

    dest_dir = "/apps/" + name
    _ensure_dir(dest_dir)
    _download_all(
        files,
        url_for=lambda p: _raw_url("apps/" + name + "/" + p),
        dest_for=lambda p: dest_dir + "/" + p,
    )
    _replace_version_marker(dest_dir, _remote_version(files))


def update_system():
    # Caller must reboot once this returns — see reboot_pending above.
    global reboot_pending

    tree = fetch_remote_tree()
    files = tree.get("/", [])
    if not files:
        raise RuntimeError("no upstream system files")

    _download_all(files, url_for=_raw_url, dest_for=lambda p: "/" + p)
    _replace_version_marker("/", _remote_version(files))
    reboot_pending = True
