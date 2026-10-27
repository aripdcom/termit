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


class Sidebar(Gtk.Box):
    __gsignals__ = {
        "tab-selected": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "tab-close-requested": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "tab-reordered": (GObject.SignalFlags.RUN_FIRST, None, (object, int)),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("sidebar-pane")
        self._selecting = False

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
        new_tab.set_margin_top(6)
        new_tab.set_margin_start(6)
        new_tab.set_margin_end(6)
        self.append(new_tab)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        self.append(scroller)

        self.list = Gtk.ListBox()
        self.list.add_css_class("navigation-sidebar")
        self.list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list.connect("row-selected", self._on_row_selected)
        scroller.set_child(self.list)

        drop = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        drop.connect("drop", self._on_drop)
        self.list.add_controller(drop)

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

    # -- context menu ----------------------------------------------------------
    def _attach_menu(self, row):
        gesture = Gtk.GestureClick(button=3)
        gesture.connect("pressed", self._on_row_right_click, row)
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
        row.add_controller(source)

    def _on_drag_prepare(self, source, x, y, row):
        value = GObject.Value(GObject.TYPE_STRING, row.session.id)
        return Gdk.ContentProvider.new_for_value(value)

    def _on_drag_begin(self, source, drag, row):
        paintable = Gtk.WidgetPaintable.new(row)
        source.set_icon(paintable, 0, 0)

    def _on_drop(self, target, value, x, y):
        session_id = str(value)
        dragged = next((s for s in self.sessions() if s.id == session_id), None)
        if dragged is None:
            return False
        target_row = self.list.get_row_at_y(int(y))
        rows = self.rows()
        if target_row is None:
            new_index = len(rows) - 1
        else:
            new_index = target_row.get_index()
        self.move_session(dragged, new_index)
        return True
