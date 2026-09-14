"""Unit tests for MetadataSanitizer and extended metadata extraction."""

import pytest
from musicmatch.services.sanitizer import MetadataSanitizer


@pytest.fixture
def sanitizer():
    return MetadataSanitizer()


def test_sanitize_standard_youtube_title(sanitizer):
    raw = "Queen - Bohemian Rhapsody (Official Video) [4K Remastered]"
    res = sanitizer.sanitize(raw)

    assert res.artist == "Queen"
    assert res.title == "Bohemian Rhapsody"
    assert "remastered" in res.extended_metadata
    assert "Remastered" in res.extended_metadata["remastered"]


def test_sanitize_featured_artist(sanitizer):
    raw = "Linkin Park - Numb ft. Jay-Z (Official Music Video)"
    res = sanitizer.sanitize(raw)

    assert res.artist == "Linkin Park"
    assert res.title == "Numb"
    assert res.extended_metadata.get("collaborators") == "Jay-Z"


def test_sanitize_live_performance(sanitizer):
    raw = "Pink Floyd - Comfortably Numb (Live at Pompeii 2016)"
    res = sanitizer.sanitize(raw)

    assert res.artist == "Pink Floyd"
    assert res.title == "Comfortably Numb"
    assert "live" in res.extended_metadata
    assert "Live at Pompeii 2016" in res.extended_metadata["live"]


def test_sanitize_acoustic_version(sanitizer):
    raw = "Foo Fighters - Everlong (Acoustic Version)"
    res = sanitizer.sanitize(raw)

    assert res.artist == "Foo Fighters"
    assert res.title == "Everlong"
    assert "acoustic" in res.extended_metadata


def test_sanitize_portuguese_video_tags(sanitizer):
    raw = "Legião Urbana - Pais e Filhos (Clipe Oficial) [HD]"
    res = sanitizer.sanitize(raw)

    assert res.artist == "Legião Urbana"
    assert res.title == "Pais e Filhos"


def test_sanitize_without_separator_uses_uploader(sanitizer):
    raw = "Bohemian Rhapsody (Audio)"
    res = sanitizer.sanitize(raw, uploader="Queen Official")

    assert res.artist == "Queen"
    assert res.title == "Bohemian Rhapsody"


def test_sanitize_various_separators(sanitizer):
    # En-dash
    res1 = sanitizer.sanitize("Led Zeppelin – Stairway to Heaven")
    assert res1.artist == "Led Zeppelin"
    assert res1.title == "Stairway to Heaven"

    # Pipe separator
    res2 = sanitizer.sanitize("Iron Maiden | The Trooper")
    assert res2.artist == "Iron Maiden"
    assert res2.title == "The Trooper"
