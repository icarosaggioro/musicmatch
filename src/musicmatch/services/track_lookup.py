"""Finds the track a person means by an ID, a short ID or a search text ('/play', agent tool).

IDs are unambiguous; text goes to the FTS5 index. When the text matches several tracks the
caller gets the candidates instead of a guess, unless exactly one of them has that very title
(or 'artist title').
"""

import re
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from musicmatch.domain.models import Track
from musicmatch.domain.text import fold_text

MIN_PREFIX_HEX = 4
MAX_CANDIDATES = 10


class TrackLookup(BaseModel):
    """Outcome of a lookup: one track, several candidates to choose from, or nothing."""

    track: Optional[Track] = Field(default=None, description="The track, when the reference identifies exactly one")
    candidates: List[Track] = Field(default_factory=list, description="Tracks to choose from when it is ambiguous")
    more: bool = Field(default=False, description="True when there are more candidates than the ones listed")


def id_prefix(ref: str) -> Optional[str]:
    """The canonical 'trk_<hex>' prefix when `ref` can be an ID or a short ID, else None."""
    cleaned = ref.strip().lower()
    hex_part = cleaned.removeprefix("trk_")
    if len(hex_part) >= MIN_PREFIX_HEX and all(c in "0123456789abcdef" for c in hex_part):
        return f"trk_{hex_part}"
    return None


def _words(text: str) -> List[str]:
    return re.findall(r"\w+", text)


def _search(repo: Any, text: str, limit: int) -> List[Track]:
    """Full-text search where every word is literal: punctuation and words like 'not' or 'or' in a
    title ('Queen - Bohemian Rhapsody', 'AC/DC') are never FTS5 operators."""
    words = _words(text)
    if not words:
        return []
    return repo.search_fulltext(" ".join(f'"{word}"*' for word in words), limit=limit)


def find_track(repo: Any, ref: str) -> TrackLookup:
    """Resolves `ref` against the catalog (see the module docstring)."""
    ref = ref.strip()
    if not ref:
        return TrackLookup()
    exact = repo.get_track(ref)
    if isinstance(exact, Track):
        return TrackLookup(track=exact)

    prefix = id_prefix(ref)
    by_id = repo.find_tracks_by_id_prefix(prefix, limit=MAX_CANDIDATES + 1) if prefix else []
    by_text = [] if ref.lower().startswith("trk_") else _search(repo, ref, MAX_CANDIDATES + 1)

    # A short ID may also be a word or a year in a title ('1985'): then both are offered.
    found = list({track.id: track for track in by_id + by_text}.values())
    if len(found) == 1:
        return TrackLookup(track=found[0])
    if not by_id:
        wanted = [fold_text(word) for word in _words(ref)]
        titled = [
            t for t in found
            if wanted in ([fold_text(w) for w in _words(t.title)], [fold_text(w) for w in _words(f"{t.artist} {t.title}")])
        ]
        if len(titled) == 1:
            return TrackLookup(track=titled[0])
    return TrackLookup(candidates=found[:MAX_CANDIDATES], more=len(found) > MAX_CANDIDATES)


__all__ = ["TrackLookup", "find_track", "id_prefix", "MIN_PREFIX_HEX", "MAX_CANDIDATES"]
