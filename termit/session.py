"""A tab session: one or more terminals (split panes), a note buffer and display metadata."""

import os
import re
import time
import uuid

from gi.repository import GObject, Gtk

from .i18n import _

TAB_COLORS = ["red", "orange", "yellow", "green", "blue", "purple"]
_HOSTTITLE_RE = re.compile(r"^[^@\s]+@[^:\s]+:\s*(.*)$")


def short_path(path):
    if not path:
        return ""
    home = os.path.expanduser("~")
    if path == home:
        return "~"
    if path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


def format_elapsed(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


class TabSession(GObject.Object):
    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, panes, sid=None):
        super().__init__()
        self.id = sid or uuid.uuid4().hex[:12]
        self.panes = panes
        self.note_buffer = Gtk.TextBuffer()
        self.note_buffer.set_enable_undo(True)
        self.custom_title = None
        self.color = None
        self.window_title = ""
        self.cwd = ""
        self.fg_process = None
        self.fg_pid = None
        self.fg_since = None
        self.activity = False
        self.attention = False
        self.row = None
        self.page = None
        self.created = time.time()

    # -- terminals ----------------------------------------------------------
    @property
    def terminal(self):
        """The active (last focused) terminal of the tab."""
        return self.panes.active

    @property
    def terminals(self):
        return self.panes.terminals

    @property
    def pane_count(self):
        return len(self.panes)

    def any_running(self):
        return any(t.has_foreground_process() for t in self.terminals)

    # -- derived display values -------------------------------------------
    @property
    def short_cwd(self):
        return short_path(self.cwd)

    @property
    def display_title(self):
        if self.custom_title:
            return self.custom_title
        title = (self.window_title or "").strip()
        if title:
            match = _HOSTTITLE_RE.match(title)
            if match:
                title = match.group(1).strip()
            if title and title not in (self.short_cwd, self.cwd):
                return title
        if self.fg_process:
            return self.fg_process
        base = os.path.basename(self.cwd.rstrip(os.sep)) if self.cwd else ""
        return base or _("Terminal")

    @property
    def process_label(self):
        if not self.fg_process:
            return ""
        if self.fg_since:
            return f"{self.fg_process} · {format_elapsed(time.time() - self.fg_since)}"
        return self.fg_process

    def mark_changed(self):
        self.emit("changed")

    def note_text(self):
        start, end = self.note_buffer.get_bounds()
        return self.note_buffer.get_text(start, end, True)

    def to_dict(self):
        def cwd_of(terminal):
            info = terminal.foreground_info()
            return (info[2] if info else "") or terminal.shell_cwd() or self.cwd

        return {
            "id": self.id,
            "cwd": self.cwd,
            "custom_title": self.custom_title,
            "color": self.color,
            "layout": self.panes.layout(cwd_of) if self.pane_count > 1 else None,
        }
