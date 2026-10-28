"""Secondary dialogs: rename, notes archive, keyboard shortcuts, about."""

import datetime

from gi.repository import Adw, Gtk

from . import APP_ID, __version__
from .i18n import _
from .session import short_path

SHORTCUT_GROUPS = [
    (_("Tabs"), [
        ("Ctrl+Shift+T", _("New tab")),
        ("Ctrl+Shift+W", _("Close tab")),
        ("Ctrl+Shift+D", _("Duplicate tab (same folder)")),
        ("Ctrl+Page Up / Page Down", _("Previous / next tab")),
        ("Ctrl+Shift+Page Up / Page Down", _("Move tab up / down")),
        ("Alt+1 … Alt+9", _("Switch to tab 1–9")),
        ("F2", _("Rename tab")),
        ("Ctrl+Shift+L", _("Find a tab by title, folder, process or note")),
    ]),
    (_("Panels"), [
        ("Ctrl+Shift+B", _("Show or hide the tab sidebar")),
        ("Ctrl+Shift+N", _("Show or hide notes")),
        ("Ctrl+Shift+E", _("Focus the note editor")),
        ("Esc", _("Return focus from notes to the terminal")),
        ("Ctrl+Shift+S", _("Snippets")),
        ("F11", _("Fullscreen")),
    ]),
    (_("Terminal"), [
        ("Ctrl+Shift+C", _("Copy")),
        ("Ctrl+Shift+V", _("Paste")),
        ("Ctrl+Shift+A", _("Select all")),
        ("Ctrl+Shift+F", _("Find")),
        ("Ctrl+Shift+G / Ctrl+Shift+H", _("Find next / previous")),
        ("Ctrl+Shift+K", _("Clear scrollback")),
        ("Ctrl++ / Ctrl+- / Ctrl+0", _("Zoom in / out / reset")),
        ("Ctrl+Click", _("Open link or file path")),
    ]),
    (_("Application"), [
        ("Ctrl+Shift+P", _("Preferences")),
        ("Ctrl+?", _("Keyboard shortcuts")),
        ("Ctrl+Shift+Q", _("Quit")),
    ]),
]


