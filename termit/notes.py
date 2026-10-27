"""Notes pane: a per-tab note plus a global scratchpad."""

import datetime

from gi.repository import Adw, Gdk, GLib, Gtk, Pango

from .i18n import _

AUTOSAVE_DELAY_MS = 800


class NotesPane(Gtk.Box):
    """Editor for the active tab's note or the global scratchpad."""

    def __init__(self, window, store, settings):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.store = store
        self.settings = settings
        self.session = None
        self.mode = "tab"  # tab | global
        self._save_source = 0
        self._dirty_buffers = set()
        self.add_css_class("notes-pane")

        self.global_buffer = Gtk.TextBuffer()
        self.global_buffer.set_enable_undo(True)
        self.global_buffer.set_text(self.store.global_read())
        self.global_buffer.connect("changed", self._on_buffer_changed)

        header = Gtk.Box(spacing=6)
        header.add_css_class("notes-header")
        self.append(header)

        self.mode_tab = Gtk.ToggleButton(label=_("This Tab"))
        self.mode_tab.set_active(True)
        self.mode_global = Gtk.ToggleButton(label=_("Global"))
        self.mode_global.set_group(self.mode_tab)
        mode_box = Gtk.Box()
        mode_box.add_css_class("linked")
        mode_box.append(self.mode_tab)
        mode_box.append(self.mode_global)
        self.mode_tab.connect("toggled", self._on_mode_toggled)
        header.append(mode_box)

        self.title_label = Gtk.Label(xalign=0)
        self.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.title_label.set_hexpand(True)
        self.title_label.add_css_class("dim-label")
        header.append(self.title_label)

        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("view-more-symbolic")
        menu_button.add_css_class("flat")
        menu_button.set_menu_model(self._build_menu())
        header.append(menu_button)

        close = Gtk.Button.new_from_icon_name("window-close-symbolic")
        close.add_css_class("flat")
        close.set_tooltip_text(_("Hide Notes"))
        close.set_action_name("win.toggle-notes")
        header.append(close)

        self.banner = Adw.Banner()
        self.banner.set_button_label(_("Restore"))
        self.banner.connect("button-clicked", self._on_restore_archived)
        self.append(self.banner)
        self._banner_note_id = None

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        self.append(scroller)

        self.view = Gtk.TextView()
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_left_margin(12)
        self.view.set_right_margin(12)
        self.view.set_top_margin(10)
        self.view.set_bottom_margin(10)
        self.view.add_css_class("notes-text")
        scroller.set_child(self.view)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.view.add_controller(keys)

        footer = Gtk.Box(spacing=6)
        footer.add_css_class("notes-footer")
        self.status = Gtk.Label(xalign=0)
        self.status.add_css_class("dim-label")
        self.status.add_css_class("caption")
        self.status.set_hexpand(True)
        footer.append(self.status)
        self.counter = Gtk.Label()
        self.counter.add_css_class("dim-label")
        self.counter.add_css_class("caption")
        footer.append(self.counter)
        self.append(footer)

        self.settings.connect("changed", self._on_settings_changed)
        self._apply_font()
        self._show_buffer()

    # -- menu -----------------------------------------------------------------
    def _build_menu(self):
        from gi.repository import Gio

        menu = Gio.Menu()
        section = Gio.Menu()
        section.append(_("Insert Timestamp"), "win.notes-timestamp")
        section.append(_("Copy Note"), "win.notes-copy")
        section.append(_("Export Note…"), "win.notes-export")
        menu.append_section(None, section)
        section = Gio.Menu()
        section.append(_("Notes Archive…"), "win.notes-archive")
        section.append(_("Clear Note"), "win.notes-clear")
        menu.append_section(None, section)
        return menu

    # -- session handling ----------------------------------------------------
    def set_session(self, session):
        if self.session is session:
            self.refresh_title()
            return
        self.flush()
        self.session = session
        if session is not None and not getattr(session, "_note_loaded", False):
            session._note_loaded = True
            text = self.store.read(session.id)
            if text:
                session.note_buffer.set_text(text)
            session.note_buffer.connect("changed", self._on_buffer_changed)
        self._show_buffer()

    def _current_buffer(self):
        if self.mode == "global":
            return self.global_buffer
        return self.session.note_buffer if self.session else None

    def _show_buffer(self):
        buffer = self._current_buffer()
        if buffer is None:
            buffer = Gtk.TextBuffer()
            self.view.set_sensitive(False)
        else:
            self.view.set_sensitive(True)
        self.view.set_buffer(buffer)
        self.refresh_title()
        self._update_counter()
        self.update_banner()

    def refresh_title(self):
        if self.mode == "global":
            self.title_label.set_text(_("Global scratchpad"))
        elif self.session is not None:
            self.title_label.set_text(self.session.display_title)
        else:
            self.title_label.set_text("")

    def _on_mode_toggled(self, button):
        self.mode = "tab" if button.get_active() else "global"
        self._show_buffer()
        self.view.grab_focus()

    def _on_key(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.flush()
            self.window.focus_terminal()
            return True
        if keyval in (Gdk.KEY_s, Gdk.KEY_S) and state & Gdk.ModifierType.CONTROL_MASK:
            self.flush()
            self.status.set_text(_("Saved"))
            return True
        return False

    # -- archive banner --------------------------------------------------------
    def update_banner(self):
        self._banner_note_id = None
        if self.mode != "tab" or self.session is None or not self.session.cwd:
            self.banner.set_revealed(False)
            return
        candidates = [nid for nid in self.store.archived_for_cwd(self.session.cwd) if nid != self.session.id]
        if not candidates:
            self.banner.set_revealed(False)
            return
        self._banner_note_id = candidates[0]
        entry = self.store.index.get(candidates[0], {})
        when = (entry.get("updated") or "")[:10]
        self.banner.set_title(_("An archived note exists for this folder") + (f" ({when})" if when else ""))
        self.banner.set_revealed(True)

    def _on_restore_archived(self, banner):
        nid = self._banner_note_id
        if not nid or self.session is None:
            return
        self.restore_archived(nid, self.session)

    def restore_archived(self, nid, session):
        """Merge an archived note into a session's note and remove the archive entry."""
        text = self.store.read(nid)
        current = session.note_text()
        if current.strip():
            merged = current.rstrip("\n") + "\n\n---\n\n" + text
        else:
            merged = text
        session.note_buffer.set_text(merged)
        self.store.delete(nid)
        self.flush()
        self.update_banner()
        self.window.toast(_("Archived note restored"))

    # -- saving ------------------------------------------------------------
    def _on_buffer_changed(self, buffer):
        self._dirty_buffers.add(buffer)
        self._update_counter()
        self.status.set_text(_("Editing…"))
        if self._save_source:
            GLib.source_remove(self._save_source)
        self._save_source = GLib.timeout_add(AUTOSAVE_DELAY_MS, self._autosave)

    def _autosave(self):
        self._save_source = 0
        self.flush()
        return GLib.SOURCE_REMOVE

    def flush(self):
        """Write every modified buffer to disk."""
        if self._save_source:
            GLib.source_remove(self._save_source)
            self._save_source = 0
        if not self._dirty_buffers:
            return
        for buffer in list(self._dirty_buffers):
            if buffer is self.global_buffer:
                start, end = buffer.get_bounds()
                self.store.global_write(buffer.get_text(start, end, True))
            else:
                session = self._session_for_buffer(buffer)
                if session is not None:
                    self.store.write(session.id, session.note_text(), session.display_title, session.cwd)
        self._dirty_buffers.clear()
        self.status.set_text(_("Saved") + " · " + datetime.datetime.now().strftime("%H:%M"))

    def _session_for_buffer(self, buffer):
        if self.session is not None and self.session.note_buffer is buffer:
            return self.session
        for session in self.window.sessions():
            if session.note_buffer is buffer:
                return session
        return None

    def save_session_note(self, session):
        """Flush a specific session (used when a tab is closed)."""
        if session.note_buffer in self._dirty_buffers:
            self.store.write(session.id, session.note_text(), session.display_title, session.cwd)
            self._dirty_buffers.discard(session.note_buffer)

    def _update_counter(self):
        buffer = self._current_buffer()
        if buffer is None:
            self.counter.set_text("")
            return
        start, end = buffer.get_bounds()
        text = buffer.get_text(start, end, True)
        words = len(text.split())
        self.counter.set_text(_("{words} words · {chars} chars").format(words=words, chars=len(text)))

    # -- actions used by the window --------------------------------------------
    def insert_timestamp(self):
        buffer = self._current_buffer()
        if buffer is None:
            return
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        buffer.insert_at_cursor(f"[{stamp}] ")
        self.view.grab_focus()

    def current_text(self):
        buffer = self._current_buffer()
        if buffer is None:
            return ""
        start, end = buffer.get_bounds()
        return buffer.get_text(start, end, True)

    def clear(self):
        buffer = self._current_buffer()
        if buffer is not None:
            buffer.set_text("")

    def focus(self):
        self.view.grab_focus()

    def _apply_font(self):
        if self.settings.get("notes_monospace"):
            self.view.add_css_class("monospace")
        else:
            self.view.remove_css_class("monospace")

    def _on_settings_changed(self, settings, key):
        if key == "notes_monospace":
            self._apply_font()
