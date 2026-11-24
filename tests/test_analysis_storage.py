"""Storage tests for acoustic analysis: migration of existing databases and projection rules (ADR 0014)."""

import sqlite3

import pytest

from musicmatch.domain.analysis import ANALYSIS_VERSION, AudioFeatures, TrackAnalysis
from musicmatch.domain.models import Track
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository

# The 'tracks' table exactly as created by MusicMatch 0.2.0 (before ADR 0014).
LEGACY_TRACKS_DDL = """
CREATE TABLE tracks (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, artist TEXT NOT NULL, album TEXT NOT NULL, genre TEXT NOT NULL,
    duration_seconds REAL NOT NULL CHECK(duration_seconds >= 0), bitrate_kbps INTEGER NOT NULL CHECK(bitrate_kbps > 0),
    bpm REAL NOT NULL CHECK(bpm > 0), file_path TEXT UNIQUE NOT NULL, mood TEXT, lufs REAL, file_mtime REAL,
    file_size INTEGER, status TEXT DEFAULT 'AVAILABLE', year INTEGER, track_number INTEGER,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
);
"""


def _track(track_id="trk_1", **extra):
    values = dict(id=track_id, title="Song", artist="Artist", album="Album", genre="Pop", duration_seconds=180.0,
                  bitrate_kbps=320, bpm=120.0, file_path=f"/music/{track_id}.mp3", file_mtime=1000.0, file_size=4096)
    values.update(extra)
    return Track(**values)


def _analysis(track_id="trk_1", bpm=128.0, bpm_confidence=0.6, **features):
    values = dict(duration_seconds=180.0, sample_rate=44100, channels=2, decoder="ffmpeg", integrated_lufs=-8.5,
                  bpm=bpm, bpm_confidence=bpm_confidence, musical_key="E minor", camelot_key="9A",
                  fingerprint_algorithm="mmfp1", fingerprint_hash="f" * 64, fingerprint_frames=2,
                  fingerprint=b"\x01\x00\x00\x00\x02\x00\x00\x00", waveform_peaks=[0.5, 1.0], waveform_rms=[0.2, 0.4])
    values.update(features)
    return TrackAnalysis(track_id=track_id, source_mtime=1000.0, source_size=4096, features=AudioFeatures(**values))


def test_existing_database_is_migrated_in_place(tmp_path):
    db_path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(db_path)
    legacy.execute(LEGACY_TRACKS_DDL)
    legacy.execute(
        "INSERT INTO tracks (id, title, artist, album, genre, duration_seconds, bitrate_kbps, bpm, file_path) "
        "VALUES ('trk_old', 'Old', 'Artist', 'Album', 'Rock', 100, 192, 120, '/music/old.mp3')"
    )
    legacy.commit()
    legacy.close()

    repo = SQLiteTrackRepository(db_path=db_path)
    try:
        columns = {row["name"] for row in repo.conn.execute("PRAGMA table_info(tracks);")}
        assert {"musical_key", "bpm_source"} <= columns
        assert repo.conn.execute("SELECT name FROM sqlite_master WHERE name = 'track_analysis'").fetchone()
        old = repo.get_track("trk_old")
        assert old.title == "Old" and old.musical_key is None
        assert (old.bpm, old.duration_seconds, old.bitrate_kbps, old.file_path) == (120, 100, 192, "/music/old.mp3")
        assert old.bpm_source is None  # unknown
        assert [t.id for t in repo.get_tracks_pending_analysis()] == ["trk_old"]
    finally:
        repo.close()
    SQLiteTrackRepository(db_path=db_path).close()  # re-opening is idempotent


def test_save_round_trip_and_catalog_projection():
    repo = SQLiteTrackRepository(db_path=":memory:")
    repo.insert_track(_track())
    assert repo.save_analyses([_analysis()]) == 1

    stored = repo.get_analysis("trk_1")
    assert stored.analysis_version == ANALYSIS_VERSION and stored.analyzed_at
    assert stored.features.fingerprint == b"\x01\x00\x00\x00\x02\x00\x00\x00"
    assert stored.features.waveform_peaks == [0.502, 1.0]  # 8-bit quantized envelope
    track = repo.get_track("trk_1")
    assert (track.bpm, track.lufs, track.musical_key) == (128.0, -8.5, "E minor")
    assert repo.get_fingerprint_records("mmfp1")[0]["track_id"] == "trk_1"
    assert repo.get_fingerprint_records("other-algorithm") == []


def test_low_confidence_tempo_keeps_the_tag_bpm_and_orphans_are_ignored():
    repo = SQLiteTrackRepository(db_path=":memory:")
    repo.insert_track(_track(bpm=87.0))
    written = repo.save_analyses([_analysis(bpm=174.0, bpm_confidence=0.05), _analysis(track_id="trk_deleted")])
    assert written == 1
    assert repo.get_track("trk_1").bpm == 87.0
    assert repo.get_track("trk_1").lufs == -8.5
    assert repo.get_analysis("trk_deleted") is None


