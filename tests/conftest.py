"""Test session isolation: tests never touch real data.

1. A throwaway sandbox for the whole session, installed *before* any application code is
   imported (this module is loaded before the test modules): the catalog database, staging
   area, developer log, library config and home folder (so ~/Music/MusicMatch, the default
   Managed Library) all point into it. Setting these variables explicitly also stops a
   developer's .env (python-dotenv never overrides existing variables) from aiming the tests
   at real data.
2. A per-test guard that fails any test which creates, modifies or deletes anything in the
   project tree or in the real ~/Music/MusicMatch, naming the files. Tests must use tmp_path
   and in-memory databases.
3. The guard also watches the sandbox's *default* data folder: a test that falls back to the
   global catalog database or staging area (instead of injecting its own) would share state
   with every other such test and depend on their order, so it fails too.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from isolation import FilesystemGuard

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REAL_HOME = Path.home()  # captured before the sandbox redirects it
REAL_MANAGED_LIBRARY = REAL_HOME / "Music" / "MusicMatch"

SANDBOX = Path(tempfile.mkdtemp(prefix="musicmatch-tests-"))
SANDBOX_ENV = {
    "HOME": str(SANDBOX / "home"),  # Path.home() on POSIX
    "USERPROFILE": str(SANDBOX / "home"),  # Path.home() on Windows
    "DATABASE_PATH": str(SANDBOX / "data" / "musicmatch.db"),
    "MUSICMATCH_STAGING_DIR": str(SANDBOX / "data" / "staging"),
    "MUSICMATCH_LOG_DIR": str(SANDBOX / "logs"),
    "MUSICMATCH_LIBRARY_CONFIG": str(SANDBOX / "data" / "library_config.json"),
    "MUSICMATCH_LIBRARY_DIR": "",  # default resolution -> the sandbox home
}
os.environ.update(SANDBOX_ENV)
(SANDBOX / "home").mkdir()

_guard = FilesystemGuard([PROJECT_ROOT, REAL_MANAGED_LIBRARY, SANDBOX / "data"])


@pytest.fixture(autouse=True)
def _no_writes_outside_the_sandbox(request):
    """Fails the test (at teardown) if it wrote to the project tree or the real managed library."""
    _guard.start()
    yield
    violations = _guard.violations()
    if violations:
        listed = "\n  ".join(violations[:20]) + ("\n  …" if len(violations) > 20 else "")
        pytest.fail(
            f"{request.node.nodeid} wrote outside its sandbox:\n  {listed}\n"
            "Tests must use tmp_path and in-memory databases (see tests/conftest.py).",
            pytrace=False,
        )


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(SANDBOX, ignore_errors=True)
