"""Notes storage: one markdown file per tab session plus a JSON index."""

import datetime
import json
import os

from .settings import DATA_DIR


def _now():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


class NotesStore:
    def __init__(self, data_dir=DATA_DIR):
        self.data_dir = data_dir
        self.notes_dir = os.path.join(data_dir, "notes")
        self.index_file = os.path.join(self.notes_dir, "index.json")
        self.global_file = os.path.join(data_dir, "global-notes.md")
        self.session_file = os.path.join(data_dir, "session.json")
        os.makedirs(self.notes_dir, exist_ok=True)
        self.index = self._load_index()

    # -- index -------------------------------------------------------------
    def _load_index(self):
        try:
            with open(self.index_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
        return {}

    def _save_index(self):
        tmp = self.index_file + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.index, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.index_file)
        except OSError as exc:  # pragma: no cover
            print(f"termit: could not save notes index: {exc}")

    def _path(self, nid):
        return os.path.join(self.notes_dir, f"{nid}.md")

    # -- per-session notes -------------------------------------------------
    def exists(self, nid):
        return nid in self.index

    def read(self, nid):
        try:
            with open(self._path(nid), "r", encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return ""

    def write(self, nid, text, title=None, cwd=None):
        """Persist note text. Empty notes that were never saved are not created."""
        if not text.strip() and nid not in self.index:
            return
        try:
            tmp = self._path(nid) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, self._path(nid))
        except OSError as exc:  # pragma: no cover
            print(f"termit: could not save note: {exc}")
            return
        entry = self.index.setdefault(nid, {"created": _now(), "closed": None})
        entry["updated"] = _now()
        if title is not None:
            entry["title"] = title
        if cwd is not None:
            entry["cwd"] = cwd
        self._save_index()

    def update_meta(self, nid, title=None, cwd=None):
        entry = self.index.get(nid)
        if not entry:
            return
        changed = False
        if title is not None and entry.get("title") != title:
            entry["title"] = title
            changed = True
        if cwd is not None and entry.get("cwd") != cwd:
            entry["cwd"] = cwd
            changed = True
        if changed:
            self._save_index()

    def delete(self, nid):
        self.index.pop(nid, None)
        try:
            os.remove(self._path(nid))
        except OSError:
            pass
        self._save_index()

    def mark_closed(self, nid):
        """Archive a note when its tab closes. Empty notes are discarded."""
        if nid not in self.index:
            return
        if not self.read(nid).strip():
            self.delete(nid)
            return
        self.index[nid]["closed"] = _now()
        self._save_index()

    def mark_open(self, nid):
        if nid in self.index and self.index[nid].get("closed"):
            self.index[nid]["closed"] = None
            self._save_index()

    def archived(self):
        items = [(nid, e) for nid, e in self.index.items() if e.get("closed")]
        items.sort(key=lambda kv: kv[1].get("updated", ""), reverse=True)
        return items

    def archived_for_cwd(self, cwd):
        return [nid for nid, e in self.archived() if e.get("cwd") == cwd]

    def preview(self, nid, limit=140):
        text = self.read(nid).strip().replace("\n", " ")
        return text[:limit] + ("…" if len(text) > limit else "")

    # -- global scratchpad -------------------------------------------------
    def global_read(self):
        try:
            with open(self.global_file, "r", encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return ""

    def global_write(self, text):
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            tmp = self.global_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, self.global_file)
        except OSError as exc:  # pragma: no cover
            print(f"termit: could not save global notes: {exc}")

    # -- session restore ---------------------------------------------------
    def load_session(self):
        try:
            with open(self.session_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and isinstance(data.get("tabs"), list):
                return data
        except (OSError, ValueError):
            pass
        return None

    def save_session(self, data):
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            tmp = self.session_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.session_file)
        except OSError as exc:  # pragma: no cover
            print(f"termit: could not save session: {exc}")

    def clear_session(self):
        try:
            os.remove(self.session_file)
        except OSError:
            pass