def rename_dialog(window, session, on_done):
    dialog = Adw.AlertDialog.new(_("Rename Tab"), None)
    entry = Gtk.Entry()
    entry.set_text(session.custom_title or session.display_title)
    entry.set_placeholder_text(_("Leave empty to use the automatic title"))
    entry.set_activates_default(True)
    dialog.set_extra_child(entry)
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("rename", _("Rename"))
    dialog.set_response_appearance("rename", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("rename")
    dialog.set_close_response("cancel")

    def on_response(d, response):
        if response == "rename":
            on_done(entry.get_text().strip() or None)

    dialog.connect("response", on_response)
    dialog.present(window)
    entry.grab_focus()


def confirm_dialog(window, heading, body, confirm_label, on_confirm, destructive=True):
    dialog = Adw.AlertDialog.new(heading, body)
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("confirm", confirm_label)
    if destructive:
        dialog.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
    else:
        dialog.set_response_appearance("confirm", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("cancel")
    dialog.set_close_response("cancel")
    dialog.connect("response", lambda d, r: on_confirm() if r == "confirm" else None)
    dialog.present(window)


def paste_warning_dialog(window, text, on_paste):
    lines = text.strip("\r\n").splitlines()
    preview = "\n".join(lines[:6])
    if len(lines) > 6:
        preview += "\n…"
    dialog = Adw.AlertDialog.new(
        _("Paste multiple lines?"),
        _("The clipboard contains {n} lines. Each line may run as a separate command.").format(n=len(lines)),
    )
    label = Gtk.Label(label=preview, xalign=0)
    label.add_css_class("monospace")
    label.set_wrap(True)
    label.set_selectable(True)
    frame = Gtk.Frame()
    frame.set_child(label)
    label.set_margin_top(6)
    label.set_margin_bottom(6)
    label.set_margin_start(8)
    label.set_margin_end(8)
    dialog.set_extra_child(frame)
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("paste", _("Paste"))
    dialog.set_response_appearance("paste", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("paste")
    dialog.set_close_response("cancel")
    dialog.connect("response", lambda d, r: on_paste() if r == "paste" else None)
    dialog.present(window)


def notes_on_close_dialog(window, session, on_keep, on_delete):
    dialog = Adw.AlertDialog.new(
        _("Keep the note for “{title}”?").format(title=session.display_title),
        _("The note is kept in the archive and can be restored later."),
    )
    dialog.add_response("delete", _("Delete Note"))
    dialog.add_response("keep", _("Keep Note"))
    dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.set_response_appearance("keep", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("keep")
    dialog.set_close_response("keep")
    dialog.connect("response", lambda d, r: on_delete() if r == "delete" else on_keep())
    dialog.present(window)


class ArchiveDialog(Adw.Dialog):
    """Browse notes whose tabs were closed."""

    def __init__(self, window, store):
        super().__init__()
        self.window = window
        self.store = store
        self.set_title(_("Notes Archive"))
        self.set_content_width(560)
        self.set_content_height(520)

        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        self.set_child(view)

        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroller.set_vexpand(True)
        view.set_content(self.scroller)
        self.rebuild()

    def rebuild(self):
        items = self.store.archived()
        if not items:
            status = Adw.StatusPage()
            status.set_icon_name("document-open-recent-symbolic")
            status.set_title(_("No archived notes"))
            status.set_description(_("Notes of closed tabs appear here."))
            self.scroller.set_child(status)
            return
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup()
        group.set_description(_("Notes from closed tabs. Open one in a new tab to continue working with it."))
        page.add(group)
        for nid, entry in items:
            row = Adw.ExpanderRow()
            row.set_title(entry.get("title") or _("Untitled"))
            when = (entry.get("updated") or "")[:16].replace("T", " ")
            cwd = short_path(entry.get("cwd") or "")
            row.set_subtitle(" · ".join(part for part in (cwd, when) if part))

            open_btn = Gtk.Button.new_from_icon_name("tab-new-symbolic")
            open_btn.add_css_class("flat")
            open_btn.set_valign(Gtk.Align.CENTER)
            open_btn.set_tooltip_text(_("Open in New Tab"))
            open_btn.connect("clicked", self._on_open, nid, entry)
            row.add_suffix(open_btn)

            copy_btn = Gtk.Button.new_from_icon_name("edit-copy-symbolic")
            copy_btn.add_css_class("flat")
            copy_btn.set_valign(Gtk.Align.CENTER)
            copy_btn.set_tooltip_text(_("Copy Note"))
            copy_btn.connect("clicked", self._on_copy, nid)
            row.add_suffix(copy_btn)

            delete_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic")
            delete_btn.add_css_class("flat")
            delete_btn.set_valign(Gtk.Align.CENTER)
            delete_btn.set_tooltip_text(_("Delete Note"))
            delete_btn.connect("clicked", self._on_delete, nid)
            row.add_suffix(delete_btn)

            body = Gtk.Label(label=self.store.read(nid).strip() or " ", xalign=0)
            body.set_wrap(True)
            body.set_selectable(True)
            body.add_css_class("monospace")
            body.set_margin_top(8)
            body.set_margin_bottom(8)
            body.set_margin_start(12)
            body.set_margin_end(12)
            row.add_row(body)
            group.add(row)
        self.scroller.set_child(page)

    def _on_open(self, button, nid, entry):
        self.window.open_archived_note(nid, entry)
        self.close()

    def _on_copy(self, button, nid):
        self.window.get_clipboard().set(self.store.read(nid))
        self.window.toast(_("Note copied to clipboard"))

    def _on_delete(self, button, nid):
        confirm_dialog(
            self.window, _("Delete this note?"), _("The note is removed permanently."), _("Delete"),
            lambda: (self.store.delete(nid), self.rebuild()),
        )


class ShortcutsDialog(Adw.Dialog):
    def __init__(self):
        super().__init__()
        self.set_title(_("Keyboard Shortcuts"))
        self.set_content_width(520)
        self.set_content_height(620)
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        self.set_child(view)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        view.set_content(scroller)
        page = Adw.PreferencesPage()
        scroller.set_child(page)
        for title, items in SHORTCUT_GROUPS:
            group = Adw.PreferencesGroup(title=title)
            for keys, description in items:
                row = Adw.ActionRow(title=description)
                label = Gtk.Label(label=keys)
                label.add_css_class("shortcut-key")
                label.set_valign(Gtk.Align.CENTER)
                row.add_suffix(label)
                group.add(row)
            page.add(group)


def about_dialog(window):
    dialog = Adw.AboutDialog()
    dialog.set_application_name("Termit")
    dialog.set_application_icon(APP_ID)
    dialog.set_version(__version__)
    dialog.set_developer_name("aripdcom")
    dialog.set_website("https://termit.aripd.com")
    dialog.set_issue_url("https://github.com/aripdcom/termit/issues")
    dialog.set_license_type(Gtk.License.MIT_X11)
    dialog.set_comments(_("A GNOME-style terminal with vertical tabs and per-tab notes."))
    dialog.set_copyright(f"© {datetime.date.today().year} aripdcom and contributors")
    dialog.present(window)
