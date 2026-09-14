r"""Managed Library Location Manager and Cross-Platform Governance.

Follows ADR 0012:
1. Cross-platform resolution: .env > config file > ~/Music/MusicMatch.
2. Critical Path Guard: Rejects OS roots (C:\, /, /etc, C:\Windows, project root).
3. Atomic Write Probe: Ensures read/write capabilities via temporary probe file.
4. Namespace Scaffolding: Scaffolds Artists/, Various Artists/, and Collections/.
"""

import json
import os
from pathlib import Path
from typing import Optional, Union

from musicmatch.config import PROJECT_ROOT, settings

# System critical path substrings to reject (case-insensitive)
DISALLOWED_PATH_PATTERNS = (
    "windows",
    "winnt",
    "program files",
    "program files (x86)",
    "system32",
    "syswow64",
    "/etc",
    "/usr",
    "/var",
    "/bin",
    "/sbin",
    "/boot",
    "/dev",
)


class LibraryLocationManager:
    """Manages the canonical on-disk storage location for the Managed Library."""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self.config_file = config_path or (PROJECT_ROOT / "data" / "library_config.json")
        self._cached_path: Optional[Path] = None

    @classmethod
    def get_default_system_path(cls) -> Path:
        """Returns the canonical OS user Music directory: ~/Music/MusicMatch."""
        return (Path.home() / "Music" / "MusicMatch").resolve()

    def resolve_library_path(self) -> Path:
        """Resolves active library path following ADR 0012 precedence:
        1. Environment variable / .env (MUSICMATCH_LIBRARY_DIR)
        2. Dynamic local config (library_config.json)
        3. Cross-platform OS fallback (~/Music/MusicMatch)
        """
        # 1. Environment variable override
        env_override = os.getenv("MUSICMATCH_LIBRARY_DIR", settings.MANAGED_LIBRARY_DIR).strip()
        if env_override:
            return Path(env_override).resolve()

        # 2. Dynamic persistent configuration
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                stored_path = data.get("library_path", "").strip()
                if stored_path:
                    return Path(stored_path).resolve()
            except Exception:
                pass

        # 3. System fallback
        return self.get_default_system_path()

    def validate_and_probe_path(self, target_path: Union[str, Path]) -> Path:
        """Validates path against Critical Path Guards and performs Atomic Write Probe.

        Raises:
            ValueError: If path violates critical OS or project boundaries.
            PermissionError: If path is read-only or not writable.
        """
        resolved = Path(target_path).resolve()

        # Guard 1: Check root directories (e.g. C:\, /, D:\)
        if resolved.parent == resolved or str(resolved) in ("/", "\\"):
            raise ValueError(f"Root drive '{resolved}' cannot be used as a Managed Library root.")

        # Guard 2: Disallow critical system directories
        normalized_str = str(resolved).lower().replace("\\", "/")
        for pattern in DISALLOWED_PATH_PATTERNS:
            if pattern in normalized_str:
                raise ValueError(
                    f"Path '{resolved}' contains critical system folder '{pattern}' and is disallowed."
                )

        # Guard 3: Disallow placing inside project source code tree
        project_root_str = str(PROJECT_ROOT.resolve()).lower().replace("\\", "/")
        src_path_str = str((PROJECT_ROOT / "src").resolve()).lower().replace("\\", "/")
        if normalized_str == project_root_str or normalized_str.startswith(src_path_str):
            raise ValueError(
                f"Path '{resolved}' cannot be placed inside the project source directory."
            )

        # Create target directory if it does not exist
        try:
            resolved.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PermissionError(
                f"Cannot create Managed Library directory '{resolved}': {exc}"
            ) from exc

        # Guard 4: Atomic Write Probe
        probe_file = resolved / ".musicmatch_probe"
        try:
            probe_file.write_bytes(b"probe_test")
            if probe_file.exists():
                probe_file.unlink()
        except OSError as exc:
            raise PermissionError(
                f"Target path '{resolved}' failed write capability probe (read-only or permission denied): {exc}"
            ) from exc

        return resolved

    def ensure_namespaces(self, library_root: Path) -> None:
        """Scaffolds the 3 top-level canonical taxonomy namespaces (ADR 0011)."""
        (library_root / "Artists").mkdir(parents=True, exist_ok=True)
        (library_root / "Various Artists").mkdir(parents=True, exist_ok=True)
        (library_root / "Collections").mkdir(parents=True, exist_ok=True)

    def set_library_path(self, new_path: Union[str, Path]) -> Path:
        """Validates, probes, scaffolds, and persists the new Managed Library path."""
        validated = self.validate_and_probe_path(new_path)
        self.ensure_namespaces(validated)

        # Persist to local config file
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"library_path": str(validated).replace("\\", "/")}
        self.config_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        self._cached_path = validated
        return validated


# Global default instance
library_location_manager = LibraryLocationManager()
