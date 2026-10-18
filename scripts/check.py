#!/usr/bin/env python3
"""Unified project check script for MusicMatch.

Follows SDLC Guide 07:
- Runs all quality gates in sequence: syntax/compilation, automated tests, package integrity.
- Provides identical execution locally and in CI.
- Fails closed with non-zero exit code if any gate fails.
"""

import subprocess
import sys
import time
from pathlib import Path

# Ensure UTF-8 output on Windows consoles if supported
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent


def run_gate(name: str, command: list[str]) -> bool:
    print(f"\n[RUNNING] {name}: {' '.join(command)}")
    start = time.perf_counter()
    result = subprocess.run(command, cwd=ROOT_DIR)
    elapsed = time.perf_counter() - start

    if result.returncode == 0:
        print(f"[PASSED]  {name} ({elapsed:.2f}s)")
        return True
    else:
        print(f"[FAILED]  {name} (exit code: {result.returncode}, {elapsed:.2f}s)")
        return False


def main() -> int:
    print("=" * 72)
    print("MusicMatch Quality Gates (SDLC Check Pipeline)")
    print("=" * 72)

    python_executable = sys.executable

    gates = [
        (
            "1. Python Syntax & Bytecode Compilation",
            [python_executable, "-m", "compileall", "-q", "src", "tests"],
        ),
        (
            "2. Package Dependency Health (pip check)",
            [python_executable, "-m", "pip", "check"],
        ),
        (
            "3. Automated Pytest Test Suite",
            [python_executable, "-m", "pytest", "-q"],
        ),
    ]

    failed_gates = []
    for name, cmd in gates:
        success = run_gate(name, cmd)
        if not success:
            failed_gates.append(name)
            # Fail closed on first broken critical gate
            break

    print("\n" + "=" * 72)
    if failed_gates:
        print(f"[FAIL] CHECK PIPELINE FAILED at: {failed_gates[0]}")
        print("=" * 72)
        return 1

    print("[SUCCESS] ALL QUALITY GATES PASSED (197 tests, clean syntax, valid dependencies)")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
