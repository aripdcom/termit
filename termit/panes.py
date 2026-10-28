"""Split panes: a tree of terminals inside one tab."""

from gi.repository import GLib, GObject, Gtk

DIRECTIONS = ("left", "right", "up", "down")


class PaneLeaf(Gtk.Box):
    """One terminal with its scrollbar.

    The terminal is deliberately not placed in a Gtk.ScrolledWindow: VTE handles
    wheel events itself (three lines per step, like GNOME Terminal) and a scrolled
    window would scroll the same events a second time.
    """

    def __init__(self, terminal):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.terminal = terminal
        self.add_css_class("pane-leaf")
        self.append(terminal)
        adjustment = terminal.get_vadjustment()
        self.scrollbar = Gtk.Scrollbar(orientation=Gtk.Orientation.VERTICAL, adjustment=adjustment)
        self.scrollbar.set_visible(False)
        self.append(self.scrollbar)
        adjustment.connect("changed", self._update_scrollbar)
        self._update_scrollbar(adjustment)

    def _update_scrollbar(self, adjustment):
        scrollable = adjustment.get_upper() - adjustment.get_lower() > adjustment.get_page_size() + 0.5
        self.scrollbar.set_visible(scrollable)

    def detach_terminal(self):
        self.remove(self.terminal)


