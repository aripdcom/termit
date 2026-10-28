"""VTE based terminal widget with link handling, search and process inspection."""

import os
import re
import shlex

import gi

gi.require_version("Vte", "3.91")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango, Vte  # noqa: E402

from . import __version__, palettes  # noqa: E402
from .i18n import _  # noqa: E402

# PCRE2 flags (vte uses PCRE2 for matching)
PCRE2_CASELESS = 0x00000008
PCRE2_MULTILINE = 0x00000400
PCRE2_UCP = 0x00020000
PCRE2_UTF = 0x00080000
PCRE2_NO_UTF_CHECK = 0x40000000
MATCH_FLAGS = PCRE2_MULTILINE | PCRE2_UCP | PCRE2_UTF | PCRE2_NO_UTF_CHECK

URL_RE = (
    r"(?:https?|ftp|ftps|file|ssh|git|sftp)://[^\s<>\"'`\]\)]+"
    r"|(?<![\w@./-])www\.[\w-]+(?:\.[\w-]+)+[^\s<>\"'`\]\)]*"
)
EMAIL_RE = r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.-])"
PATH_RE = (
    r"(?<![\w/.~-])(?:~/|\.{1,2}/|/)[\w.@+%-]+(?:/[\w.@+%-]+)*(?::\d+(?::\d+)?)?"
    r"|(?<![\w/.~-])[\w.@+%-]+(?:/[\w.@+%-]+)+(?::\d+(?::\d+)?)?"
)

_TRAILING_PUNCT = ".,;:!?'\")]}>"

KIND_URL = "url"
KIND_EMAIL = "email"
KIND_PATH = "path"


def _rgba(hex_color):
    rgba = Gdk.RGBA()
    rgba.parse(hex_color)
    return rgba


def _default_monospace_font():
    source = Gio.SettingsSchemaSource.get_default()
    if source is not None and source.lookup("org.gnome.desktop.interface", True):
        try:
            gs = Gio.Settings.new("org.gnome.desktop.interface")
            font = gs.get_string("monospace-font-name")
            if font:
                return font
        except Exception:  # pragma: no cover
            pass
    return "Monospace 11"


