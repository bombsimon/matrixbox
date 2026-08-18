import json
import os


class JSONStore:
    # Values coerce to the type of their default — see docs/ARCHITECTURE.md.
    def __init__(self, path, defaults):
        self._path = path
        self._defaults = dict(defaults)
        self._values = dict(self._defaults)
        self.load()

    def load(self):
        try:
            with open(self._path) as f:
                stored = json.loads(f.read())
        except OSError:
            return self
        except ValueError as e:
            # A corrupt file (e.g. a write interrupted by power loss —
            # see docs/ARCHITECTURE.md) silently falling back to blank
            # defaults is how ssid/password vanish without a trace, so
            # this stays loud even though it's still non-fatal.
            print(f"could not parse {self._path}, using defaults: {e}")
            return self

        for key, value in stored.items():
            if key in self._defaults:
                self._values[key] = self._coerce(key, value)

        return self

    def save(self):
        # Write to a temp file and rename over the real one — atomic, so an
        # interrupted write (power loss mid-save) can never leave the real
        # file half-written or trailing garbage behind — see docs/ARCHITECTURE.md.
        #
        # matrixbox.display isn't imported at module level here — it in
        # turn imports matrixbox.settings for the panel geometry, and a
        # top-level import back would be circular — see docs/ARCHITECTURE.md.
        from matrixbox.display import display

        display.set_visible(False)
        display.refresh()

        tmp_path = self._path + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                f.write(json.dumps(self._values))

            os.rename(tmp_path, self._path)
        except OSError as e:
            print(f"could not save {self._path}: {e}")

        display.set_visible(True)
        display.refresh()

        return self

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value, save=False):
        if key not in self._defaults:
            raise KeyError(f"unknown setting: {key!r}")

        self._values[key] = self._coerce(key, value)
        if save:
            self.save()

        return self

    def update(self, values, save=False):
        for key, value in values.items():
            if key in self._defaults:
                self._values[key] = self._coerce(key, value)

        if save:
            self.save()

        return self

    def delete(self, key, save=False):
        self._values[key] = self._defaults[key]  # resets to default, doesn't remove
        if save:
            self.save()

        return self

    def as_dict(self):
        return dict(self._values)

    def _coerce(self, key, value):
        default = self._defaults[key]
        if isinstance(default, bool):
            return (
                value.lower() not in ("", "0", "false")
                if isinstance(value, str)
                else bool(value)
            )

        if isinstance(default, int):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        return value

    def __getitem__(self, key):
        return self._values[key]

    def __setitem__(self, key, value):
        self.set(key, value)

    def __contains__(self, key):
        return key in self._values


SETTINGS_PATH = "/settings.txt"

DEFAULTS = {
    "ssid": "",
    "password": "",
    "channel": 0,
    "static_ip": "",  # "" = DHCP — see docs/ARCHITECTURE.md
    "static_netmask": "",
    "static_gateway": "",
    "static_dns": "",
    "autostart": "",  # "" = off, else an app directory name — see docs/ARCHITECTURE.md
    "screensaver": "",
    "rotation": 0,
    "width": 64,
    "height": 32,
    "tiles": 1,
    "wifi_power": 15,
    "color_correct": False,
    "email": "",
    "repository_source": "bombsimon/matrixbox",  # GitHub "owner/repo", temporary — see docs/ARCHITECTURE.md
    "repository_branch": "matrixbox-v2",
}


class Settings(JSONStore):
    def __init__(self, path=SETTINGS_PATH, defaults=None):
        super().__init__(path, defaults if defaults is not None else DEFAULTS)


class AppSettings(JSONStore):
    pass


settings = Settings()
