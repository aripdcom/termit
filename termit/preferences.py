"""Preferences dialog."""

from gi.repository import Adw, Gtk, Pango

from .i18n import _
from .palettes import PALETTE_ORDER, PALETTES


def _combo(group, title, settings, key, choices, subtitle=None):
    """choices: list of (value, label)."""
    row = Adw.ComboRow(title=title)
    if subtitle:
        row.set_subtitle(subtitle)
    row.set_model(Gtk.StringList.new([label for _value, label in choices]))
    values = [value for value, _label in choices]
    current = settings.get(key)
    row.set_selected(values.index(current) if current in values else 0)
    row.connect("notify::selected", lambda r, _p: settings.set(key, values[r.get_selected()]))
    group.add(row)
    return row


def _switch(group, title, settings, key, subtitle=None):
    row = Adw.SwitchRow(title=title)
    if subtitle:
        row.set_subtitle(subtitle)
    row.set_active(bool(settings.get(key)))
    row.connect("notify::active", lambda r, _p: settings.set(key, r.get_active()))
    group.add(row)
    return row


class PreferencesDialog(Adw.PreferencesDialog):
    def __init__(self, window, settings):
        super().__init__()
        self.window = window
        self.settings = settings
        self.set_title(_("Preferences"))
        self.set_search_enabled(True)
        self._build_general()
        self._build_terminal()
        self._build_notes()

    # -- pages -----------------------------------------------------------------
    def _build_general(self):
        s = self.settings
        page = Adw.PreferencesPage(title=_("General"), icon_name="preferences-system-symbolic")
        self.add(page)

        group = Adw.PreferencesGroup(title=_("Layout"))
        page.add(group)
        _combo(group, _("Tab sidebar position"), s, "sidebar_position",
               [("left", _("Left")), ("right", _("Right"))])
        _combo(group, _("Notes position"), s, "notes_position",
               [("right", _("Right of the terminal")), ("bottom", _("Below the terminal"))])
        _combo(group, _("Application theme"), s, "color_scheme",
               [("system", _("Follow system")), ("light", _("Light")), ("dark", _("Dark"))])

        group = Adw.PreferencesGroup(title=_("Session"))
        page.add(group)
        _switch(group, _("Restore tabs on startup"), s, "restore_session",
                _("Reopen the tabs from the last session with their folders and notes."))
        _switch(group, _("New tabs open in the current folder"), s, "new_tab_inherits_cwd")
        _switch(group, _("Confirm before closing a tab"), s, "confirm_close_tab",
                _("Ask every time a tab is closed from the sidebar, the menu or the keyboard."))
        _switch(group, _("Confirm closing tabs with a running process"), s, "confirm_close_running",
                _("Applies when the setting above is off."))
        _switch(group, _("Notify when a background tab rings the bell"), s, "bell_notification",
                _("Claude Code can ring the terminal bell when it needs your attention."))

    def _build_terminal(self):
        s = self.settings
        page = Adw.PreferencesPage(title=_("Terminal"), icon_name="utilities-terminal-symbolic")
        self.add(page)

        group = Adw.PreferencesGroup(title=_("Appearance"))
        page.add(group)
        font_row = Adw.ActionRow(title=_("Font"), subtitle=_("Leave unset to use the system monospace font"))
        font_button = Gtk.FontDialogButton(dialog=Gtk.FontDialog())
        font_button.set_level(Gtk.FontLevel.FONT)
        font_button.set_valign(Gtk.Align.CENTER)
        if s.get("font"):
            font_button.set_font_desc(Pango.FontDescription.from_string(s.get("font")))
        font_button.connect("notify::font-desc", lambda b, _p: s.set("font", b.get_font_desc().to_string()))
        font_row.add_suffix(font_button)
        reset = Gtk.Button.new_from_icon_name("edit-clear-symbolic")
        reset.add_css_class("flat")
        reset.set_valign(Gtk.Align.CENTER)
        reset.set_tooltip_text(_("Use system font"))
        reset.connect("clicked", lambda b: s.set("font", ""))
        font_row.add_suffix(reset)
        group.add(font_row)
        _combo(group, _("Color palette"), s, "palette",
               [(pid, PALETTES[pid]["name"]) for pid in PALETTE_ORDER])
        _combo(group, _("Cursor shape"), s, "cursor_shape",
               [("block", _("Block")), ("ibeam", _("I-Beam")), ("underline", _("Underline"))])
        _combo(group, _("Cursor blinking"), s, "cursor_blink",
               [("system", _("Follow system")), ("on", _("On")), ("off", _("Off"))])
        _switch(group, _("Show bold text in bright colors"), s, "bold_is_bright")

        group = Adw.PreferencesGroup(title=_("Behavior"))
        page.add(group)
        spin = Adw.SpinRow.new_with_range(100, 1000000, 1000)
        spin.set_title(_("Scrollback lines"))
        spin.set_value(int(s.get("scrollback_lines")))
        spin.connect("notify::value", lambda r, _p: s.set("scrollback_lines", int(r.get_value())))
        group.add(spin)
        speed = Adw.SpinRow.new_with_range(1, 20, 1)
        speed.set_title(_("Lines per mouse wheel step"))
        speed.set_subtitle(_("GNOME Terminal scrolls 3 lines"))
        speed.set_value(int(s.get("scroll_lines")))
        speed.connect("notify::value", lambda r, _p: s.set("scroll_lines", int(r.get_value())))
        group.add(speed)
        touchpad = Adw.SpinRow.new_with_range(0.25, 4.0, 0.25)
        touchpad.set_title(_("Touchpad scroll speed"))
        touchpad.set_subtitle(_("1.0 moves the text as far as your fingers move"))
        touchpad.set_digits(2)
        touchpad.set_value(float(s.get("touchpad_scroll_speed")))
        touchpad.connect("notify::value", lambda r, _p: s.set("touchpad_scroll_speed", round(r.get_value(), 2)))
        group.add(touchpad)
        _switch(group, _("Scroll on output"), s, "scroll_on_output")
        _switch(group, _("Scroll on keystroke"), s, "scroll_on_keystroke")
        _switch(group, _("Copy selected text automatically"), s, "copy_on_select")
        _switch(group, _("Warn before pasting multiple lines into the shell"), s, "paste_warning",
                _("The warning is skipped while a program such as Claude Code is running."))
        _switch(group, _("Audible bell"), s, "audible_bell")

        group = Adw.PreferencesGroup(title=_("Command"))
        page.add(group)
        _switch(group, _("Run shell as a login shell"), s, "login_shell")
        entry = Adw.EntryRow(title=_("Custom command instead of the shell"))
        entry.set_text(s.get("custom_command") or "")
        entry.set_show_apply_button(True)
        entry.connect("apply", lambda r: s.set("custom_command", r.get_text().strip()))
        group.add(entry)

    def _build_notes(self):
        s = self.settings
        page = Adw.PreferencesPage(title=_("Notes & Snippets"), icon_name="document-edit-symbolic")
        self.add(page)

        group = Adw.PreferencesGroup(title=_("Notes"))
        page.add(group)
        _combo(group, _("When a tab is closed"), s, "notes_on_close",
               [("keep", _("Keep the note in the archive")), ("delete", _("Delete the note")),
                ("ask", _("Ask every time"))])
        _switch(group, _("Use a monospace font for notes"), s, "notes_monospace")

        self.snippet_group = Adw.PreferencesGroup(title=_("Snippets"))
        self.snippet_group.set_description(
            _("Commands you can insert into the terminal from the snippets menu (Ctrl+Shift+S).")
        )
        add = Gtk.Button.new_from_icon_name("list-add-symbolic")
        add.add_css_class("flat")
        add.set_tooltip_text(_("Add Snippet"))
        add.connect("clicked", lambda b: self._edit_snippet(None))
        self.snippet_group.set_header_suffix(add)
        page.add(self.snippet_group)
        self._snippet_rows = []
        self._rebuild_snippets()

    # -- snippets -------------------------------------------------------------
    def _rebuild_snippets(self):
        for row in self._snippet_rows:
            self.snippet_group.remove(row)
        self._snippet_rows = []
        for index, snippet in enumerate(self.settings.get("snippets")):
            row = Adw.ActionRow(title=snippet.get("name") or snippet.get("command", ""))
            row.set_subtitle(snippet.get("command", ""))
            row.set_subtitle_selectable(True)
            if snippet.get("run"):
                badge = Gtk.Label(label=_("runs"))
                badge.add_css_class("pill")
                badge.set_valign(Gtk.Align.CENTER)
                row.add_suffix(badge)
            edit = Gtk.Button.new_from_icon_name("document-edit-symbolic")
            edit.add_css_class("flat")
            edit.set_valign(Gtk.Align.CENTER)
            edit.connect("clicked", lambda b, i=index: self._edit_snippet(i))
            row.add_suffix(edit)
            remove = Gtk.Button.new_from_icon_name("user-trash-symbolic")
            remove.add_css_class("flat")
            remove.set_valign(Gtk.Align.CENTER)
            remove.connect("clicked", lambda b, i=index: self._remove_snippet(i))
            row.add_suffix(remove)
            self.snippet_group.add(row)
            self._snippet_rows.append(row)

    def _remove_snippet(self, index):
        snippets = list(self.settings.get("snippets"))
        del snippets[index]
        self.settings.set("snippets", snippets)
        self._rebuild_snippets()

    def _edit_snippet(self, index):
        snippets = list(self.settings.get("snippets"))
        current = snippets[index] if index is not None else {"name": "", "command": "", "run": True}
        dialog = Adw.AlertDialog.new(_("Edit Snippet") if index is not None else _("Add Snippet"), None)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        group = Adw.PreferencesGroup()
        name = Adw.EntryRow(title=_("Name"))
        name.set_text(current.get("name", ""))
        command = Adw.EntryRow(title=_("Command"))
        command.set_text(current.get("command", ""))
        run = Adw.SwitchRow(title=_("Run immediately"))
        run.set_subtitle(_("Otherwise the command is only typed into the terminal"))
        run.set_active(bool(current.get("run", True)))
        group.add(name)
        group.add(command)
        group.add(run)
        box.append(group)
        dialog.set_extra_child(box)
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("save", _("Save"))
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")

        def on_response(d, response):
            if response != "save" or not command.get_text().strip():
                return
            item = {
                "name": name.get_text().strip() or command.get_text().strip(),
                "command": command.get_text().strip(),
                "run": run.get_active(),
            }
            if index is None:
                snippets.append(item)
            else:
                snippets[index] = item
            self.settings.set("snippets", snippets)
            self._rebuild_snippets()

        dialog.connect("response", on_response)
        dialog.present(self)