@pytest.mark.parametrize("source,before,after,after_source", [
    ("tag", 77.0, 77.0, "tag"),         # tags are never overwritten
    ("tag", 120.0, 120.0, "tag"),       # not even when the tag equals the placeholder
    ("default", 120.0, 128.0, "dsp"),
    ("dsp", 140.0, 128.0, "dsp"),       # a newer measurement replaces an older one
    (None, 120.0, 128.0, "dsp"),        # cataloged before bpm_source existed, at the placeholder
    (None, 77.0, 77.0, None),           # cataloged before bpm_source existed, from a tag
])
def test_measured_bpm_only_replaces_values_that_are_not_tags(source, before, after, after_source):
    repo = SQLiteTrackRepository(db_path=":memory:")
    repo.insert_track(_track(bpm=before, bpm_source=source))
    repo.save_analyses([_analysis(bpm=128.0)])
    track = repo.get_track("trk_1")
    assert (track.bpm, track.bpm_source) == (after, after_source)
    assert repo.get_analysis("trk_1").features.bpm == 128.0  # the measurement is always kept


def test_bpm_source_survives_every_write_path():
    repo = SQLiteTrackRepository(db_path=":memory:")
    repo.insert_batch([_track(bpm=77.0, bpm_source="tag")])
    track = repo.get_track("trk_1")
    track.title = "Retagged"
    repo.update_track(track)
    assert repo.get_track("trk_1").bpm_source == "tag"
    repo.insert_batch([_track(bpm=120.0, bpm_source="default")])  # rescan after the tag was removed
    assert repo.get_track("trk_1").bpm_source == "default"


def test_error_records_do_not_touch_the_catalog():
    repo = SQLiteTrackRepository(db_path=":memory:")
    repo.insert_track(_track(lufs=-14.0))
    repo.save_analyses([TrackAnalysis(track_id="trk_1", status="ERROR", error_message="corrupt",
                                      source_mtime=1000.0, source_size=4096)])
    assert repo.get_track("trk_1").lufs == -14.0
    assert repo.get_analysis("trk_1").features is None
    assert repo.get_analysis_counts() == {"available": 1, "analyzed": 0, "failed": 1, "pending": 0}


def test_pending_selection_by_stamp_version_path_and_ids():
    repo = SQLiteTrackRepository(db_path=":memory:")
    repo.insert_track(_track("trk_1", file_path="/music/rock/a.mp3"))
    repo.insert_track(_track("trk_2", file_path="/music/jazz/b.mp3"))
    repo.insert_track(_track("trk_3", file_path="/music/jazz/c.mp3", status="MISSING"))
    repo.save_analyses([_analysis("trk_1")])

    assert [t.id for t in repo.get_tracks_pending_analysis()] == ["trk_2"]
    assert repo.get_tracks_pending_analysis(path_prefix="/music/rock") == []
    assert [t.id for t in repo.get_tracks_pending_analysis(path_prefix="/music/rock", force=True)] == ["trk_1"]
    assert repo.get_tracks_pending_analysis(track_ids=[]) == []
    assert [t.id for t in repo.get_tracks_pending_analysis(track_ids=["trk_1", "trk_2"], force=True, limit=1)] == ["trk_1"]

    repo.insert_track(_track("trk_4", file_path="/music/myXband/d.mp3"))
    repo.insert_track(_track("trk_5", file_path="/music/my_band/e.mp3"))
    assert [t.id for t in repo.get_tracks_pending_analysis(path_prefix="/music/my_band")] == ["trk_5"]
    repo.delete_track("trk_4")
    repo.delete_track("trk_5")

    touched = repo.get_track("trk_1")
    touched.file_mtime = 2000.0  # e.g. /retag rewrote the file
    repo.update_track(touched)
    assert repo.count_pending_analysis() == 2

    repo.conn.execute("UPDATE track_analysis SET analysis_version = ?, source_mtime = 2000.0", (ANALYSIS_VERSION - 1,))
    assert repo.count_pending_analysis("/music/rock") == 1  # outdated algorithm version


def test_exact_fingerprint_groups_query():
    repo = SQLiteTrackRepository(db_path=":memory:")
    for tid in ("trk_1", "trk_2", "trk_3"):
        repo.insert_track(_track(tid))
    repo.save_analyses([_analysis("trk_1"), _analysis("trk_2"), _analysis("trk_3", fingerprint_hash="0" * 64)])
    groups = repo.get_exact_fingerprint_groups("mmfp1")
    assert [[row["track_id"] for row in group] for group in groups] == [["trk_1", "trk_2"]]


def test_clear_cascades_to_analysis():
    repo = SQLiteTrackRepository(db_path=":memory:")
    repo.insert_track(_track())
    repo.save_analyses([_analysis()])
    repo.clear()
    assert repo.conn.execute("SELECT COUNT(*) FROM track_analysis").fetchone()[0] == 0
