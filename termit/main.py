"""Application entry point."""

import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Vte", "3.91")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, __version__  # noqa: E402
from .dialogs import ShortcutsDialog, about_dialog  # noqa: E402
from .i18n import _  # noqa: E402
from .preferences import PreferencesDialog  # noqa: E402
from .settings import Settings  # noqa: E402
from .storage import NotesStore  # noqa: E402
from .window import TermitWindow  # noqa: E402

RESOURCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources")
DATA_ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "icons")


class TermitApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.settings = Settings()
        self.store = NotesStore()
        self._first_window = True
        self.add_main_option("working-directory", ord("w"), GLib.OptionFlags.NONE, GLib.OptionArg.STRING,
                             "Start the shell in DIR", "DIR")
        self.add_main_option("new-tab", ord("t"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Open a tab in the existing window instead of a new window", None)
        self.add_main_option("version", ord("v"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Show the version and exit", None)
        self.add_main_option(GLib.OPTION_REMAINING, 0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING_ARRAY,
                             "Command to run instead of the shell", "[-- COMMAND...]")

    # -- lifecycle -------------------------------------------------------------
    def do_startup(self):
        Adw.Application.do_startup(self)
        self._load_css()
        self._apply_color_scheme()
        self.settings.connect("changed", self._on_settings_changed)
        display = Gdk.Display.get_default()
        if display is not None and os.path.isdir(DATA_ICON_DIR):
            Gtk.IconTheme.get_for_display(display).add_search_path(DATA_ICON_DIR)
        Gtk.Window.set_default_icon_name(APP_ID)

        for name, callback in (
            ("new-window", lambda *a: self.new_window()),
            ("preferences", lambda *a: self._show_preferences()),
            ("shortcuts", lambda *a: ShortcutsDialog().present(self.get_active_window())),
            ("about", lambda *a: about_dialog(self.get_active_window())),
            ("quit", lambda *a: self.quit_all()),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
        focus = Gio.SimpleAction.new("focus-tab", GLib.VariantType("s"))
        focus.connect("activate", self._on_focus_tab)
        self.add_action(focus)

        self.set_accels_for_action("app.new-window", ["<Control><Shift>o"])
        self.set_accels_for_action("app.preferences", ["<Control><Shift>p", "<Control>comma"])
        self.set_accels_for_action("app.shortcuts", ["<Control>question"])
        self.set_accels_for_action("app.quit", ["<Control><Shift>q"])
        # Window accelerators are also registered here so menus show them.
        for accel, action, argument in TermitWindow.SHORTCUTS:
            if argument is None:
                existing = self.get_accels_for_action(action)
                self.set_accels_for_action(action, existing + [accel])

    def do_command_line(self, command_line):
        options = command_line.get_options_dict().end().unpack()
        if options.get("version"):
            print(f"termit {__version__}")
            return 0
        cwd = options.get("working-directory")
        if cwd:
            cwd = os.path.abspath(os.path.join(command_line.get_cwd() or os.getcwd(), cwd))
        command = options.get(GLib.OPTION_REMAINING) or None
        if command and command[0] == "--":
            command = command[1:]
        window = self.get_active_window()
        if window is not None and options.get("new-tab"):
            window.new_tab(cwd=cwd, argv=command)
            window.present()
        else:
            self.new_window(cwd=cwd, command=command)
        return 0

    def do_activate(self):
        window = self.get_active_window()
        if window is None:
            self.new_window()
        else:
            window.present()

    def new_window(self, cwd=None, command=None):
        restore = self._first_window and self.settings.get("restore_session") and not cwd and not command
        self._first_window = False
        window = TermitWindow(self, restore=restore, cwd=cwd, command=command)
        window.present()
        return window

    def _show_preferences(self):
        window = self.get_active_window()
        PreferencesDialog(window, self.settings).present(window)

    def quit_all(self):
        for window in list(self.get_windows()):
            window.close()

    # -- helpers ---------------------------------------------------------------
    def _load_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_path(os.path.join(RESOURCE_DIR, "style.css"))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _apply_color_scheme(self):
        scheme = {
            "system": Adw.ColorScheme.DEFAULT,
            "light": Adw.ColorScheme.FORCE_LIGHT,
            "dark": Adw.ColorScheme.FORCE_DARK,
        }.get(self.settings.get("color_scheme"), Adw.ColorScheme.DEFAULT)
        Adw.StyleManager.get_default().set_color_scheme(scheme)

    def _on_settings_changed(self, settings, key):
        if key == "color_scheme":
            self._apply_color_scheme()

    def notify_attention(self, window, session):
        notification = Gio.Notification.new(_("{title} needs your attention").format(title=session.display_title))
        notification.set_body(session.short_cwd or "")
        notification.set_default_action_and_target("app.focus-tab", GLib.Variant("s", session.id))
        self.send_notification(f"bell-{session.id}", notification)

    def _on_focus_tab(self, action, parameter):
        session_id = parameter.get_string()
        for window in self.get_windows():
            for session in window.sessions():
                if session.id == session_id:
                    window.select_session(session)
                    window.present()
                    return


def main(argv=None):
    app = TermitApplication()
    return app.run(sys.argv if argv is None else argv)
