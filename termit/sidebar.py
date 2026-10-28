"""Vertical tab list shown at the left or right edge of the window."""

from gi.repository import Gdk, Gio, GLib, GObject, Gtk

from .i18n import _
from .session import TAB_COLORS


class TabRow(Gtk.ListBoxRow):
    """One row in the sidebar representing a tab session."""

    def __init__(self, session):
        super().__init__()
        self.session = session
        self.add_css_class("tab-row")
        session.row = self

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(6)
        box.set_margin_end(2)
        self.set_child(box)

        self.color_dot = Gtk.Box()
        self.color_dot.add_css_class("color-dot")
        self.color_dot.set_valign(Gtk.Align.CENTER)
        self.color_dot.set_visible(False)
        box.append(self.color_dot)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        text_box.set_hexpand(True)
        text_box.set_valign(Gtk.Align.CENTER)
        box.append(text_box)

        self.title = Gtk.Label(xalign=0)
        self.title.set_ellipsize(3)  # Pango.EllipsizeMode.END
        self.title.add_css_class("tab-title")
        text_box.append(self.title)

        sub_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        text_box.append(sub_box)
        self.subtitle = Gtk.Label(xalign=0)
        self.subtitle.set_ellipsize(1)  # Pango.EllipsizeMode.START
        self.subtitle.set_hexpand(True)
        self.subtitle.add_css_class("tab-sub")
        sub_box.append(self.subtitle)
        self.process = Gtk.Label()
        self.process.add_css_class("pill")
        self.process.set_visible(False)
        sub_box.append(self.process)

        self.status_dot = Gtk.Box()
        self.status_dot.add_css_class("status-dot")
        self.status_dot.set_valign(Gtk.Align.CENTER)
        self.status_dot.set_visible(False)
        box.append(self.status_dot)

        self.close_button = Gtk.Button.new_from_icon_name("window-close-symbolic")
        self.close_button.add_css_class("flat")
        self.close_button.add_css_class("circular")
        self.close_button.add_css_class("tab-close")
        self.close_button.set_valign(Gtk.Align.CENTER)
        self.close_button.set_tooltip_text(_("Close Tab"))
        box.append(self.close_button)

        session.connect("changed", lambda *_a: self.refresh())
        self.refresh()

    def refresh(self):
        s = self.session
        if self._sidebar_filtering():
            self.changed()  # re-evaluate the search filter for this row
        self.title.set_text(s.display_title)
        self.title.set_tooltip_text(s.window_title or s.display_title)
        self.subtitle.set_text(s.short_cwd or "")
        self.subtitle.set_tooltip_text(s.cwd or "")
        label = s.process_label
        self.process.set_text(label)
        self.process.set_visible(bool(label))

        for color in TAB_COLORS:
            self.color_dot.remove_css_class(color)
        if s.color in TAB_COLORS:
            self.color_dot.add_css_class(s.color)
            self.color_dot.set_visible(True)
        else:
            self.color_dot.set_visible(False)

        self.status_dot.set_visible(s.activity or s.attention)
        if s.attention:
            self.status_dot.add_css_class("attention")
        else:
            self.status_dot.remove_css_class("attention")


    def _sidebar_filtering(self):
        sidebar = self.get_ancestor(Sidebar)
        return sidebar is not None and sidebar.search_active()

    def matches(self, tokens):
        s = self.session
        haystack = " ".join((
            s.display_title, s.window_title or "", s.short_cwd, s.cwd, s.fg_process or "", s.note_text(),
        )).lower()
        return all(token in haystack for token in tokens)


