"""Main application window."""

import os
import time

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from . import dialogs
from .i18n import _
from .notes import NotesPane
from .panes import PaneGroup
from .session import TAB_COLORS, TabSession
from .sidebar import Sidebar
from .terminal import TermitTerminal

POLL_INTERVAL_MS = 1000


class TermitWindow(Adw.ApplicationWindow):
    def __init__(self, app, restore=False, cwd=None, command=None):
        super().__init__(application=app)
        self.app = app
        self.settings = app.settings
        self.store = app.store
        self._sessions = []
        self._current = None
        self._closing = False
        self._paned_sync = False

        self.set_title("Termit")
        self.set_icon_name(app.get_application_id())
        self.set_default_size(int(self.settings.get("window_width")), int(self.settings.get("window_height")))
        if self.settings.get("window_maximized"):
            self.maximize()

        self._build_ui()
        self._build_actions()
        self._build_shortcuts()

        self.settings.connect("changed", self._on_settings_changed)
        Adw.StyleManager.get_default().connect("notify::dark", self._on_theme_changed)
        self.connect("close-request", self._on_close_request)
        self.connect("notify::is-active", self._on_active_changed)
        self.connect("notify::default-width", lambda *a: self._queue_geometry_save())
        self.connect("notify::default-height", lambda *a: self._queue_geometry_save())
        self.connect("notify::maximized", lambda *a: self._queue_geometry_save())
        self._geometry_source = 0

        restored = restore and self._restore_session()
        if not restored:
            self.new_tab(cwd=cwd, argv=command)
        GLib.timeout_add(POLL_INTERVAL_MS, self._poll_sessions)
        GLib.idle_add(self._apply_notes_position, True)

    # ------------------------------------------------------------------ UI --
    def _build_ui(self):
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        toolbar_view = Adw.ToolbarView()
        self.toast_overlay.set_child(toolbar_view)

        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        self.sidebar_button = Gtk.ToggleButton()
        self.sidebar_button.set_tooltip_text(_("Toggle Tab Sidebar (Ctrl+Shift+B)"))
        self.sidebar_button.set_active(bool(self.settings.get("sidebar_visible")))
        self.sidebar_button.connect("toggled", lambda b: self.settings.set("sidebar_visible", b.get_active()))
        header.pack_start(self.sidebar_button)

        new_tab_button = Gtk.Button.new_from_icon_name("tab-new-symbolic")
        new_tab_button.set_tooltip_text(_("New Tab (Ctrl+Shift+T)"))
        new_tab_button.set_action_name("win.new-tab")
        header.pack_start(new_tab_button)

        self.window_title = Adw.WindowTitle(title="Termit", subtitle="")
        header.set_title_widget(self.window_title)

        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.set_tooltip_text(_("Main Menu"))
        menu_button.set_menu_model(self._build_primary_menu())
        menu_button.set_primary(True)
        header.pack_end(menu_button)

        self.notes_button = Gtk.ToggleButton()
        self.notes_button.set_icon_name("document-edit-symbolic")
        self.notes_button.set_tooltip_text(_("Toggle Notes (Ctrl+Shift+N)"))
        self.notes_button.set_active(bool(self.settings.get("notes_visible")))
        self.notes_button.connect("toggled", lambda b: self.settings.set("notes_visible", b.get_active()))
        header.pack_end(self.notes_button)

        self.snippets_button = Gtk.MenuButton()
        self.snippets_button.set_icon_name("utilities-terminal-symbolic")
        self.snippets_button.set_tooltip_text(_("Snippets (Ctrl+Shift+S)"))
        self._rebuild_snippets_menu()
        header.pack_end(self.snippets_button)

        self.search_button = Gtk.ToggleButton()
        self.search_button.set_icon_name("edit-find-symbolic")
        self.search_button.set_tooltip_text(_("Find (Ctrl+Shift+F)"))
        header.pack_end(self.search_button)

        self.split_view = Adw.OverlaySplitView()
        self.split_view.set_min_sidebar_width(200)
        self.split_view.set_max_sidebar_width(360)
        self.split_view.set_sidebar_width_fraction(0.22)
        self.split_view.set_show_sidebar(bool(self.settings.get("sidebar_visible")))
        self.split_view.connect("notify::show-sidebar", self._on_split_sidebar_changed)
        toolbar_view.set_content(self.split_view)

        self.sidebar = Sidebar()
        self.sidebar.connect("tab-selected", lambda sb, s: self.select_session(s, focus=not sb.quiet_selection()))
        self.sidebar.connect("tab-activated", lambda sb, s: self.select_session(s))
        self.sidebar.connect("search-closed", lambda sb: self.focus_terminal())
        self.sidebar.connect("tab-close-requested", lambda sb, s: self.close_session(s))
        self.sidebar.connect("tab-reordered", lambda sb, s, i: self.save_session_state())
        self.split_view.set_sidebar(self.sidebar)
        self._apply_sidebar_position()

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.split_view.set_content(content)

        self.search_bar = Gtk.SearchBar()
        self.search_bar.set_show_close_button(True)
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(_("Find in terminal…"))
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.search_entry.connect("activate", lambda e: self.find(backwards=True))
        self.search_entry.connect("next-match", lambda e: self.find(backwards=False))
        self.search_entry.connect("previous-match", lambda e: self.find(backwards=True))
        self.search_entry.connect("stop-search", lambda e: self.search_button.set_active(False))
        search_box = Gtk.Box(spacing=6)
        search_box.append(self.search_entry)
        prev_btn = Gtk.Button.new_from_icon_name("go-up-symbolic")
        prev_btn.set_tooltip_text(_("Previous match"))
        prev_btn.connect("clicked", lambda b: self.find(backwards=True))
        next_btn = Gtk.Button.new_from_icon_name("go-down-symbolic")
        next_btn.set_tooltip_text(_("Next match"))
        next_btn.connect("clicked", lambda b: self.find(backwards=False))
        self.search_case = Gtk.ToggleButton(label="Aa")
        self.search_case.set_tooltip_text(_("Match case"))
        self.search_regex = Gtk.ToggleButton(label=".*")
        self.search_regex.set_tooltip_text(_("Regular expression"))
        for widget in (prev_btn, next_btn, self.search_case, self.search_regex):
            search_box.append(widget)
        self.search_bar.set_child(search_box)
        self.search_bar.connect_entry(self.search_entry)
        self.search_bar.set_key_capture_widget(None)
        content.append(self.search_bar)
        self.search_button.bind_property(
            "active", self.search_bar, "search-mode-enabled",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
        )
        self.search_bar.connect("notify::search-mode-enabled", self._on_search_mode)

        self.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.paned.set_vexpand(True)
        self.paned.set_shrink_start_child(False)
        self.paned.set_shrink_end_child(False)
        self.paned.set_resize_start_child(True)
        self.paned.set_resize_end_child(False)
        self.paned.connect("notify::position", self._on_paned_position)
        content.append(self.paned)

        self.stack = Gtk.Stack()
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.paned.set_start_child(self.stack)

        self.notes = NotesPane(self, self.store, self.settings)
        self.notes.set_visible(bool(self.settings.get("notes_visible")))
        self.paned.set_end_child(self.notes)

        self._update_sidebar_button_icon()

    def _build_primary_menu(self):
        menu = Gio.Menu()
        section = Gio.Menu()
        section.append(_("New Tab"), "win.new-tab")
        section.append(_("New Window"), "app.new-window")
        menu.append_section(None, section)
        section = Gio.Menu()
        section.append(_("Split Right"), "win.split-right")
        section.append(_("Split Down"), "win.split-down")
        section.append(_("Close Pane"), "win.close-pane")
        menu.append_section(None, section)
        section = Gio.Menu()
        section.append(_("Find…"), "win.find")
        section.append(_("Find Tab…"), "win.find-tab")
        section.append(_("Notes Archive…"), "win.notes-archive")
        section.append(_("Clear Scrollback"), "win.clear-scrollback")
        menu.append_section(None, section)
        section = Gio.Menu()
        section.append(_("Fullscreen"), "win.fullscreen")
        section.append(_("Preferences"), "app.preferences")
        section.append(_("Keyboard Shortcuts"), "app.shortcuts")
        section.append(_("About Termit"), "app.about")
        menu.append_section(None, section)
        section = Gio.Menu()
        section.append(_("Quit"), "app.quit")
        menu.append_section(None, section)
        return menu

    def _rebuild_snippets_menu(self):
        menu = Gio.Menu()
        section = Gio.Menu()
        snippets = self.settings.get("snippets") or []
        for index, snippet in enumerate(snippets):
            item = Gio.MenuItem.new(snippet.get("name") or snippet.get("command", ""), None)
            item.set_action_and_target_value("win.snippet", GLib.Variant("i", index))
            section.append_item(item)
        if not snippets:
            section.append(_("No snippets yet"), "win.none")
        menu.append_section(None, section)
        section = Gio.Menu()
        section.append(_("Manage Snippets…"), "app.preferences")
        menu.append_section(None, section)
        self.snippets_button.set_menu_model(menu)

    # ------------------------------------------------------------- actions --
    def _add_action(self, name, callback, parameter=None):
        action = Gio.SimpleAction.new(name, parameter)
        action.connect("activate", callback)
        self.add_action(action)
        return action

    def _build_actions(self):
        self._add_action("new-tab", lambda *a: self.new_tab())
        self._add_action("new-tab-here", lambda *a: self.new_tab(cwd=self._current_cwd()))
        self._add_action("duplicate-tab", lambda *a: self.new_tab(cwd=self._current_cwd()))
        self._add_action("close-tab", lambda *a: self.close_session(self._current))
        self._add_action("close-other-tabs", self._on_close_other_tabs)
        self._add_action("next-tab", lambda *a: self._cycle(1))
        self._add_action("prev-tab", lambda *a: self._cycle(-1))
        self._add_action("move-tab-up", lambda *a: self._move_current(-1))
        self._add_action("move-tab-down", lambda *a: self._move_current(1))
        self._add_action("switch-tab", self._on_switch_tab, GLib.VariantType("i"))
        self._add_action("rename-tab", self._on_rename_tab)
        self._add_action("set-tab-color", self._on_set_tab_color, GLib.VariantType("s"))
        self._add_action("copy", lambda *a: self._with_terminal(lambda t: t.copy()))
        self._add_action("paste", lambda *a: self._with_terminal(lambda t: t.paste()))
        self._add_action("select-all", lambda *a: self._with_terminal(lambda t: t.select_all()))
        self._add_action("clear-scrollback", lambda *a: self._with_terminal(lambda t: t.clear_scrollback()))
        self._add_action("find", lambda *a: self._open_search())
        self._add_action("find-next", lambda *a: self.find(backwards=False))
        self._add_action("find-prev", lambda *a: self.find(backwards=True))
        self._add_action("toggle-sidebar", lambda *a: self.settings.set(
            "sidebar_visible", not self.settings.get("sidebar_visible")))
        self._add_action("find-tab", lambda *a: self._find_tab())
        self._add_action("split-right", lambda *a: self.split_pane(Gtk.Orientation.HORIZONTAL))
        self._add_action("split-down", lambda *a: self.split_pane(Gtk.Orientation.VERTICAL))
        self._add_action("close-pane", lambda *a: self.close_pane())
        self._add_action("focus-pane", self._on_focus_pane, GLib.VariantType("s"))
        self._add_action("toggle-notes", lambda *a: self.toggle_notes())
        self._add_action("focus-notes", lambda *a: self.focus_notes())
        self._add_action("notes-archive", lambda *a: dialogs.ArchiveDialog(self, self.store).present(self))
        self._add_action("notes-timestamp", lambda *a: self.notes.insert_timestamp())
        self._add_action("notes-copy", self._on_notes_copy)
        self._add_action("notes-export", self._on_notes_export)
        self._add_action("notes-clear", self._on_notes_clear)
        self._add_action("snippet", self._on_snippet, GLib.VariantType("i"))
        self._add_action("snippets-menu", lambda *a: self.snippets_button.popup())
        self._add_action("zoom-in", lambda *a: self._zoom(1.1))
        self._add_action("zoom-out", lambda *a: self._zoom(1 / 1.1))
        self._add_action("zoom-reset", lambda *a: self._zoom(None))
        self._add_action("fullscreen", lambda *a: self.unfullscreen() if self.is_fullscreen() else self.fullscreen())

    SHORTCUTS = [
        ("<Control><Shift>t", "win.new-tab", None),
        ("<Control><Shift>w", "win.close-tab", None),
        ("<Control><Shift>d", "win.duplicate-tab", None),
        ("<Control>Page_Down", "win.next-tab", None),
        ("<Control>Page_Up", "win.prev-tab", None),
        ("<Control><Shift>Page_Up", "win.move-tab-up", None),
        ("<Control><Shift>Page_Down", "win.move-tab-down", None),
        ("F2", "win.rename-tab", None),
        ("<Control><Shift>c", "win.copy", None),
        ("<Control><Shift>v", "win.paste", None),
        ("<Control><Shift>a", "win.select-all", None),
        ("<Control><Shift>f", "win.find", None),
        ("<Control><Shift>g", "win.find-next", None),
        ("<Control><Shift>h", "win.find-prev", None),
        ("<Control><Shift>k", "win.clear-scrollback", None),
        ("<Control><Shift>b", "win.toggle-sidebar", None),
        ("<Control><Shift>l", "win.find-tab", None),
        ("<Control><Shift>n", "win.toggle-notes", None),
        ("<Control><Shift>e", "win.focus-notes", None),
        ("<Control><Shift>s", "win.snippets-menu", None),
        ("<Control>plus", "win.zoom-in", None),
        ("<Control>equal", "win.zoom-in", None),
        ("<Control>KP_Add", "win.zoom-in", None),
        ("<Control>minus", "win.zoom-out", None),
        ("<Control>KP_Subtract", "win.zoom-out", None),
        ("<Control>0", "win.zoom-reset", None),
        ("<Control>KP_0", "win.zoom-reset", None),
        ("F11", "win.fullscreen", None),
        ("<Control><Alt>r", "win.split-right", None),
        ("<Control><Alt>d", "win.split-down", None),
        ("<Control><Alt>w", "win.close-pane", None),
        ("<Alt>Left", "win.focus-pane", GLib.Variant("s", "left")),
        ("<Alt>Right", "win.focus-pane", GLib.Variant("s", "right")),
        ("<Alt>Up", "win.focus-pane", GLib.Variant("s", "up")),
        ("<Alt>Down", "win.focus-pane", GLib.Variant("s", "down")),
    ] + [(f"<Alt>{n}", "win.switch-tab", GLib.Variant("i", n)) for n in range(1, 10)]

    def _build_shortcuts(self):
        # Capture-phase controller so shortcuts win over the terminal widget.
        controller = Gtk.ShortcutController()
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        for accel, action, argument in self.SHORTCUTS:
            trigger = Gtk.ShortcutTrigger.parse_string(accel)
            if trigger is None:
                continue
            shortcut = Gtk.Shortcut.new(trigger, Gtk.NamedAction.new(action))
            if argument is not None:
                shortcut.set_arguments(argument)
            controller.add_shortcut(shortcut)
        self.add_controller(controller)

    # ----------------------------------------------------------- sessions --
    def sessions(self):
        return list(self._sessions)

    @property
    def current(self):
        return self._current

    def _current_cwd(self):
        if self._current is None:
            return None
        return self._current.cwd or self._current.terminal.shell_cwd() or None

    def new_tab(self, cwd=None, argv=None, session_id=None, custom_title=None, color=None, select=True,
                layout=None):
        if cwd is None and self.settings.get("new_tab_inherits_cwd"):
            cwd = self._current_cwd()
        if not cwd or not os.path.isdir(cwd):
            cwd = os.path.expanduser("~")

        panes = PaneGroup()
        session = TabSession(panes, sid=session_id)
        session.cwd = cwd
        session.custom_title = custom_title
        session.color = color if color in TAB_COLORS else None
        panes.connect("active-changed", self._on_active_pane_changed, session)
        panes.connect("terminal-removed", self._on_pane_removed, session)
        panes.connect("layout-changed", lambda g: (session.mark_changed(), self.save_session_state()))
        session.page = panes
        self.stack.add_named(panes, session.id)

        if self._current is not None and self._current in self._sessions:
            position = self._sessions.index(self._current) + 1
        else:
            position = len(self._sessions)
        self._sessions.insert(position, session)
        self.sidebar.add_session(session, position)
        if self.store.exists(session.id):
            self.store.mark_open(session.id)

        restored = False
        if layout and not argv:
            restored = panes.restore(layout, lambda pane_cwd: self._create_terminal(session, pane_cwd or cwd))
        if not restored:
            panes.add_terminal(self._create_terminal(session, cwd, argv))
        if select or self._current is None:
            self.select_session(session)
        self.save_session_state()
        return session

    def _create_terminal(self, session, cwd, argv=None):
        """Create, wire up and spawn a terminal that belongs to `session`."""
        terminal = TermitTerminal(self.settings)
        terminal.on_link_open = self._open_uri
        terminal.on_paste_confirm = lambda text, cont: dialogs.paste_warning_dialog(self, text, cont)
        terminal.connect("bell", self._on_bell, session)
        terminal.connect("contents-changed", self._on_contents_changed, session)
        terminal.connect("window-title-changed", self._on_title_changed, session)
        terminal.connect("child-exited", self._on_child_exited, session)
        terminal.connect("notify::current-directory-uri", self._on_cwd_uri, session)
        if not cwd or not os.path.isdir(cwd):
            cwd = os.path.expanduser("~")
        terminal.spawn(cwd=cwd, argv=argv, session_id=session.id)
        return terminal

    # -- split panes -----------------------------------------------------------
    def split_pane(self, orientation):
        session = self._current
        if session is None or session.terminal is None:
            return
        source = session.terminal
        info = source.foreground_info()
        cwd = (info[2] if info else "") or source.shell_cwd() or session.cwd
        terminal = self._create_terminal(session, cwd)
        session.panes.split(source, orientation, terminal)
        terminal.grab_focus()

    def close_pane(self):
        session = self._current
        if session is None or session.terminal is None:
            return
        if session.pane_count <= 1:
            self.close_session(session)
            return
        terminal = session.terminal
        if self.settings.get("confirm_close_running") and terminal.has_foreground_process():
            process = session.fg_process or _("a process")
            dialogs.confirm_dialog(
                self, _("Close this pane?"),
                _("“{process}” is still running in this pane.").format(process=process),
                _("Close Pane"), lambda: self._remove_pane(session, terminal),
            )
            return
        self._remove_pane(session, terminal)

    def _remove_pane(self, session, terminal):
        terminal.on_link_open = None
        terminal.on_paste_confirm = None
        if session.panes.remove(terminal):
            self._finish_close(session, keep_note=(self.settings.get("notes_on_close") != "delete"))

    def _on_active_pane_changed(self, panes, terminal, session):
        session.window_title = terminal.get_window_title() or ""
        self._refresh_session_process(session)
        if session is self._current:
            self._update_window_title()
            self.notes.refresh_title()

    def _on_pane_removed(self, panes, terminal, session):
        terminal.on_link_open = None
        terminal.on_paste_confirm = None

    def _on_focus_pane(self, action, parameter):
        if self._current is not None:
            self._current.panes.focus_direction(parameter.get_string())

    def select_session(self, session, focus=True):
        if session is None or session not in self._sessions:
            return
        self._current = session
        self.stack.set_visible_child(session.page)
        self.sidebar.select_session(session)
        session.activity = False
        session.attention = False
        session.mark_changed()
        self.notes.set_session(session)
        self._update_window_title()
        if self.search_bar.get_search_mode():
            self._on_search_changed(self.search_entry)
        if focus:
            self.focus_terminal()

    def focus_terminal(self):
        if self._current is not None and self._current.terminal is not None:
            self._current.terminal.grab_focus()

    def close_session(self, session, force=False):
        if session is None or session not in self._sessions:
            return
        if not force:
            running = session.any_running()
            if self.settings.get("confirm_close_tab") or (running and self.settings.get("confirm_close_running")):
                dialogs.confirm_dialog(
                    self, _("Close “{title}”?").format(title=session.display_title),
                    self._close_tab_body(session, running),
                    _("Close Tab"), lambda: self.close_session(session, force=True),
                )
                return
        self.notes.flush()
        self.notes.save_session_note(session)
        policy = self.settings.get("notes_on_close")
        has_note = bool(session.note_text().strip())
        if has_note and policy == "ask":
            dialogs.notes_on_close_dialog(
                self, session,
                lambda: self._finish_close(session, keep_note=True),
                lambda: self._finish_close(session, keep_note=False),
            )
            return
        self._finish_close(session, keep_note=(policy != "delete"))

    def _close_tab_body(self, session, running):
        parts = []
        if running:
            process = session.fg_process or next(
                (t.foreground_info()[1] for t in session.terminals if t.has_foreground_process()), None,
            ) or _("a process")
            parts.append(_("“{process}” is still running in this tab.").format(process=process))
        if session.note_text().strip():
            policy = self.settings.get("notes_on_close")
            if policy == "delete":
                parts.append(_("The tab's note will be deleted."))
            elif policy == "keep":
                parts.append(_("The tab's note is kept in the archive."))
        if not parts:
            parts.append(_("The shell in this tab will be terminated."))
        return " ".join(parts)

    def _finish_close(self, session, keep_note=True):
        if session not in self._sessions:
            return
        if keep_note:
            self.store.mark_closed(session.id)
        else:
            self.store.delete(session.id)
        index = self._sessions.index(session)
        self._sessions.remove(session)
        self.sidebar.remove_session(session)
        self.stack.remove(session.page)
        for terminal in session.terminals:
            terminal.on_link_open = None
            terminal.on_paste_confirm = None
        if self._current is session:
            self._current = None
            if self._sessions:
                self.select_session(self._sessions[min(index, len(self._sessions) - 1)])
            else:
                self.notes.set_session(None)
        self.save_session_state()
        if not self._sessions and not self._closing:
            self._closing = True
            if not self.settings.get("restore_session"):
                self.store.clear_session()
            self.close()

    def _on_close_other_tabs(self, *args):
        others = [s for s in self._sessions if s is not self._current]
        if not others:
            return
        running = [s for s in others if s.any_running()]
        if self.settings.get("confirm_close_tab") or (running and self.settings.get("confirm_close_running")):
            if running:
                body = _("{n} tabs have a running process.").format(n=len(running))
            else:
                body = _("{n} tabs will be closed.").format(n=len(others))
            dialogs.confirm_dialog(
                self, _("Close other tabs?"), body,
                _("Close Tabs"), lambda: [self.close_session(s, force=True) for s in others],
            )
            return
        for session in others:
            self.close_session(session, force=True)

    def _cycle(self, delta):
        if not self._sessions or self._current is None:
            return
        index = (self._sessions.index(self._current) + delta) % len(self._sessions)
        self.select_session(self._sessions[index])

    def _move_current(self, delta):
        if self._current is None:
            return
        index = self._sessions.index(self._current)
        new_index = max(0, min(index + delta, len(self._sessions) - 1))
        if new_index == index:
            return
        self._sessions.remove(self._current)
        self._sessions.insert(new_index, self._current)
        self.sidebar.move_session(self._current, new_index)

    def _sync_order_from_sidebar(self):
        self._sessions = self.sidebar.sessions()

    def _on_switch_tab(self, action, parameter):
        index = parameter.get_int32() - 1
        if 0 <= index < len(self._sessions):
            self.select_session(self._sessions[index])

    def _on_rename_tab(self, *args):
        if self._current is None:
            return
        session = self._current

        def done(title):
            session.custom_title = title
            session.mark_changed()
            self._update_window_title()
            self.notes.refresh_title()
            self.save_session_state()

        dialogs.rename_dialog(self, session, done)

    def _on_set_tab_color(self, action, parameter):
        if self._current is None:
            return
        color = parameter.get_string()
        self._current.color = color if color in TAB_COLORS else None
        self._current.mark_changed()
        self.save_session_state()

    def _with_terminal(self, func):
        if self._current is not None and self._current.terminal is not None:
            func(self._current.terminal)

    def _zoom(self, factor):
        if self._current is None:
            return
        for terminal in self._current.terminals:
            if factor is None:
                terminal.set_font_scale(1.0)
            else:
                terminal.set_font_scale(max(0.4, min(4.0, terminal.get_font_scale() * factor)))

    def _on_snippet(self, action, parameter):
        index = parameter.get_int32()
        snippets = self.settings.get("snippets") or []
        if self._current is None or not (0 <= index < len(snippets)):
            return
        snippet = snippets[index]
        command = snippet.get("command", "")
        if snippet.get("run"):
            self._current.terminal.run_command(command)
        else:
            self._current.terminal.insert_text(command)

    # ------------------------------------------------------ terminal events --
    def _on_bell(self, terminal, session):
        if session is not self._current or not self.is_active():
            session.attention = True
            session.mark_changed()
            if self.settings.get("bell_notification"):
                self.app.notify_attention(self, session)

    def _on_contents_changed(self, terminal, session):
        # Ignore the initial prompt of a freshly spawned shell.
        if time.time() - session.created < 2.0:
            return
        if session is not self._current and not session.activity:
            session.activity = True
            session.mark_changed()

    def _on_title_changed(self, terminal, session):
        if terminal is not session.terminal:
            return
        session.window_title = terminal.get_window_title() or ""
        session.mark_changed()
        if session is self._current:
            self._update_window_title()
            self.notes.refresh_title()

    def _on_cwd_uri(self, terminal, pspec, session):
        if terminal is not session.terminal:
            return
        uri = terminal.get_current_directory_uri()
        if uri:
            path = Gio.File.new_for_uri(uri).get_path()
            if path:
                self._set_session_cwd(session, path)

    def _on_child_exited(self, terminal, status, session):
        terminal.exited = True
        self._remove_pane(session, terminal)

    def _set_session_cwd(self, session, cwd):
        if cwd and cwd != session.cwd:
            session.cwd = cwd
            session.mark_changed()
            self.store.update_meta(session.id, cwd=cwd)
            if session is self._current:
                self._update_window_title()
                self.notes.update_banner()
            self.save_session_state()

    def _poll_sessions(self):
        for session in self._sessions:
            if self._refresh_session_process(session):
                session.mark_changed()
                if session is self._current:
                    self._update_window_title()
        return GLib.SOURCE_CONTINUE

    def _refresh_session_process(self, session):
        """Update the session's foreground process and folder. Returns True when something changed."""
        active = session.terminal
        if active is None:
            return False
        info = active.foreground_info()
        if not info:
            return False
        pid, comm, cwd = info
        if active.is_shell_idle(info):
            # Prefer a program running in another pane of the same tab.
            for terminal in session.terminals:
                if terminal is active:
                    continue
                other = terminal.foreground_info()
                if other and not terminal.is_shell_idle(other):
                    pid, comm, _cwd = other
                    break
            else:
                pid = None
        changed = False
        if pid is None:
            if session.fg_process is not None:
                session.fg_process = None
                session.fg_pid = None
                session.fg_since = None
                changed = True
        else:
            if session.fg_pid != pid:
                session.fg_pid = pid
                session.fg_since = time.time()
                changed = True
            if comm and session.fg_process != comm:
                session.fg_process = comm
                changed = True
            changed = True  # refresh the elapsed-time label
        if cwd and cwd != session.cwd:
            self._set_session_cwd(session, cwd)
            changed = True
        return changed

    def _update_window_title(self):
        if self._current is None:
            self.window_title.set_title("Termit")
            self.window_title.set_subtitle("")
            self.set_title("Termit")
            return
        title = self._current.display_title
        self.window_title.set_title(title)
        self.window_title.set_subtitle(self._current.short_cwd)
        self.set_title(f"{title} — Termit")

    def _open_uri(self, uri):
        def done(launcher, result):
            try:
                launcher.launch_finish(result)
            except GLib.Error as exc:
                self.toast(_("Could not open: {error}").format(error=exc.message))

        if uri.startswith("file://"):
            launcher = Gtk.FileLauncher.new(Gio.File.new_for_uri(uri))
        else:
            launcher = Gtk.UriLauncher.new(uri)
        launcher.launch(self, None, done)
        return True

    def _find_tab(self):
        if not self.settings.get("sidebar_visible"):
            self.settings.set("sidebar_visible", True)
        self.sidebar.show_search()

    # --------------------------------------------------------------- search --
    def _open_search(self):
        self.search_button.set_active(True)
        self.search_entry.grab_focus()
        self.search_entry.select_region(0, -1)

    def _on_search_mode(self, bar, pspec):
        if bar.get_search_mode():
            self.search_entry.grab_focus()
        else:
            self._with_terminal(lambda t: t.search_clear())
            self.focus_terminal()

    def _on_search_changed(self, entry):
        self.find(backwards=True)

    def find(self, backwards=True):
        if self._current is None:
            return
        text = self.search_entry.get_text()
        found = self._current.terminal.search(
            text, backwards=backwards,
            case_sensitive=self.search_case.get_active(),
            use_regex=self.search_regex.get_active(),
        )
        if text and not found:
            self.search_entry.add_css_class("error")
        else:
            self.search_entry.remove_css_class("error")

    # ---------------------------------------------------------------- notes --
    def toggle_notes(self):
        visible = not self.settings.get("notes_visible")
        self.settings.set("notes_visible", visible)
        if visible:
            self.notes.focus()
        else:
            self.focus_terminal()

    def focus_notes(self):
        if not self.settings.get("notes_visible"):
            self.settings.set("notes_visible", True)
        self.notes.focus()

    def _on_notes_copy(self, *args):
        text = self.notes.current_text()
        if text:
            self.get_clipboard().set(text)
            self.toast(_("Note copied to clipboard"))

    def _on_notes_clear(self, *args):
        dialogs.confirm_dialog(
            self, _("Clear this note?"), _("The note text is removed."), _("Clear"), self.notes.clear)

    def _on_notes_export(self, *args):
        text = self.notes.current_text()
        dialog = Gtk.FileDialog()
        name = (self._current.display_title if self._current else "notes").replace("/", "-")
        dialog.set_initial_name(f"{name}.md")

        def done(d, result):
            try:
                gfile = d.save_finish(result)
            except GLib.Error:
                return
            try:
                with open(gfile.get_path(), "w", encoding="utf-8") as fh:
                    fh.write(text)
                self.toast(_("Note exported"))
            except OSError as exc:
                self.toast(_("Could not export: {error}").format(error=exc))

        dialog.save(self, None, done)

    def open_archived_note(self, nid, entry):
        cwd = entry.get("cwd") or None
        self.new_tab(cwd=cwd, session_id=nid, custom_title=entry.get("title"))

    def toast(self, text):
        self.toast_overlay.add_toast(Adw.Toast.new(text))

    # --------------------------------------------------------------- layout --
    def _apply_sidebar_position(self):
        position = Gtk.PackType.END if self.settings.get("sidebar_position") == "right" else Gtk.PackType.START
        self.split_view.set_sidebar_position(position)
        self._update_sidebar_button_icon()

    def _update_sidebar_button_icon(self):
        right = self.settings.get("sidebar_position") == "right"
        self.sidebar_button.set_icon_name("sidebar-show-right-symbolic" if right else "sidebar-show-symbolic")

    def _apply_notes_position(self, initial=False):
        bottom = self.settings.get("notes_position") == "bottom"
        self.paned.set_orientation(Gtk.Orientation.VERTICAL if bottom else Gtk.Orientation.HORIZONTAL)
        self.notes.remove_css_class("notes-right")
        self.notes.remove_css_class("notes-bottom")
        self.notes.add_css_class("notes-bottom" if bottom else "notes-right")
        self._restore_paned_position()
        return GLib.SOURCE_REMOVE

    def _paned_total(self):
        if self.paned.get_orientation() == Gtk.Orientation.VERTICAL:
            return self.paned.get_height()
        return self.paned.get_width()

    def _restore_paned_position(self):
        total = self._paned_total()
        if total <= 0 or not self.notes.get_visible():
            return
        size = min(int(self.settings.get("notes_size")), total // 2)
        self._paned_sync = True
        self.paned.set_position(max(100, total - size))
        self._paned_sync = False

    def _on_paned_position(self, paned, pspec):
        if self._paned_sync or not self.notes.get_visible():
            return
        total = self._paned_total()
        if total <= 0:
            return
        size = total - paned.get_position()
        if size > 60:
            self.settings.set("notes_size", size)

    def _on_split_sidebar_changed(self, view, pspec):
        if view.get_show_sidebar() != self.settings.get("sidebar_visible"):
            self.settings.set("sidebar_visible", view.get_show_sidebar())

    def _on_settings_changed(self, settings, key):
        if key == "sidebar_visible":
            visible = settings.get(key)
            self.split_view.set_show_sidebar(visible)
            if self.sidebar_button.get_active() != visible:
                self.sidebar_button.set_active(visible)
        elif key == "sidebar_position":
            self._apply_sidebar_position()
        elif key == "notes_visible":
            visible = settings.get(key)
            self.notes.set_visible(visible)
            if self.notes_button.get_active() != visible:
                self.notes_button.set_active(visible)
            if visible:
                GLib.idle_add(self._restore_paned_position)
        elif key == "notes_position":
            self._apply_notes_position()
        elif key == "snippets":
            self._rebuild_snippets_menu()

    def _on_theme_changed(self, manager, pspec):
        for session in self._sessions:
            for terminal in session.terminals:
                terminal.apply_colors(manager.get_dark())

    def _on_active_changed(self, window, pspec):
        if self.is_active() and self._current is not None and self._current.attention:
            self._current.attention = False
            self._current.mark_changed()

    def _queue_geometry_save(self):
        if self._geometry_source:
            GLib.source_remove(self._geometry_source)
        self._geometry_source = GLib.timeout_add(500, self._save_geometry)

    def _save_geometry(self):
        self._geometry_source = 0
        if not self.is_maximized() and not self.is_fullscreen():
            width, height = self.get_default_size()
            if width > 0 and height > 0:
                self.settings.set("window_width", width)
                self.settings.set("window_height", height)
        self.settings.set("window_maximized", self.is_maximized())
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------- session state --
    def save_session_state(self):
        if self._closing:
            return
        self._sync_order_from_sidebar()
        data = {
            "tabs": [s.to_dict() for s in self._sessions],
            "selected": self._sessions.index(self._current) if self._current in self._sessions else 0,
        }
        self.store.save_session(data)

    def _restore_session(self):
        data = self.store.load_session()
        if not data or not data.get("tabs"):
            return False
        restored = []
        for tab in data["tabs"]:
            if not isinstance(tab, dict):
                continue
            session = self.new_tab(
                cwd=tab.get("cwd"), session_id=tab.get("id"), custom_title=tab.get("custom_title"),
                color=tab.get("color"), select=False, layout=tab.get("layout"),
            )
            restored.append(session)
        if not restored:
            return False
        index = data.get("selected", 0)
        if not isinstance(index, int) or not (0 <= index < len(restored)):
            index = 0
        self.select_session(restored[index])
        return True

    def _on_close_request(self, window):
        if self._closing:
            return False
        running = [s for s in self._sessions if s.any_running()]
        if running and self.settings.get("confirm_close_running"):
            dialogs.confirm_dialog(
                self, _("Close the window?"),
                _("{n} tabs still have a running process.").format(n=len(running)),
                _("Close Window"), self._force_close,
            )
            return True
        self._prepare_close()
        return False

    def _force_close(self):
        self._prepare_close()
        self._closing = True
        self.close()

    def _prepare_close(self):
        self.notes.flush()
        self.settings.save()
        if self.settings.get("restore_session"):
            self.save_session_state()
        else:
            for session in self._sessions:
                self.store.mark_closed(session.id)
            self.store.clear_session()
        self._closing = True
