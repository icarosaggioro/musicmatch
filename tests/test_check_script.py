"""Regression test for scripts/check.py's success summary."""

import importlib.util
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def _load_check_module():
    spec = importlib.util.spec_from_file_location("check_script", ROOT_DIR / "scripts" / "check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_success_summary_does_not_state_a_hardcoded_test_count(monkeypatch, capsys) -> None:
    check = _load_check_module()
    monkeypatch.setattr(check, "run_gate", lambda name, command: True)

    assert check.main() == 0

    output = capsys.readouterr().out
    assert "ALL QUALITY GATES PASSED" in output
    # pytest prints the real count itself; a number here would go stale.
    assert not re.search(r"\d+\s+tests", output), output
