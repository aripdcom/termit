#!/usr/bin/env python3
"""Bump the Termit version.

Usage: scripts/bump_version.py X.Y.Z

Updates termit/__init__.py and pyproject.toml, turns the "Unreleased"
section of CHANGELOG.md into a dated section for the new version, and
prints the git commands that publish the release.
"""

import datetime
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
INIT = ROOT / "termit" / "__init__.py"
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"


def current_version():
    match = re.search(r'^__version__ = "([^"]+)"', INIT.read_text(encoding="utf-8"), re.M)
    return match.group(1) if match else None


def replace_once(path, pattern, replacement):
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.M)
    if count != 1:
        sys.exit(f"error: could not find the version in {path}")
    path.write_text(new_text, encoding="utf-8")


def update_changelog(version):
    text = CHANGELOG.read_text(encoding="utf-8")
    if f"## [{version}]" in text:
        sys.exit(f"error: CHANGELOG.md already has a section for {version}")
    marker = "## [Unreleased]\n"
    if marker not in text:
        sys.exit("error: CHANGELOG.md has no '## [Unreleased]' section")
    head, rest = text.split(marker, 1)
    body = rest.lstrip("\n")
    if body.startswith("## ["):
        sys.exit("error: the Unreleased section is empty; add changelog entries first")
    today = datetime.date.today().isoformat()
    CHANGELOG.write_text(f"{head}{marker}\n## [{version}] - {today}\n\n{body}", encoding="utf-8")


def main(argv):
    if len(argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", argv[1]):
        sys.exit(__doc__.strip())
    version = argv[1]
    old = current_version()
    if old == version:
        sys.exit(f"error: version is already {version}")
    update_changelog(version)
    replace_once(INIT, r'^__version__ = "[^"]+"', f'__version__ = "{version}"')
    replace_once(PYPROJECT, r'^version = "[^"]+"', f'version = "{version}"')
    print(f"Bumped {old} -> {version}. Review the changes, then publish with:\n")
    print(f'  git commit -am "Release {version}"')
    print(f'  git tag -a v{version} -m "Termit {version}"')
    print(f"  git push origin main v{version}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