class Sidebar(Gtk.Box):
    __gsignals__ = {
        "tab-selected": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "tab-close-requested": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "tab-reordered": (GObject.SignalFlags.RUN_FIRST, None, (object, int)),
        "tab-activated": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "search-closed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("sidebar-pane")
        self._selecting = False
        self._quiet_select = False

        new_tab = Gtk.Button()
        new_tab.set_action_name("win.new-tab")
        new_tab.add_css_class("flat")
        new_tab.add_css_class("new-tab-button")
        content = Gtk.Box(spacing=8)
        content.append(Gtk.Image.new_from_icon_name("tab-new-symbolic"))
        content.append(Gtk.Label(label=_("New Tab"), xalign=0, hexpand=True))
        shortcut = Gtk.Label(label="Ctrl+Shift+T")
        shortcut.add_css_class("dim-label")
        shortcut.add_css_class("caption")
        content.append(shortcut)
        new_tab.set_child(content)
        new_tab.set_hexpand(True)

        header = Gtk.Box(spacing=2)
        header.set_margin_top(6)
        header.set_margin_start(6)
        header.set_margin_end(6)
        header.append(new_tab)
        self.search_button = Gtk.ToggleButton()
        self.search_button.set_icon_name("edit-find-symbolic")
        self.search_button.add_css_class("flat")
        self.search_button.set_tooltip_text(_("Find Tab (Ctrl+Shift+L)"))
        self.search_button.connect("toggled", self._on_search_toggled)
        header.append(self.search_button)
        self.append(header)

        self.search_revealer = Gtk.Revealer()
        self.search_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(_("Filter tabs…"))
        self.search_entry.set_margin_start(6)
        self.search_entry.set_margin_end(6)
        self.search_entry.set_margin_top(4)
        self.search_entry.set_margin_bottom(2)
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.search_entry.connect("activate", self._on_search_activate)
        self.search_entry.connect("stop-search", lambda e: self.hide_search())
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_search_key)
        self.search_entry.add_controller(keys)
        self.search_revealer.set_child(self.search_entry)
        self.append(self.search_revealer)
        self._tokens = []

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        self.append(scroller)

        self.list = Gtk.ListBox()
        self.list.add_css_class("navigation-sidebar")
        self.list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list.connect("row-selected", self._on_row_selected)
        self.list.set_filter_func(self._filter_row)
        scroller.set_child(self.list)

        drop = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        drop.connect("enter", self._on_drag_motion)
        drop.connect("motion", self._on_drag_motion)
        drop.connect("leave", lambda *_a: self._clear_drop_indicator())
        drop.connect("drop", self._on_drop)
        self.list.add_controller(drop)
        self._indicator_row = None

        footer = Gtk.Box(spacing=4)
        footer.set_margin_start(6)
        footer.set_margin_end(6)
        footer.set_margin_bottom(6)
        footer.set_margin_top(2)
        archive = Gtk.Button()
        archive.set_action_name("win.notes-archive")
        archive.add_css_class("flat")
        archive_content = Gtk.Box(spacing=8)
        archive_content.append(Gtk.Image.new_from_icon_name("document-open-recent-symbolic"))
        archive_content.append(Gtk.Label(label=_("Notes Archive"), xalign=0, hexpand=True))
        archive.set_child(archive_content)
        archive.set_hexpand(True)
        footer.append(archive)
        self.append(footer)

    # -- rows ----------------------------------------------------------------
    def rows(self):
        rows = []
        index = 0
        while True:
            row = self.list.get_row_at_index(index)
            if row is None:
                return rows
            rows.append(row)
            index += 1

    def sessions(self):
        return [row.session for row in self.rows()]

    def add_session(self, session, position=None):
        row = TabRow(session)
        row.close_button.connect("clicked", lambda *_a: self.emit("tab-close-requested", session))
        self._attach_menu(row)
        self._attach_drag(row)
        self.list.insert(row, -1 if position is None else position)
        return row

    def remove_session(self, session):
        if session.row is not None:
            self.list.remove(session.row)
            session.row = None

    def select_session(self, session):
        if session.row is not None and self.list.get_selected_row() is not session.row:
            self.list.select_row(session.row)

    def selected_session(self):
        row = self.list.get_selected_row()
        return row.session if row else None

    def index_of(self, session):
        return session.row.get_index() if session.row is not None else -1

    def move_session(self, session, new_index):
        rows = self.rows()
        if session.row is None or not rows:
            return
        new_index = max(0, min(new_index, len(rows) - 1))
        old_index = session.row.get_index()
        if old_index == new_index:
            return
        self._selecting = True
        self.list.remove(session.row)
        self.list.insert(session.row, new_index)
        self.list.select_row(session.row)
        self._selecting = False
        self.emit("tab-reordered", session, new_index)

    def _on_row_selected(self, listbox, row):
        if row is not None and not self._selecting:
            self.emit("tab-selected", row.session)

    def quiet_selection(self):
        """True while the search entry is driving the selection."""
        return self._quiet_select

    # -- search / filter -------------------------------------------------------
    def search_active(self):
        return bool(self._tokens)

    def show_search(self):
        self.search_button.set_active(True)
        self.search_entry.grab_focus()
        self.search_entry.select_region(0, -1)

    def hide_search(self):
        self.search_button.set_active(False)

    def _on_search_toggled(self, button):
        active = button.get_active()
        self.search_revealer.set_reveal_child(active)
        if active:
            self.search_entry.grab_focus()
        else:
            self.search_entry.set_text("")
            self._apply_filter("")
            self.emit("search-closed")

    def _on_search_changed(self, entry):
        self._apply_filter(entry.get_text())

    def _apply_filter(self, text):
        self._tokens = [t for t in text.lower().split() if t]
        self.list.invalidate_filter()
        if self._tokens:
            visible = self.visible_rows()
            selected = self.list.get_selected_row()
            if visible and (selected is None or selected not in visible):
                self._select_quietly(visible[0])

    def _filter_row(self, row):
        return not self._tokens or row.matches(self._tokens)

    def visible_rows(self):
        return [row for row in self.rows() if self._filter_row(row)]

    def _select_quietly(self, row):
        """Select a row without the window stealing focus from the search entry."""
        self._quiet_select = True
        self.list.select_row(row)
        self._quiet_select = False

    def _on_search_key(self, controller, keyval, keycode, state):
        if keyval not in (Gdk.KEY_Up, Gdk.KEY_Down):
            return False
        visible = self.visible_rows()
        if not visible:
            return True
        selected = self.list.get_selected_row()
        index = visible.index(selected) if selected in visible else -1
        index = (index + (1 if keyval == Gdk.KEY_Down else -1)) % len(visible)
        self._select_quietly(visible[index])
        return True

    def _on_search_activate(self, entry):
        selected = self.list.get_selected_row()
        visible = self.visible_rows()
        if selected not in visible and visible:
            selected = visible[0]
        self.hide_search()
        if selected is not None:
            self.emit("tab-activated", selected.session)

    # -- context menu ----------------------------------------------------------
    def _attach_menu(self, row):
        gesture = Gtk.GestureClick(button=3)
        gesture.connect("pressed", lambda g, *_a: g.set_state(Gtk.EventSequenceState.CLAIMED))
        # Open the menu on release: opening it on press would place the first
        # item under the pointer and the release would activate it immediately.
        gesture.connect("released", self._on_row_right_click, row)
        row.add_controller(gesture)

    def _on_row_right_click(self, gesture, n_press, x, y, row):
        self.list.select_row(row)
        menu = Gio.Menu()
        section = Gio.Menu()
        section.append(_("Rename Tab…"), "win.rename-tab")
        section.append(_("Duplicate Tab"), "win.duplicate-tab")
        colors = Gio.Menu()
        colors.append(_("None"), "win.set-tab-color::none")
        for color in TAB_COLORS:
            colors.append(_(color.capitalize()), f"win.set-tab-color::{color}")
        section.append_submenu(_("Color"), colors)
        menu.append_section(None, section)
        section = Gio.Menu()
        section.append(_("Move Up"), "win.move-tab-up")
        section.append(_("Move Down"), "win.move-tab-down")
        menu.append_section(None, section)
        section = Gio.Menu()
        section.append(_("Close Other Tabs"), "win.close-other-tabs")
        section.append(_("Close Tab"), "win.close-tab")
        menu.append_section(None, section)

        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(row)
        popover.set_has_arrow(False)
        popover.set_pointing_to(Gdk.Rectangle(x=int(x), y=int(y), width=1, height=1))
        popover.connect("closed", lambda p: GLib.idle_add(p.unparent))
        popover.popup()

    # -- drag and drop reordering ------------------------------------------
    def _attach_drag(self, row):
        source = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        source.connect("prepare", self._on_drag_prepare, row)
        source.connect("drag-begin", self._on_drag_begin, row)
        source.connect("drag-end", self._on_drag_end, row)
        row.add_controller(source)

    def _on_drag_prepare(self, source, x, y, row):
        self._drag_hotspot = (int(x), int(y))
        value = GObject.Value(GObject.TYPE_STRING, row.session.id)
        return Gdk.ContentProvider.new_for_value(value)

    def _on_drag_begin(self, source, drag, row):
        paintable = Gtk.WidgetPaintable.new(row)
        hx, hy = getattr(self, "_drag_hotspot", (0, 0))
        source.set_icon(paintable, hx, hy)
        row.add_css_class("dragging")

    def _on_drag_end(self, source, drag, delete_data, row):
        row.remove_css_class("dragging")
        self._clear_drop_indicator()

    def _drop_position(self, y):
        """Return (insert index, row to mark, mark below?) for a pointer y in the list."""
        rows = self.rows()
        row = self.list.get_row_at_y(int(y))
        if row is None or not rows:
            return len(rows), rows[-1] if rows else None, True
        ok, bounds = row.compute_bounds(self.list)
        top = bounds.get_y() if ok else 0
        below = (y - top) > row.get_height() / 2
        return row.get_index() + (1 if below else 0), row, below

    def _clear_drop_indicator(self):
        if self._indicator_row is not None:
            self._indicator_row.remove_css_class("drop-before")
            self._indicator_row.remove_css_class("drop-after")
            self._indicator_row = None

    def _on_drag_motion(self, target, x, y):
        _index, row, below = self._drop_position(y)
        if row is not self._indicator_row:
            self._clear_drop_indicator()
        if row is not None:
            row.remove_css_class("drop-before")
            row.remove_css_class("drop-after")
            row.add_css_class("drop-after" if below else "drop-before")
            self._indicator_row = row
        return Gdk.DragAction.MOVE

    def _on_drop(self, target, value, x, y):
        self._clear_drop_indicator()
        session_id = str(value)
        dragged = next((s for s in self.sessions() if s.id == session_id), None)
        if dragged is None:
            return False
        insert_index, _row, _below = self._drop_position(y)
        old_index = self.index_of(dragged)
        if old_index < insert_index:
            insert_index -= 1
        self.move_session(dragged, insert_index)
        return True