class PaneGroup(Gtk.Box):
    """Holds the terminals of a tab, arranged in nested Gtk.Paned splits.

    The group tracks which terminal is active (last focused). Signals:
    - active-changed(terminal): a different terminal became active
    - terminal-removed(terminal): a pane was closed; the group may now be empty
    - layout-changed: panes were added or removed
    """

    __gsignals__ = {
        "active-changed": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "terminal-removed": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "layout-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self._leaves = {}
        self.active = None

    # -- queries ---------------------------------------------------------------
    @property
    def terminals(self):
        """Terminals in visual order (top-left first)."""
        return [leaf.terminal for leaf in self._ordered_leaves()]

    def __len__(self):
        return len(self._leaves)

    def _ordered_leaves(self, widget=None):
        widget = widget if widget is not None else self.get_first_child()
        if widget is None:
            return []
        if isinstance(widget, PaneLeaf):
            return [widget]
        if isinstance(widget, Gtk.Paned):
            return self._ordered_leaves(widget.get_start_child()) + self._ordered_leaves(widget.get_end_child())
        return []

    # -- building ----------------------------------------------------------------
    def add_terminal(self, terminal):
        """Add the first terminal of the group."""
        leaf = self._make_leaf(terminal)
        self.append(leaf)
        self.set_active(terminal)
        self.emit("layout-changed")

    def split(self, terminal, orientation, new_terminal):
        """Split the pane holding `terminal`, placing `new_terminal` after it."""
        leaf = self._leaves[terminal]
        parent = leaf.get_parent()
        paned = Gtk.Paned(orientation=orientation)
        paned.set_wide_handle(False)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)
        paned.set_resize_start_child(True)
        paned.set_resize_end_child(True)
        size = leaf.get_width() if orientation == Gtk.Orientation.HORIZONTAL else leaf.get_height()
        self._replace_child(parent, leaf, paned)
        new_leaf = self._make_leaf(new_terminal)
        paned.set_start_child(leaf)
        paned.set_end_child(new_leaf)
        if size > 0:
            paned.set_position(size // 2)
        self.set_active(new_terminal)
        self.emit("layout-changed")
        return new_leaf

    def remove(self, terminal):
        """Remove a pane. Returns True when the group is empty afterwards."""
        leaf = self._leaves.pop(terminal, None)
        if leaf is None:
            return len(self._leaves) == 0
        parent = leaf.get_parent()
        was_active = self.active is terminal
        if isinstance(parent, Gtk.Paned):
            sibling = parent.get_end_child() if parent.get_start_child() is leaf else parent.get_start_child()
            grand = parent.get_parent()
            parent.set_start_child(None)
            parent.set_end_child(None)
            self._replace_child(grand, parent, sibling)
        else:
            self.remove_child_widget(leaf)
        leaf.detach_terminal()
        self.emit("terminal-removed", terminal)
        if was_active:
            self.active = None
            remaining = self.terminals
            if remaining:
                self.set_active(remaining[0])
                remaining[0].grab_focus()
        self.emit("layout-changed")
        return len(self._leaves) == 0

    def remove_child_widget(self, child):
        Gtk.Box.remove(self, child)

    def _replace_child(self, parent, old, new):
        if isinstance(parent, Gtk.Paned):
            if parent.get_start_child() is old:
                parent.set_start_child(new)
            else:
                parent.set_end_child(new)
        else:
            Gtk.Box.remove(self, old)
            self.append(new)

    def _make_leaf(self, terminal):
        leaf = PaneLeaf(terminal)
        self._leaves[terminal] = leaf
        focus = Gtk.EventControllerFocus()
        focus.connect("enter", lambda c: self.set_active(terminal))
        terminal.add_controller(focus)
        return leaf

    # -- active pane ---------------------------------------------------------------
    def set_active(self, terminal):
        if terminal not in self._leaves or terminal is self.active:
            return
        self.active = terminal
        self._update_active_style()
        self.emit("active-changed", terminal)

    def _update_active_style(self):
        multiple = len(self._leaves) > 1
        for terminal, leaf in self._leaves.items():
            if multiple and terminal is self.active:
                leaf.add_css_class("active")
            else:
                leaf.remove_css_class("active")

    def focus_direction(self, direction):
        """Move focus to the nearest pane in the given direction."""
        if self.active is None or len(self._leaves) < 2 or direction not in DIRECTIONS:
            return False
        current = self._leaves[self.active]
        ok, bounds = current.compute_bounds(self)
        if not ok:
            return False
        cx = bounds.get_x() + bounds.get_width() / 2
        cy = bounds.get_y() + bounds.get_height() / 2
        best, best_score = None, None
        for terminal, leaf in self._leaves.items():
            if terminal is self.active:
                continue
            ok, b = leaf.compute_bounds(self)
            if not ok:
                continue
            ox = b.get_x() + b.get_width() / 2
            oy = b.get_y() + b.get_height() / 2
            dx, dy = ox - cx, oy - cy
            if direction == "left" and dx >= -1 or direction == "right" and dx <= 1:
                continue
            if direction == "up" and dy >= -1 or direction == "down" and dy <= 1:
                continue
            primary = abs(dx) if direction in ("left", "right") else abs(dy)
            secondary = abs(dy) if direction in ("left", "right") else abs(dx)
            score = primary + secondary * 2
            if best_score is None or score < best_score:
                best, best_score = terminal, score
        if best is None:
            return False
        best.grab_focus()
        self.set_active(best)
        return True

    # -- persistence ---------------------------------------------------------------
    def layout(self, cwd_of):
        """Serialise the split tree. `cwd_of(terminal)` returns the folder to save."""
        return self._layout_of(self.get_first_child(), cwd_of)

    def _layout_of(self, widget, cwd_of):
        if isinstance(widget, PaneLeaf):
            return {"type": "terminal", "cwd": cwd_of(widget.terminal)}
        if isinstance(widget, Gtk.Paned):
            horizontal = widget.get_orientation() == Gtk.Orientation.HORIZONTAL
            total = widget.get_width() if horizontal else widget.get_height()
            ratio = widget.get_position() / total if total > 0 else 0.5
            return {
                "type": "split",
                "orientation": "horizontal" if horizontal else "vertical",
                "ratio": round(min(max(ratio, 0.1), 0.9), 3),
                "children": [
                    self._layout_of(widget.get_start_child(), cwd_of),
                    self._layout_of(widget.get_end_child(), cwd_of),
                ],
            }
        return None

    def restore(self, layout, make_terminal):
        """Rebuild a saved layout. `make_terminal(cwd)` creates and spawns a terminal."""
        widget = self._build(layout, make_terminal)
        if widget is None:
            return False
        self.append(widget)
        terminals = self.terminals
        if terminals:
            self.set_active(terminals[0])
        self.emit("layout-changed")
        return True

    def _build(self, node, make_terminal):
        if not isinstance(node, dict):
            return None
        if node.get("type") == "terminal":
            return self._make_leaf(make_terminal(node.get("cwd")))
        if node.get("type") == "split" and len(node.get("children") or []) == 2:
            start = self._build(node["children"][0], make_terminal)
            end = self._build(node["children"][1], make_terminal)
            if start is None or end is None:
                return start or end
            horizontal = node.get("orientation") != "vertical"
            paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL if horizontal else Gtk.Orientation.VERTICAL)
            paned.set_shrink_start_child(False)
            paned.set_shrink_end_child(False)
            paned.set_resize_start_child(True)
            paned.set_resize_end_child(True)
            paned.set_start_child(start)
            paned.set_end_child(end)
            ratio = node.get("ratio", 0.5)
            if isinstance(ratio, (int, float)):
                GLib.idle_add(self._apply_ratio, paned, float(ratio))
            return paned
        return None

    def _apply_ratio(self, paned, ratio):
        total = paned.get_width() if paned.get_orientation() == Gtk.Orientation.HORIZONTAL else paned.get_height()
        if total <= 0:
            return GLib.SOURCE_CONTINUE  # not allocated yet, try again
        paned.set_position(int(total * ratio))
        return GLib.SOURCE_REMOVE
