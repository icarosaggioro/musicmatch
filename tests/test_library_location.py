"""Tests for LibraryLocationManager and ADR 0012 governance safeguards."""

import json
from pathlib import Path
from unittest.mock import patch
import pytest

from musicmatch.config import PROJECT_ROOT
from musicmatch.services.location import LibraryLocationManager


def test_default_system_path_resolution():
    manager = LibraryLocationManager(config_path=Path("non_existent_config.json"))
    expected = (Path.home() / "Music" / "MusicMatch").resolve()
    assert manager.get_default_system_path() == expected


def test_resolve_with_environment_override(monkeypatch, tmp_path):
    custom_dir = tmp_path / "env_music"
    monkeypatch.setenv("MUSICMATCH_LIBRARY_DIR", str(custom_dir))

    manager = LibraryLocationManager(config_path=tmp_path / "cfg.json")
    resolved = manager.resolve_library_path()
    assert resolved == custom_dir.resolve()


def test_resolve_with_config_file(monkeypatch, tmp_path):
    monkeypatch.delenv("MUSICMATCH_LIBRARY_DIR", raising=False)
    config_file = tmp_path / "library_config.json"
    custom_dir = tmp_path / "config_music"

    config_file.write_text(json.dumps({"library_path": str(custom_dir)}), encoding="utf-8")

    manager = LibraryLocationManager(config_path=config_file)
    resolved = manager.resolve_library_path()
    assert resolved == custom_dir.resolve()


def test_critical_path_guard_rejects_root(tmp_path):
    manager = LibraryLocationManager(config_path=tmp_path / "cfg.json")

    with pytest.raises(ValueError, match="Root drive"):
        manager.validate_and_probe_path(Path("C:\\").resolve())


def test_critical_path_guard_rejects_system_directory(tmp_path):
    manager = LibraryLocationManager(config_path=tmp_path / "cfg.json")

    with pytest.raises(ValueError, match="critical system folder"):
        manager.validate_and_probe_path(Path("C:/Windows/System32"))


def test_critical_path_guard_rejects_project_source_tree(tmp_path):
    manager = LibraryLocationManager(config_path=tmp_path / "cfg.json")

    with pytest.raises(ValueError, match="project source directory"):
        manager.validate_and_probe_path(PROJECT_ROOT / "src" / "musicmatch")


def test_validate_and_probe_path_success(tmp_path):
    target = tmp_path / "valid_library"
    manager = LibraryLocationManager(config_path=tmp_path / "cfg.json")

    validated = manager.validate_and_probe_path(target)
    assert validated.exists()
    assert validated == target.resolve()
    # Ensure probe file was cleaned up
    assert not (validated / ".musicmatch_probe").exists()


def test_ensure_namespaces_scaffolding(tmp_path):
    target = tmp_path / "scaffold_lib"
    target.mkdir(parents=True, exist_ok=True)
    manager = LibraryLocationManager(config_path=tmp_path / "cfg.json")

    manager.ensure_namespaces(target)
    assert (target / "Artists").is_dir()
    assert (target / "Various Artists").is_dir()
    assert (target / "Collections").is_dir()


def test_set_library_path_persists_and_scaffolds(tmp_path):
    target = tmp_path / "new_library"
    cfg = tmp_path / "cfg.json"
    manager = LibraryLocationManager(config_path=cfg)

    saved_path = manager.set_library_path(target)
    assert saved_path == target.resolve()
    assert (target / "Artists").is_dir()
    assert (target / "Various Artists").is_dir()
    assert (target / "Collections").is_dir()

    # Verify persisted config file
    assert cfg.exists()
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["library_path"] == str(target.resolve()).replace("\\", "/")


def test_validate_and_probe_path_fails_on_permission_error(tmp_path):
    target = tmp_path / "unwritable_dir"
    manager = LibraryLocationManager(config_path=tmp_path / "cfg.json")

    # Mock Path.write_bytes to raise PermissionError
    with patch.object(Path, "write_bytes", side_effect=PermissionError("Access Denied")):
        with pytest.raises(PermissionError, match="failed write capability probe"):
            manager.validate_and_probe_path(target)
