"""Web Audio Metadata Sanitizer.

Follows ADR 0011:
- Strips SEO noise from web titles (Official Video, [4K], [Remastered], etc.).
- Extracts canonical Artist and Title.
- Preserves removed facets (remastered, live, acoustic, collaborators) as extended_metadata.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


@dataclass
class SanitizedMetadata:
    """Consolidated clean metadata and preserved semantic facets."""

    artist: str
    title: str
    extended_metadata: Dict[str, Any] = field(default_factory=dict)


class MetadataSanitizer:
    """Deterministic regex sanitizer for web audio video titles."""

    # Patterns to detect version facets for preservation in extended_metadata
    VERSION_FACETS = [
        (r"\b(remaster(?:ed)?(?:\s*\d{4})?)\b", "remastered"),
        (r"\b(live(?:\s+at\s+[\w\s]+|\s*\d{4})?|ao\s+vivo)\b", "live"),
        (r"\b(acoustic|ac[uú]stico)\b", "acoustic"),
        (r"\b(instrumental)\b", "instrumental"),
        (r"\b(radio\s+edit)\b", "radio_edit"),
        (r"\b(extended\s+mix)\b", "extended_mix"),
    ]

    # Featured artist patterns: (feat. Artist) or ft. Artist (supports hyphens like Jay-Z)
    FEAT_PATTERN = re.compile(
        r"[\(\[\s]*(?:feat\.?|ft\.?|featuring)\s+([\w\s,&.-]+)[\)\]]*", re.IGNORECASE
    )

    # Keywords that indicate a bracketed expression is metadata noise to be stripped
    NOISE_KEYWORD_REGEX = (
        r"official|video|audio|lyrics?|visualizer|clip|clipe|hd|4k|1080p|720p|uhd|hq|"
        r"remaster|live|ao\s+vivo|acoustic|ac[uú]stico|letra"
    )

    # Clean uploader suffixes
    UPLOADER_CLEAN_PATTERNS = [
        r" - Topic$",
        r"VEVO$",
        r" Official$",
        r"Channel$",
    ]

    def sanitize(self, raw_title: str, uploader: Optional[str] = None) -> SanitizedMetadata:
        """Cleans a raw web title, returning canonical artist, title, and extended metadata."""
        cleaned = raw_title.strip()
        extended_metadata: Dict[str, Any] = {}

        # 1. Extract featured artists
        feat_match = self.FEAT_PATTERN.search(cleaned)
        if feat_match:
            collaborator = feat_match.group(1).strip().strip(")]")
            if collaborator:
                extended_metadata["collaborators"] = collaborator
            cleaned = self.FEAT_PATTERN.sub("", cleaned)

        # 2. Extract and record version facets before stripping
        for pattern, facet_key in self.VERSION_FACETS:
            match = re.search(pattern, cleaned, re.IGNORECASE)
            if match:
                extended_metadata[facet_key] = match.group(1).strip()

        # 3. Strip entire bracketed expressions containing noise keywords
        # E.g. [4K Remastered], (Official Music Video), (Acoustic Version), (Ao Vivo)
        cleaned = re.sub(
            rf"\([^\)]*(?:{self.NOISE_KEYWORD_REGEX})[^\)]*\)", "", cleaned, flags=re.IGNORECASE
        )
        cleaned = re.sub(
            rf"\[[^\]]*(?:{self.NOISE_KEYWORD_REGEX})[^\]]*\]", "", cleaned, flags=re.IGNORECASE
        )

        # 4. Strip standalone unbracketed noise phrases
        standalone_noise = [
            r"\b(?:official\s+video|official\s+audio|music\s+video|audio\s+oficial|clipe\s+oficial)\b",
            r"\b(?:4k|1080p|720p|uhd|hd|hq)\b",
        ]
        for noise in standalone_noise:
            cleaned = re.sub(noise, "", cleaned, flags=re.IGNORECASE)

        # Clean dangling brackets or punctuation
        cleaned = re.sub(r"[\(\[\{\)\]\}]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_|#")

        # 5. Split Artist and Title if separator exists
        artist, title = self._split_artist_title(cleaned, uploader)

        return SanitizedMetadata(
            artist=artist,
            title=title,
            extended_metadata=extended_metadata,
        )

    def _split_artist_title(
        self, cleaned_title: str, uploader: Optional[str] = None
    ) -> Tuple[str, str]:
        """Splits string into (Artist, Title)."""
        delimiters = [" - ", " – ", " — ", " : ", " | "]
        for delim in delimiters:
            if delim in cleaned_title:
                parts = cleaned_title.split(delim, 1)
                part_artist = parts[0].strip()
                part_title = parts[1].strip()
                if part_artist and part_title:
                    return part_artist, part_title

        # No delimiter found. Clean uploader as artist fallback
        clean_uploader = (uploader or "").strip()
        for pat in self.UPLOADER_CLEAN_PATTERNS:
            clean_uploader = re.sub(pat, "", clean_uploader, flags=re.IGNORECASE).strip()

        artist = clean_uploader or "Unknown Artist"
        title = cleaned_title or "Unknown Title"
        return artist, title


# Global default instance
metadata_sanitizer = MetadataSanitizer()
