"""Guards that Markdown links in project-owned docs resolve inside the repository.

Links such as ``file:///c:/...`` only work on the author's machine and break on
GitHub. Package-owned SDLC files (.agents/, .claude/) are excluded because
package updates overwrite them.
"""

import re
import subprocess
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
EXCLUDED_PREFIXES = (".agents/", ".claude/")
# Markdown inline links: [text](target), ignoring an optional "title".
LINK_PATTERN = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")


def _project_docs() -> list[str]:
    tracked = subprocess.run(
        ["git", "ls-files", "--", "*.md"],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [path for path in tracked if not path.startswith(EXCLUDED_PREFIXES)]


def _links(doc: str) -> list[str]:
    return LINK_PATTERN.findall((ROOT_DIR / doc).read_text(encoding="utf-8"))


@pytest.mark.parametrize("doc", _project_docs())
def test_doc_has_no_machine_local_links(doc: str) -> None:
    local = [target for target in _links(doc) if target.lower().startswith("file:")]
    assert local == [], f"{doc} links to machine-local paths: {local}"


@pytest.mark.parametrize("doc", _project_docs())
def test_doc_relative_links_resolve(doc: str) -> None:
    broken = []
    for target in _links(doc):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE) or target.startswith("#"):
            continue  # external URL, mailto:, file: (checked above) or in-page anchor
        path = target.split("#", 1)[0]
        if not (ROOT_DIR / doc).parent.joinpath(path).resolve().exists():
            broken.append(target)
    assert broken == [], f"{doc} has relative links to missing files: {broken}"
