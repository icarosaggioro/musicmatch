"""Text normalization shared by the domain (queue sort keys, playlist names)."""

import unicodedata
from typing import Optional


def fold_text(text: Optional[str]) -> str:
    """Case- and accent-insensitive form: 'Érase' and 'erase' compare (and sort) equal."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold().strip()
