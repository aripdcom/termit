"""Persistent application settings (JSON in ~/.config/termit/config.json)."""

import copy
import json
import os

from gi.repository import GLib, GObject

CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "termit")
DATA_DIR = os.path.join(GLib.get_user_data_dir(), "termit")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_SNIPPETS = [
    {"name": "Claude Code", "command": "claude", "run": True},
    {"name": "Claude Code: continue last session", "command": "claude --continue", "run": True},
    {"name": "Claude Code: resume a session", "command": "claude --resume", "run": True},
    {"name": "Git status", "command": "git status", "run": True},
    {"name": "Git log (short)", "command": "git log --oneline -20", "run": True},
]

DEFAULTS = {
    # Layout
    "sidebar_position": "left",     # left | right
    "sidebar_visible": True,
    "notes_position": "right",      # right | bottom
    "notes_visible": False,
    "notes_size": 340,
    "window_width": 1100,
    "window_height": 720,
    "window_maximized": False,
    # Appearance
    "font": "",                     # empty = system monospace font
    "color_scheme": "system",       # system | light | dark
    "palette": "gnome",
    "cursor_shape": "block",        # block | ibeam | underline
    "cursor_blink": "system",       # system | on | off
    "bold_is_bright": False,
    "notes_monospace": False,
    # Terminal behaviour
    "custom_command": "",           # empty = $SHELL
    "login_shell": False,
    "scrollback_lines": 10000,
    "scroll_lines": 3,              # lines per mouse wheel step
    "touchpad_scroll_speed": 1.0,   # multiplier for touchpad (pixel) scrolling
    "scroll_on_output": False,
    "scroll_on_keystroke": True,
    "audible_bell": False,
    "bell_notification": True,
    "paste_warning": True,
    "copy_on_select": False,
    "new_tab_inherits_cwd": True,
    "confirm_close_tab": True,
    "confirm_close_running": True,
    # Session & notes
    "restore_session": True,
    "notes_on_close": "keep",       # keep | delete | ask
    "snippets": DEFAULT_SNIPPETS,
}


class Settings(GObject.Object):
    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, path=CONFIG_FILE):
        super().__init__()
        self.path = path
        self._data = copy.deepcopy(DEFAULTS)
        self._save_source = 0
        self.load()

    # -- persistence -------------------------------------------------------
    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        for key in DEFAULTS:
            if key in data:
                self._data[key] = data[key]

    def queue_save(self):
        if self._save_source:
            GLib.source_remove(self._save_source)
        self._save_source = GLib.timeout_add(400, self._save_timeout)

    def _save_timeout(self):
        self._save_source = 0
        self.save()
        return GLib.SOURCE_REMOVE

    def save(self):
        if self._save_source:
            GLib.source_remove(self._save_source)
            self._save_source = 0
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError as exc:  # pragma: no cover
            print(f"termit: could not save settings: {exc}")

    # -- access ------------------------------------------------------------
    def get(self, key):
        return self._data[key]

    def set(self, key, value, save=True):
        if key not in DEFAULTS:
            raise KeyError(key)
        if self._data.get(key) == value:
            return
        self._data[key] = copy.deepcopy(value)
        self.emit("changed", key)
        if save:
            self.queue_save()

    def __getitem__(self, key):
        return self.get(key)
