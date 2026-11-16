"""Guards that every CI job declares a timeout.

Without `timeout-minutes`, a hung step runs until GitHub's 360-minute default,
burning Actions minutes and leaving the pull request without a result.
"""

import re
from pathlib import Path

import pytest

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / ".github" / "workflows"
EXPECTED_TIMEOUTS = {"ci.yml": 15, "ci-codereview.yml": 20}


def _job_blocks(workflow: str) -> dict[str, str]:
    """Split the `jobs:` section into {job_id: job body} using indentation."""
    jobs_section = workflow.split("\njobs:\n", 1)[1]
    blocks: dict[str, str] = {}
    current = None
    for line in jobs_section.splitlines():
        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if match:
            current = match.group(1)
            blocks[current] = ""
        elif current is not None:
            blocks[current] += line + "\n"
    return blocks


@pytest.mark.parametrize("workflow_name", sorted(EXPECTED_TIMEOUTS))
def test_every_job_declares_timeout(workflow_name: str) -> None:
    workflow = (WORKFLOWS_DIR / workflow_name).read_text(encoding="utf-8")
    blocks = _job_blocks(workflow)
    assert blocks, f"{workflow_name} has no jobs"
    for job_id, body in blocks.items():
        match = re.search(r"^    timeout-minutes:\s*(\d+)\s*$", body, re.MULTILINE)
        assert match, f"{workflow_name}: job '{job_id}' has no timeout-minutes"
        assert int(match.group(1)) == EXPECTED_TIMEOUTS[workflow_name]
