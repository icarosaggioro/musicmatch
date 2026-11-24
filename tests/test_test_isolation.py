"""Guards for test isolation: the suite must never touch real data (see conftest.py).

These tests protect the protection: they fail if importing the application starts creating
files again, if the session stops running in its sandbox, or if the per-test guard stops
catching writes to the project tree or to the real Managed Library.
"""

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import conftest
from isolation import FilesystemGuard, changes, snapshot

TESTS_DIR = Path(__file__).resolve().parent


def test_guard_reports_created_modified_and_deleted_entries(tmp_path):
    watched = tmp_path / "project"
    (watched / "data").mkdir(parents=True)
    (watched / "data" / "keep.txt").write_text("a")
    (watched / "data" / "edit.txt").write_text("a")
    (watched / "data" / "drop.txt").write_text("a")
    guard = FilesystemGuard([watched, tmp_path / "library"])
    guard.start()

    (watched / "data" / "new.db").write_bytes(b"x")
    (watched / "data" / "edit.txt").write_text("changed")
    (watched / "data" / "drop.txt").unlink()
    (watched / "Playlists").mkdir()  # empty folders count too
    (tmp_path / "library").mkdir()  # a watched root that did not exist
    (watched / "__pycache__").mkdir()  # tooling output is ignored
    (watched / "__pycache__" / "x.pyc").write_bytes(b"x")
    (watched / ".coverage").write_text("x")

    found = guard.violations()
    assert f"+ {watched / 'data' / 'new.db'}" in found
    assert f"~ {watched / 'data' / 'edit.txt'}" in found
    assert f"- {watched / 'data' / 'drop.txt'}" in found
    assert f"+ {watched / 'Playlists'}" in found
    assert f"+ {tmp_path / 'library'} (created)" in found
    assert not any("__pycache__" in line or ".coverage" in line or "keep.txt" in line for line in found)
    assert len(found) == 5


def test_guard_reports_a_deleted_root(tmp_path):
    (tmp_path / "lib").mkdir()
    before = snapshot(tmp_path / "lib")
    shutil.rmtree(tmp_path / "lib")
    assert changes(tmp_path / "lib", before, snapshot(tmp_path / "lib")) == [f"- {tmp_path / 'lib'} (deleted)"]


def test_the_session_runs_in_a_sandbox():
    from musicmatch.config import settings
    from musicmatch.services.downloader import audio_downloader_service
    from musicmatch.services.location import library_location_manager

    sandbox = conftest.SANDBOX.resolve()
    for name in ("DATABASE_PATH", "STAGING_DIR", "LOG_DIR", "LIBRARY_CONFIG_PATH"):
        value = Path(getattr(settings, name)).resolve()
        assert value.is_relative_to(sandbox), f"settings.{name} = {value} is outside the test sandbox"
    assert Path.home().resolve().is_relative_to(sandbox)
    assert library_location_manager.resolve_library_path().resolve().is_relative_to(sandbox)
    assert audio_downloader_service.staging_dir.resolve().is_relative_to(sandbox)
    assert not conftest.PROJECT_ROOT.resolve().is_relative_to(sandbox)


def test_importing_the_application_creates_no_files(tmp_path):
    """A fresh interpreter imports every module: no database, folder or log may appear.
    (Process-wide services must open their resources on first use, not at import.)"""
    target = tmp_path / "would-be-created"
    env = dict(os.environ)
    env.update({
        "HOME": str(target / "home"), "USERPROFILE": str(target / "home"),
        "DATABASE_PATH": str(target / "data" / "musicmatch.db"),
        "MUSICMATCH_STAGING_DIR": str(target / "data" / "staging"),
        "MUSICMATCH_LOG_DIR": str(target / "logs"),
        "MUSICMATCH_LIBRARY_CONFIG": str(target / "data" / "library_config.json"),
        "MUSICMATCH_LIBRARY_DIR": str(target / "library"),
    })
    script = textwrap.dedent("""
        import importlib, pkgutil, musicmatch
        names = [m.name for m in pkgutil.walk_packages(musicmatch.__path__, "musicmatch.")]
        for name in names:
            importlib.import_module(name)
        print(len(names))
    """)
    result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert int(result.stdout.strip()) > 40  # every module was really imported
    assert not target.exists(), f"importing created: {sorted(str(p) for p in target.rglob('*'))}"


def test_the_guard_fails_tests_that_write_outside_the_sandbox(tmp_path):
    """Runs a tiny inner pytest session with the real conftest.py against a throwaway project."""
    project = tmp_path / "project"
    inner_tests = project / "tests"
    inner_tests.mkdir(parents=True)
    for name in ("conftest.py", "isolation.py"):
        shutil.copy(TESTS_DIR / name, inner_tests / name)
    report = tmp_path / "sandbox.txt"
    (inner_tests / "test_inner.py").write_text(textwrap.dedent(f"""
        import os
        from pathlib import Path
        import conftest

        def test_writes_into_the_project():
            leak = Path(__file__).resolve().parent.parent / "data" / "leak.db"
            leak.parent.mkdir()
            leak.write_bytes(b"x")

        def test_falls_back_to_the_default_database():
            default = Path(os.environ["DATABASE_PATH"])
            default.parent.mkdir(parents=True, exist_ok=True)
            default.write_bytes(b"")

        def test_clean(tmp_path):
            (tmp_path / "ok.txt").write_text("fine")
            Path({str(report)!r}).write_text(str(conftest.SANDBOX))
            assert Path.home().is_relative_to(conftest.SANDBOX)
    """), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(inner_tests)],
        cwd=project, capture_output=True, text=True, timeout=120,
    )
    out = result.stdout
    assert result.returncode != 0
    assert "test_writes_into_the_project wrote outside its sandbox" in out
    assert f"+ {project / 'data' / 'leak.db'}" in out
    assert "test_falls_back_to_the_default_database wrote outside its sandbox" in out
    # pytest counts a test whose body passed but whose teardown (the guard) failed as both
    # "passed" and "error"; the run fails either way.
    assert "3 passed, 2 errors" in out and "ERROR at teardown of test_clean" not in out, out
    assert not Path(report.read_text()).exists()  # the session sandbox is removed at the end
