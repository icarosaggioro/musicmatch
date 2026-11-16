"""Guards against drift in repository metadata.

The supported minimum Python version is declared in three places that must agree:
the project rules (.agents/rules/project.md), packaging metadata (pyproject.toml)
and the CI runtime (.github/workflows/ci.yml). Build artifacts such as egg-info
must also stay out of version control.
"""

import re
import subprocess
import tomllib
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def _requires_python_minimum() -> str:
    pyproject = tomllib.loads((ROOT_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    spec = pyproject["project"]["requires-python"]
    match = re.fullmatch(r">=\s*(\d+\.\d+(?:\.\d+)?)", spec.strip())
    assert match, f"requires-python must be a single '>=X.Y[.Z]' bound, got {spec!r}"
    return match.group(1)


def _project_rules_minimum() -> str:
    rules = (ROOT_DIR / ".agents" / "rules" / "project.md").read_text(encoding="utf-8")
    match = re.search(r"Python (\d+\.\d+(?:\.\d+)?)\+", rules)
    assert match, "project.md must state the minimum Python version as 'Python X.Y[.Z]+'"
    return match.group(1)


def _ci_python_version() -> str:
    workflow = (ROOT_DIR / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    match = re.search(r"python-version:\s*[\"']?(\d+\.\d+(?:\.\d+)?)[\"']?", workflow)
    assert match, "ci.yml must pin a python-version"
    return match.group(1)


def _minor(version: str) -> tuple[int, int]:
    major, minor = version.split(".")[:2]
    return int(major), int(minor)


def test_requires_python_matches_project_rules() -> None:
    assert _requires_python_minimum() == _project_rules_minimum()


def test_ci_runs_the_supported_minor_version() -> None:
    # CI pins the minor series (e.g. "3.14"), which resolves to the latest patch
    # release, so it always satisfies a patch-level minimum such as 3.14.6.
    assert _minor(_ci_python_version()) == _minor(_requires_python_minimum())


def test_egg_info_is_not_tracked() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "--", "*.egg-info/*"],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert tracked == "", f"egg-info build artifacts are tracked by git:\n{tracked}"


def test_package_version_matches_pyproject() -> None:
    import musicmatch

    pyproject = tomllib.loads((ROOT_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    assert musicmatch.__version__ == pyproject["project"]["version"]


def test_license_uses_spdx_expression() -> None:
    # The TOML-table form `license = { text = "..." }` is deprecated by setuptools,
    # which stops supporting it after 2027-02-18; the SPDX string needs setuptools>=77.
    pyproject = tomllib.loads((ROOT_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["license"] == "MIT"
    assert "LICENSE" in pyproject["project"]["license-files"]
    assert "setuptools>=77.0.0" in pyproject["build-system"]["requires"]
