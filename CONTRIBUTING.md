# Contributing to Termit

Thank you for considering a contribution. Termit is a small, focused project and we try to keep it that way: a GNOME-style terminal that is pleasant to use with many tabs and with AI coding agents.

## Development setup

1. Install the runtime dependencies listed in the [README](README.md#installation) (PyGObject, GTK 4, libadwaita, VTE for GTK 4).
2. Clone the repository and run Termit from the checkout:

   ```sh
   git clone https://github.com/aripdcom/termit.git
   cd termit
   python3 -m termit
   ```

3. Optional tools: `ruff` for linting (`make lint`) and `xvfb-run` for headless testing.

Use a separate config and data directory while hacking so your real notes stay untouched:

```sh
XDG_CONFIG_HOME=/tmp/termit-dev/config XDG_DATA_HOME=/tmp/termit-dev/data python3 -m termit
```

## Project layout

| File | Purpose |
| --- | --- |
| `termit/main.py` | `Adw.Application`, command line options, app-level actions |
| `termit/window.py` | Main window: header bar, split view, terminal stack, actions and shortcuts |
| `termit/terminal.py` | `Vte.Terminal` subclass: spawning, links, search, paste protection, process inspection |
| `termit/panes.py` | Split-pane tree (`PaneGroup`) holding the terminals of a tab |
| `termit/sidebar.py` | Vertical tab list with search, context menu and drag-and-drop |
| `termit/notes.py` | Notes pane (per-tab note and global scratchpad) with autosave |
| `termit/session.py` | `TabSession`: terminal + note buffer + display metadata |
| `termit/storage.py` | Notes on disk, archive index, session restore file |
| `termit/settings.py` | JSON settings with change notifications |
| `termit/preferences.py` | Preferences dialog |
| `termit/dialogs.py` | Rename, archive, shortcuts, about and confirmation dialogs |
| `termit/palettes.py` | Terminal colour palettes |
| `termit/i18n.py`, `termit/translations_tr.py` | Minimal translation layer |
| `termit/resources/style.css` | Application CSS |
| `data/` | Desktop entry, icon, AppStream metadata |
| `docs/` | The website published at https://termit.aripd.com |

## Conventions

- Everything in the repository — code, comments, commit messages, documentation — is written in English. User-facing strings go through `_()` so they can be translated.
- Follow the existing style: 4-space indentation, 120-character lines, `ruff` clean (`make lint`).
- Keep pull requests focused. A change to behaviour should be described in the PR and, where it is user-visible, in the README.
- Prefer libadwaita widgets and GNOME Human Interface Guidelines patterns over custom chrome.
- Do not add runtime dependencies outside PyGObject/GTK/libadwaita/VTE without discussing it in an issue first.

## Adding a translation

1. Copy `termit/translations_tr.py` to `termit/translations_<lang>.py` and translate the values.
2. Register the language in `termit/i18n.py`.
3. Test with `LANGUAGE=<lang> python3 -m termit`.

## Releasing

1. Make sure the `Unreleased` section of `CHANGELOG.md` lists every user-visible change.
2. Run `make bump VERSION=X.Y.Z`. It updates `termit/__init__.py`, `pyproject.toml` and turns the
   `Unreleased` section into a dated `X.Y.Z` section.
3. Commit, tag and push:

   ```sh
   git commit -am "Release X.Y.Z"
   git tag -a vX.Y.Z -m "Termit X.Y.Z"
   git push origin main vX.Y.Z
   ```

The `Release` workflow checks that the tag matches the version in the sources and publishes a
GitHub release with the notes taken from the changelog.

## Reporting bugs

Open an issue at https://github.com/aripdcom/termit/issues with your distribution, the versions of GTK, libadwaita and VTE (for example `pkg-config --modversion gtk4 libadwaita-1 vte-2.91-gtk4`), and the steps to reproduce. Terminal output from `python3 -m termit` is very helpful.
