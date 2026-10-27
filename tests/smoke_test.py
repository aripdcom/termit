"""Headless smoke test: start the app, open tabs, write a note, close a tab, verify the archive.

Run with: xvfb-run -a python3 tests/smoke_test.py
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

tmp = tempfile.mkdtemp(prefix="termit-test-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(tmp, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(tmp, "data")
os.environ.setdefault("SHELL", "/bin/sh")

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Vte", "3.91")
from gi.repository import GLib  # noqa: E402

from termit.main import TermitApplication  # noqa: E402

app = TermitApplication()
failures = []


def check(condition, message):
    if not condition:
        failures.append(message)
        print("FAIL:", message)
    else:
        print("ok:", message)


def finish(code):
    print("DONE" if code == 0 else "FAILED")
    os._exit(code)


def step1():
    win = app.get_active_window()
    check(win is not None, "window created")
    check(len(win.sessions()) == 1, "one tab on start")
    second = win.new_tab(cwd=tmp)
    second.custom_title = "Second"
    second.note_buffer.set_text("remember this")
    win.notes.flush()
    check(app.store.read(second.id) == "remember this", "note written to disk")
    check(win.current is second, "new tab is selected")
    win.lookup_action("set-tab-color").activate(GLib.Variant("s", "green"))
    check(second.color == "green", "tab colour applied")
    win.lookup_action("prev-tab").activate(None)
    check(win.current is win.sessions()[0], "prev-tab switches tab")
    GLib.timeout_add(1500, step2, second)
    return False


def step2(second):
    win = app.get_active_window()
    check(second.terminal.child_pid is not None, "shell spawned")
    win.close_session(second, force=True)
    check(second not in win.sessions(), "tab closed")
    archived = [nid for nid, _entry in app.store.archived()]
    check(second.id in archived, "note archived when tab closed")
    check(len(win.sessions()) == 1, "one tab left")
    win.settings.set("notes_position", "bottom")
    win.settings.set("sidebar_position", "right")
    win.settings.set("palette", "dracula")
    finish(1 if failures else 0)
    return False


GLib.timeout_add(1500, step1)
GLib.timeout_add(20000, lambda: (print("TIMEOUT"), finish(1)))
sys.exit(app.run([]))
