"""Test isolation helpers: filesystem snapshots of the places tests must never touch.

Used by conftest.py (the per-test guard) and by test_test_isolation.py (which tests the guard
itself). Kept free of pytest and of musicmatch imports, so conftest can use it before any
application code is imported.
"""

import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# Written by tooling, not by the code under test: never part of a snapshot.
SKIPPED_DIRS = {".venv", "venv", ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "htmlcov"}
SKIPPED_FILE_PREFIXES = (".coverage",)

Entry = Tuple[str, int, int]  # kind ('f' file / 'd' directory), size, mtime_ns
Snapshot = Optional[Dict[str, Entry]]  # None: the root does not exist


def snapshot(root: Path) -> Snapshot:
    """Every file and directory under `root` (relative path -> kind, size, mtime)."""
    root = Path(root)
    if not root.exists():
        return None
    entries: Dict[str, Entry] = {}
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIPPED_DIRS and not d.endswith(".egg-info"))
        for name in dirs:
            path = os.path.join(current, name)
            entries[os.path.relpath(path, root)] = ("d", 0, 0)
        for name in files:
            if name.startswith(SKIPPED_FILE_PREFIXES):
                continue
            path = os.path.join(current, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue  # vanished while walking
            entries[os.path.relpath(path, root)] = ("f", stat.st_size, stat.st_mtime_ns)
    return entries


def changes(root: Path, before: Snapshot, after: Snapshot) -> List[str]:
    """Human-readable differences between two snapshots of `root` ('+' created, '~' modified, '-' deleted)."""
    if before is None and after is None:
        return []
    if before is None:
        return [f"+ {root} (created)"] + [f"+ {Path(root) / p}" for p in sorted(after)]
    if after is None:
        return [f"- {root} (deleted)"]
    lines = [f"+ {Path(root) / p}" for p in sorted(after.keys() - before.keys())]
    lines += [f"- {Path(root) / p}" for p in sorted(before.keys() - after.keys())]
    lines += [f"~ {Path(root) / p}" for p in sorted(before.keys() & after.keys())
              if before[p][0] == "f" and before[p] != after[p]]
    return lines


class FilesystemGuard:
    """Snapshots `roots` before a test and reports whatever the test changed in them."""

    def __init__(self, roots: Iterable[Path]) -> None:
        self.roots = [Path(r) for r in roots]
        self._before: List[Snapshot] = []

    def start(self) -> None:
        self._before = [snapshot(root) for root in self.roots]

    def violations(self) -> List[str]:
        found: List[str] = []
        for root, before in zip(self.roots, self._before):
            found.extend(changes(root, before, snapshot(root)))
        return found
