"""Tiny translation layer. English source strings, Turkish translations."""

import locale
import os

_LANG = None


def _detect():
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var)
        if val:
            return val.split(":")[0].split(".")[0].split("_")[0].lower()
    try:
        loc = locale.getlocale()[0]
    except Exception:  # pragma: no cover
        loc = None
    return (loc or "en").split("_")[0].lower()


def language():
    global _LANG
    if _LANG is None:
        _LANG = _detect()
    return _LANG


def _(text):
    if language() == "tr":
        return TR.get(text, text)
    return text


TR = {}  # filled below

from .translations_tr import TR as _TR  # noqa: E402

TR.update(_TR)