class TermitTerminal(Vte.Terminal):
    """Vte.Terminal with Termit behaviour."""

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.child_pid = None
        self.shell_name = ""
        self.spawned = False
        self._pending_input = []
        self.exited = False
        self._context_link = None
        self._match_kinds = {}
        self.on_link_open = None  # callable(uri) -> bool
        self.on_paste_confirm = None  # callable(text, continue_cb)

        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_mouse_autohide(True)
        self.set_allow_hyperlink(True)
        self.set_enable_sixel(False)
        self.set_word_char_exceptions("-,.;:/@_~#%&?=+")

        self._scroll_remainder = 0.0
        self._setup_matches()
        self._setup_actions()
        self._setup_gestures()
        self._setup_scrolling()
        self.connect("setup-context-menu", self._on_setup_context_menu)
        self.connect("selection-changed", self._on_selection_changed)
        self.settings.connect("changed", self._on_settings_changed)
        self.apply_settings()

    # -- settings ------------------------------------------------------------
    def apply_settings(self):
        s = self.settings
        font = s.get("font") or _default_monospace_font()
        self.set_font(Pango.FontDescription.from_string(font))
        self.set_scrollback_lines(int(s.get("scrollback_lines")))
        self.set_scroll_on_output(bool(s.get("scroll_on_output")))
        self.set_scroll_on_keystroke(bool(s.get("scroll_on_keystroke")))
        self.set_audible_bell(bool(s.get("audible_bell")))
        self.set_bold_is_bright(bool(s.get("bold_is_bright")))
        shape = {
            "block": Vte.CursorShape.BLOCK,
            "ibeam": Vte.CursorShape.IBEAM,
            "underline": Vte.CursorShape.UNDERLINE,
        }.get(s.get("cursor_shape"), Vte.CursorShape.BLOCK)
        self.set_cursor_shape(shape)
        blink = {
            "system": Vte.CursorBlinkMode.SYSTEM,
            "on": Vte.CursorBlinkMode.ON,
            "off": Vte.CursorBlinkMode.OFF,
        }.get(s.get("cursor_blink"), Vte.CursorBlinkMode.SYSTEM)
        self.set_cursor_blink_mode(blink)
        self.apply_colors()

    def apply_colors(self, dark=None):
        if dark is None:
            try:
                gi.require_version("Adw", "1")
                from gi.repository import Adw

                dark = Adw.StyleManager.get_default().get_dark()
            except Exception:  # pragma: no cover
                dark = True
        fg, bg, colors = palettes.resolve(self.settings.get("palette"), dark)
        self.set_colors(_rgba(fg), _rgba(bg), [_rgba(c) for c in colors])

    def _on_settings_changed(self, settings, key):
        if key in (
            "font", "scrollback_lines", "scroll_on_output", "scroll_on_keystroke",
            "audible_bell", "bold_is_bright", "cursor_shape", "cursor_blink", "palette",
        ):
            self.apply_settings()

    # -- spawning ------------------------------------------------------------
    def spawn(self, cwd=None, argv=None, session_id=None):
        if not cwd or not os.path.isdir(cwd):
            cwd = os.path.expanduser("~")
        flags = GLib.SpawnFlags.DEFAULT
        if argv:
            argv = list(argv)
        else:
            custom = (self.settings.get("custom_command") or "").strip()
            if custom:
                try:
                    argv = shlex.split(custom)
                except ValueError:
                    argv = [custom]
            else:
                shell = os.environ.get("SHELL") or "/bin/bash"
                if not os.path.exists(shell):
                    shell = "/bin/sh"
                if self.settings.get("login_shell"):
                    argv = [shell, "-" + os.path.basename(shell)]
                    flags |= GLib.SpawnFlags.FILE_AND_ARGV_ZERO
                else:
                    argv = [shell]
        if not (flags & GLib.SpawnFlags.FILE_AND_ARGV_ZERO):
            flags |= GLib.SpawnFlags.SEARCH_PATH

        env = dict(os.environ)
        env.pop("COLUMNS", None)
        env.pop("LINES", None)
        env.update({
            "TERM": "xterm-256color",
            "COLORTERM": "truecolor",
            "TERM_PROGRAM": "termit",
            "TERM_PROGRAM_VERSION": __version__,
            "VTE_VERSION": f"{Vte.get_major_version()}{Vte.get_minor_version():02d}{Vte.get_micro_version():02d}",
        })
        if session_id:
            env["TERMIT_SESSION_ID"] = session_id
        envv = [f"{k}={v}" for k, v in env.items()]
        self.shell_name = os.path.basename(argv[0])

        self.spawn_async(
            Vte.PtyFlags.DEFAULT, cwd, argv, envv, flags,
            None, None, -1, None, self._on_spawned,
        )

    def _on_spawned(self, terminal, pid, error, *user_data):
        if error is not None or pid <= 0:
            msg = error.message if error else "unknown error"
            self.feed(f"\r\n\x1b[31m{_('Could not start the shell')}: {msg}\x1b[0m\r\n".encode())
            self.child_pid = None
            return
        self.child_pid = pid
        self.spawned = True
        if self._pending_input:
            # Give the shell a moment to initialise before typing queued commands.
            GLib.timeout_add(300, self._flush_pending_input)

    def _flush_pending_input(self):
        pending, self._pending_input = self._pending_input, []
        for data in pending:
            self.feed_child(data)
        return GLib.SOURCE_REMOVE

    # -- process inspection ----------------------------------------------------
    def foreground_info(self):
        """Return (pid, command name, cwd) of the foreground process group, or None."""
        pty = self.get_pty()
        if pty is None or self.child_pid is None:
            return None
        try:
            pgrp = os.tcgetpgrp(pty.get_fd())
        except OSError:
            return None
        if pgrp <= 0:
            return None
        try:
            with open(f"/proc/{pgrp}/comm", "r", encoding="utf-8", errors="replace") as fh:
                comm = fh.read().strip()
        except OSError:
            comm = ""
        try:
            cwd = os.readlink(f"/proc/{pgrp}/cwd")
        except OSError:
            cwd = ""
        return pgrp, comm, cwd

    def is_shell_idle(self, info):
        """True when the foreground process is the shell itself (no program running)."""
        if not info or self.child_pid is None:
            return True
        pid, comm, _cwd = info
        if pid != self.child_pid:
            return False
        # The shell may have replaced itself with another program (`exec htop`).
        return not comm or comm == self.shell_name or comm.lstrip("-") == self.shell_name

    def has_foreground_process(self):
        return not self.is_shell_idle(self.foreground_info())

    def shell_cwd(self):
        if self.child_pid:
            try:
                return os.readlink(f"/proc/{self.child_pid}/cwd")
            except OSError:
                pass
        return ""

    # -- clipboard -----------------------------------------------------------
    def copy(self):
        if self.get_has_selection():
            self.copy_clipboard_format(Vte.Format.TEXT)

    def paste(self):
        clipboard = self.get_clipboard()
        clipboard.read_text_async(None, self._on_clipboard_text)

    def _on_clipboard_text(self, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
        except GLib.Error:
            return
        if not text:
            return
        self.paste_with_check(text)

    def paste_with_check(self, text):
        multiline = "\n" in text.strip("\r\n") or "\r" in text.strip("\r\n")
        warn = self.settings.get("paste_warning") and multiline and not self.has_foreground_process()
        if warn and self.on_paste_confirm:
            self.on_paste_confirm(text, lambda: self.paste_text(text))
        else:
            self.paste_text(text)

    def run_command(self, command):
        """Type a command into the shell and press Enter."""
        data = (command.rstrip("\n") + "\r").encode()
        if self.spawned:
            self.feed_child(data)
        else:
            self._pending_input.append(data)
        self.grab_focus()

    def insert_text(self, text):
        self.paste_text(text)
        self.grab_focus()

    def _on_selection_changed(self, terminal):
        if self.settings.get("copy_on_select") and self.get_has_selection():
            self.copy_clipboard_format(Vte.Format.TEXT)

    # -- search --------------------------------------------------------------
    def search(self, text, backwards=True, case_sensitive=False, use_regex=False):
        if not text:
            self.search_set_regex(None, 0)
            return False
        flags = MATCH_FLAGS
        if not case_sensitive:
            flags |= PCRE2_CASELESS
        pattern = text if use_regex else GLib.Regex.escape_string(text)
        try:
            regex = Vte.Regex.new_for_search(pattern, -1, flags)
        except GLib.Error:
            return False
        self.search_set_regex(regex, 0)
        self.search_set_wrap_around(True)
        return self.search_find_previous() if backwards else self.search_find_next()

    def search_clear(self):
        self.search_set_regex(None, 0)

    # -- matches / links -----------------------------------------------------
    def _setup_matches(self):
        for pattern, kind in ((URL_RE, KIND_URL), (EMAIL_RE, KIND_EMAIL), (PATH_RE, KIND_PATH)):
            try:
                regex = Vte.Regex.new_for_match(pattern, -1, MATCH_FLAGS)
            except GLib.Error as exc:  # pragma: no cover
                print(f"termit: bad match regex ({kind}): {exc.message}")
                continue
            tag = self.match_add_regex(regex, 0)
            self.match_set_cursor_name(tag, "pointer")
            self._match_kinds[tag] = kind

    def link_at(self, x, y):
        """Return (uri, kind) under the pointer or None."""
        hyperlink = self.check_hyperlink_at(x, y)
        if hyperlink:
            return hyperlink, KIND_URL
        match, tag = self.check_match_at(x, y)
        if not match:
            return None
        kind = self._match_kinds.get(tag, KIND_URL)
        match = match.rstrip(_TRAILING_PUNCT)
        if kind == KIND_URL:
            if match.startswith("www."):
                match = "https://" + match
            return match, kind
        if kind == KIND_EMAIL:
            return "mailto:" + match, kind
        return match, kind

    def resolve_path(self, text):
        """Resolve a path match (with optional :line:col) relative to the shell cwd."""
        line = None
        m = re.match(r"^(.*?)(?::(\d+))?(?::(\d+))?$", text)
        if m:
            text, line = m.group(1), m.group(2)
        path = os.path.expanduser(text)
        if not os.path.isabs(path):
            info = self.foreground_info()
            base = (info[2] if info else "") or self.shell_cwd() or os.path.expanduser("~")
            path = os.path.join(base, path)
        path = os.path.normpath(path)
        if os.path.exists(path):
            return path, line
        return None, None

    def _setup_gestures(self):
        click = Gtk.GestureClick(button=1)
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click.connect("pressed", self._on_click)
        self.add_controller(click)

    def _on_click(self, gesture, n_press, x, y):
        state = gesture.get_current_event_state()
        if not state & Gdk.ModifierType.CONTROL_MASK:
            return
        link = self.link_at(x, y)
        if not link:
            return
        if self.open_link(*link):
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def open_link(self, uri, kind):
        if kind == KIND_PATH:
            path, _line = self.resolve_path(uri)
            if not path:
                return False
            uri = Gio.File.new_for_path(path).get_uri()
        if self.on_link_open:
            return bool(self.on_link_open(uri))
        return False

    # -- mouse wheel ---------------------------------------------------------
    def _setup_scrolling(self):
        """Scroll the history by a fixed number of lines per wheel step.

        VTE's own handler scales the step with the row count, which feels much
        faster than GNOME Terminal in tall windows. This capture-phase controller
        takes over plain wheel events while there is history to scroll and leaves
        everything else (alternate screen, modifiers, mouse-tracking apps) to VTE.
        """
        controller = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        controller.connect("scroll", self._on_scroll)
        controller.connect("scroll-end", lambda c: setattr(self, "_scroll_remainder", 0.0))
        self.add_controller(controller)

    def _on_scroll(self, controller, dx, dy):
        modifiers = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.ALT_MASK
        if controller.get_current_event_state() & modifiers:
            return False
        adjustment = self.get_vadjustment()
        scrollable = adjustment.get_upper() - adjustment.get_lower() - adjustment.get_page_size()
        if scrollable <= 0.5:
            return False  # nothing to scroll: alternate screen or no history yet
        if controller.get_unit() == Gdk.ScrollUnit.SURFACE:
            # Touchpad: GTK reports pixels. Move the history as far as the finger moved.
            speed = float(self.settings.get("touchpad_scroll_speed") or 1.0)
            self._scroll_remainder += dy / max(self.get_char_height(), 1) * speed
        else:
            # Mouse wheel: GTK reports clicks. Scroll a fixed number of lines per click.
            lines = max(1, int(self.settings.get("scroll_lines") or 3))
            self._scroll_remainder += dy * lines
        step = int(self._scroll_remainder)
        if step == 0:
            return True  # a touchpad fraction; wait until it adds up to a line
        self._scroll_remainder -= step
        lower = adjustment.get_lower()
        upper = adjustment.get_upper() - adjustment.get_page_size()
        adjustment.set_value(min(max(adjustment.get_value() + step, lower), upper))
        return True

    # -- context menu --------------------------------------------------------
    def _setup_actions(self):
        group = Gio.SimpleActionGroup()
        for name, cb in (("open-link", self._act_open_link), ("copy-link", self._act_copy_link)):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", cb)
            group.add_action(action)
        self.insert_action_group("term", group)

    def _act_open_link(self, *args):
        if self._context_link:
            self.open_link(*self._context_link)

    def _act_copy_link(self, *args):
        if self._context_link:
            uri, kind = self._context_link
            if kind == KIND_EMAIL:
                uri = uri[len("mailto:"):]
            self.get_clipboard().set(uri)

    def _on_setup_context_menu(self, terminal, context):
        self._context_link = None
        if context is not None:
            ok, x, y = context.get_coordinates()
            if ok:
                self._context_link = self.link_at(x, y)
        menu = Gio.Menu()
        if self._context_link:
            kind = self._context_link[1]
            section = Gio.Menu()
            section.append(
                {KIND_URL: _("Open Link"), KIND_EMAIL: _("Send Email"), KIND_PATH: _("Open File")}[kind],
                "term.open-link",
            )
            section.append(_("Copy Link"), "term.copy-link")
            menu.append_section(None, section)
        section = Gio.Menu()
        section.append(_("Copy"), "win.copy")
        section.append(_("Paste"), "win.paste")
        section.append(_("Select All"), "win.select-all")
        menu.append_section(None, section)
        section = Gio.Menu()
        section.append(_("Split Right"), "win.split-right")
        section.append(_("Split Down"), "win.split-down")
        section.append(_("Close Pane"), "win.close-pane")
        menu.append_section(None, section)
        section = Gio.Menu()
        section.append(_("New Tab Here"), "win.new-tab-here")
        section.append(_("Rename Tab…"), "win.rename-tab")
        section.append(_("Notes"), "win.toggle-notes")
        section.append(_("Clear Scrollback"), "win.clear-scrollback")
        menu.append_section(None, section)
        self.set_context_menu_model(menu)

    def clear_scrollback(self):
        self.reset(False, True)
