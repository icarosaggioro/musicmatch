"""Integration tests for AcousticAnalysisService, analysis persistence and acoustic duplicates (ADR 0014).

Real WAV files are written to tmp_path and analysed end-to-end (decoder -> DSP -> SQLite).
The service logic is exercised with the standard-library WAV decoder so results do not depend
on whether FFmpeg is installed; FFmpeg-specific behaviour (lossy formats) has its own tests.
"""

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

import numpy as np
import pytest

from audio_synth import synth_song, tag_file, write_wav
from musicmatch.domain.analysis import ANALYSIS_VERSION
from musicmatch.services.analysis import AcousticAnalysisService
from musicmatch.services.analyzer import AudioAnalyzer
from musicmatch.services.audio_decoder import AudioDecodeError, AudioDecoder
from musicmatch.services.library import LibraryService
from musicmatch.services.maintenance import LibraryMaintenanceService
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository

HAS_FFMPEG = shutil.which("ffmpeg") is not None
SONG_SECONDS = 20


@pytest.fixture
def repo():
    r = SQLiteTrackRepository(db_path=":memory:")
    yield r
    r.close()


@pytest.fixture
def library(repo):
    return LibraryService(repository=repo)


@pytest.fixture
def service(repo):
    return AcousticAnalysisService(repository=repo, analyzer=AudioAnalyzer(AudioDecoder(ffmpeg_path=None)))


def _song_file(path: Path, seed: int, title: str, artist: str = "Synth Band", bpm: float = 120.0, tonic: int = 0,
               mode: str = "major", gain: float = 1.0) -> Path:
    write_wav(path, np.asarray(synth_song(seconds=SONG_SECONDS, bpm=bpm, tonic=tonic, mode=mode, seed=seed)) * gain)
    return tag_file(path, title=title, artist=artist)


def _by_title(repo, title):
    return next(t for t in repo.get_all_tracks() if t.title == title)


def test_scan_stays_metadata_only_and_analysis_persists_real_metrics(tmp_path, repo, library, service):
    music = tmp_path / "music"
    _song_file(music / "a.wav", seed=1, title="Alpha", bpm=128.0, tonic=9, mode="minor")
    _song_file(music / "b.wav", seed=2, title="Beta", bpm=96.0, tonic=2, mode="major")

    scan = library.scan_and_ingest(str(music))
    assert scan.tracks_added == 2
    assert scan.tracks_pending_analysis == 2
    assert _by_title(repo, "Alpha").bpm == 120.0  # scan never decodes: tag/placeholder value only
    assert service.coverage().pending_tracks == 2

    result = service.analyze_library(workers=2)
    assert (result.status, result.analyzed_ok, result.failed, result.remaining_pending) == ("success", 2, 0, 0)

    alpha = _by_title(repo, "Alpha")
    analysis = service.get_analysis(alpha.id)
    f = analysis.features
    assert analysis.status == "OK" and analysis.analysis_version == ANALYSIS_VERSION
    assert (analysis.source_mtime, analysis.source_size) == (alpha.file_mtime, alpha.file_size)
    assert f.bpm == pytest.approx(128.0, abs=0.3)
    assert (f.musical_key, f.camelot_key) == ("A minor", "8A")
    assert -30.0 < f.integrated_lufs < -5.0 and f.loudness_range_lu is not None
    assert f.duration_seconds == pytest.approx(SONG_SECONDS, abs=0.1)
    assert f.fingerprint_frames > 150 and len(f.fingerprint) == 4 * f.fingerprint_frames
    assert 0 < len(f.waveform_peaks) <= 1000 and len(f.waveform_peaks) == len(f.waveform_rms)
    # Headline metrics are projected onto the catalog row used by /search, /list and the agent.
    assert alpha.bpm == f.bpm and alpha.lufs == f.integrated_lufs and alpha.musical_key == "A minor"
    beta = _by_title(repo, "Beta")
    assert beta.musical_key == "D major" and beta.bpm == pytest.approx(96.0, abs=0.3)
    assert library.search_tracks(min_bpm=125, max_bpm=130)[0].title == "Alpha"

    coverage = service.coverage()
    assert (coverage.available_tracks, coverage.analyzed_tracks, coverage.pending_tracks) == (2, 2, 0)


def test_reanalysis_is_incremental_and_follows_file_changes(tmp_path, repo, library, service):
    music = tmp_path / "music"
    path = _song_file(music / "a.wav", seed=3, title="Alpha")
    _song_file(music / "b.wav", seed=4, title="Beta")
    library.scan_and_ingest(str(music))
    assert service.analyze_library().analyzed_ok == 2

    again = service.analyze_library()
    assert again.total_candidates == 0 and again.message.startswith("Nenhuma")

    # Modified audio: the re-scan re-persists the track and drops the stale analysis.
    _song_file(path, seed=30, title="Alpha v2")
    stat = path.stat()
    os.utime(path, (stat.st_atime, stat.st_mtime + 10))
    library.scan_and_ingest(str(music))
    changed = _by_title(repo, "Alpha v2")
    assert service.get_analysis(changed.id) is None
    assert changed.musical_key is None and changed.lufs is None
    rerun = service.analyze_library()
    assert rerun.total_candidates == 1 and rerun.analyzed_ok == 1

    forced = service.analyze_library(force=True, limit=1)
    assert forced.total_candidates == 1 and forced.remaining_pending == 0


class _FaultyAnalyzer(AudioAnalyzer):
    """Real analyzer that fails for chosen file names (decoder error or unexpected bug)."""

    def __init__(self, decode_errors=(), crashes=()):
        super().__init__(AudioDecoder(ffmpeg_path=None))
        self.decode_errors, self.crashes = set(decode_errors), set(crashes)

    def analyze_file(self, file_path, cancel_event=None):
        name = Path(file_path).name
        if name in self.decode_errors:
            raise AudioDecodeError("Invalid data found when processing input")
        if name in self.crashes:
            raise ZeroDivisionError("boom")
        return super().analyze_file(file_path, cancel_event)


def test_unreadable_files_are_recorded_once_and_only_retried_with_force(tmp_path, repo, library):
    music = tmp_path / "music"
    _song_file(music / "good.wav", seed=5, title="Good")
    _song_file(music / "corrupt.wav", seed=15, title="Corrupt")
    _song_file(music / "trigger.wav", seed=16, title="Trigger")
    library.scan_and_ingest(str(music))
    service = AcousticAnalysisService(
        repository=repo, analyzer=_FaultyAnalyzer(decode_errors={"corrupt.wav"}, crashes={"trigger.wav"})
    )

    result = service.analyze_library()
    assert (result.analyzed_ok, result.failed, result.skipped) == (1, 2, 0)
    assert len(result.failures) == 2
    corrupt = service.get_analysis(_by_title(repo, "Corrupt").id)
    assert corrupt.status == "ERROR" and "Invalid data" in corrupt.error_message and corrupt.features is None
    crashed = service.get_analysis(_by_title(repo, "Trigger").id)
    assert crashed.status == "ERROR" and "ZeroDivisionError" in crashed.error_message  # batch kept going
    assert service.coverage().failed_tracks == 2
    assert _by_title(repo, "Corrupt").musical_key is None  # failures never touch catalog metrics

    assert service.analyze_library().total_candidates == 0  # not retried on every run
    assert service.analyze_library(force=True).failed == 2


def test_missing_and_unsupported_files_are_skipped_without_being_recorded(tmp_path, repo, library):
    music = tmp_path / "music"
    gone = _song_file(music / "gone.wav", seed=6, title="Gone")
    _song_file(music / "kept.wav", seed=7, title="Kept")
    m4a = music / "song.m4a"
    shutil.copy(music / "kept.wav", m4a)  # any bytes: without FFmpeg it must not even be opened
    library.scan_and_ingest(str(music))
    gone.unlink()  # e.g. a disconnected drive, not yet noticed by a re-scan

    no_ffmpeg = AcousticAnalysisService(repository=repo, analyzer=AudioAnalyzer(AudioDecoder(ffmpeg_path=None)))
    assert not no_ffmpeg.coverage().decoder_available
    result = no_ffmpeg.analyze_library()
    assert (result.analyzed_ok, result.failed, result.skipped) == (1, 0, 2)
    assert result.remaining_pending == 2  # retried later (drive back / FFmpeg installed)
    assert no_ffmpeg.get_analysis(_by_title(repo, "Gone").id) is None


def test_progress_events_are_typed_and_json_serializable(tmp_path, repo, library, service):
    music = tmp_path / "music"
    for i in range(3):
        _song_file(music / f"{i}.wav", seed=10 + i, title=f"Song {i}")
    library.scan_and_ingest(str(music))
    events = []
    result = service.analyze_library(workers=2, on_progress=events.append)
    assert [e.completed for e in events] == [1, 2, 3]
    assert all(e.total == 3 and e.outcome == "OK" for e in events)
    assert events[-1].percent == 100.0 and events[-1].eta_seconds == 0.0
    json.loads(events[0].model_dump_json())
    json.loads(result.model_dump_json())
    analysis = service.get_analysis(events[0].track_id)
    payload = json.loads(analysis.model_dump_json())
    assert "fingerprint" not in payload["features"]  # raw bytes never leak into JSON
    assert payload["features"]["waveform_peaks"]


def test_cancellation_keeps_finished_work_and_resumes(tmp_path, repo, library, service):
    music = tmp_path / "music"
    for i in range(4):
        _song_file(music / f"{i}.wav", seed=20 + i, title=f"Song {i}")
    library.scan_and_ingest(str(music))

    pre_cancelled = threading.Event()
    pre_cancelled.set()
    result = service.analyze_library(cancel_event=pre_cancelled)
    assert result.cancelled and result.status == "cancelled" and result.analyzed_ok == 0
    assert result.remaining_pending == 4

    cancel = threading.Event()
    partial = service.analyze_library(workers=1, cancel_event=cancel, on_progress=lambda e: cancel.set())
    assert partial.cancelled and partial.analyzed_ok >= 1
    assert partial.remaining_pending == 4 - partial.analyzed_ok

    def interrupt(event):
        raise KeyboardInterrupt  # Ctrl+C arriving in the caller's thread

    interrupted = service.analyze_library(workers=1, on_progress=interrupt)
    assert interrupted.cancelled
    finished = service.analyze_library()
    assert finished.remaining_pending == 0 and service.coverage().analyzed_tracks == 4


def test_relocation_and_unindex_keep_analysis_consistent(tmp_path, repo, library, service):
    old_dir, new_dir = tmp_path / "old", tmp_path / "new"
    path = _song_file(old_dir / "song.wav", seed=8, title="Traveller")
    library.scan_and_ingest(str(old_dir))
    service.analyze_library()
    original = _by_title(repo, "Traveller")
    fingerprint_hash = service.get_analysis(original.id).features.fingerprint_hash

    new_dir.mkdir()
    shutil.move(str(path), str(new_dir / "renamed.wav"))
    library.scan_and_ingest(str(old_dir))  # marks MISSING
    relocated_scan = library.scan_and_ingest(str(new_dir))  # Fast Relocation (ADR 0009)
    assert relocated_scan.tracks_updated == 1 and relocated_scan.tracks_pending_analysis == 0

    moved = _by_title(repo, "Traveller")
    assert moved.id != original.id and moved.status == "AVAILABLE"
    assert service.get_analysis(original.id) is None
    assert service.get_analysis(moved.id).features.fingerprint_hash == fingerprint_hash
    assert service.count_pending() == 0  # no DSP re-run needed

    repo.delete_track(moved.id)  # /unindex
    assert service.get_analysis(moved.id) is None


def test_reorganize_keeps_catalog_record_and_analysis(tmp_path, repo, library, service):
    root = tmp_path / "managed"
    _song_file(root / "loose.wav", seed=9, title="Loose", artist="Organizer")
    library.scan_and_ingest(str(root))
    service.analyze_library()
    before = _by_title(repo, "Loose")

    maintenance = LibraryMaintenanceService(repository=repo, analysis_service=service)
    result = maintenance.reorganize_library(managed_root=root)
    assert (result.realigned_count, result.errors) == (1, [])

    after = _by_title(repo, "Loose")
    assert after.file_path.endswith("Artists/Organizer/Album/Organizer - Loose.wav")
    assert Path(after.file_path).exists() and repo.count() == 1
    assert service.get_analysis(after.id).features.fingerprint_hash is not None
    assert service.count_pending() == 0


def test_exact_duplicates_ignore_tags_and_respect_duration(tmp_path, repo, library, service):
    music = tmp_path / "music"
    _song_file(music / "original.wav", seed=11, title="Original Title", artist="Band")
    copy = music / "other" / "copy.wav"
    copy.parent.mkdir(parents=True)
    shutil.copy(music / "original.wav", copy)
    tag_file(copy, title="Totally Different Tags", artist="Someone Else")
    _song_file(music / "unrelated.wav", seed=12, title="Unrelated")
    library.scan_and_ingest(str(music))
    service.analyze_library()

    clusters = service.find_exact_duplicates()
    assert len(clusters) == 1
    cluster = clusters[0]
    titles = {repo.get_track(tid).title for tid in cluster.track_ids}
    assert titles == {"Original Title", "Totally Different Tags"}
    assert cluster.match_type == "EXACT_FINGERPRINT" and cluster.similarity == 1.0

    maintenance = LibraryMaintenanceService(repository=repo, analysis_service=service)
    assert maintenance.find_duplicates(strategy="metadata") == []  # tags alone cannot see it
    default = maintenance.find_duplicates()  # fingerprint first
    assert [g.match_type for g in default] == ["EXACT_FINGERPRINT"]
    assert default[0].signature.startswith("fingerprint:")
    groups = maintenance.find_duplicates(strategy="exact")
    assert len(groups) == 1 and groups[0].match_type == "EXACT_FINGERPRINT"
    assert groups[0].recommended_track_id in cluster.track_ids

    report = maintenance.audit_library()
    assert report.analyzed_tracks == 3 and report.pending_analysis_tracks == 0
    assert report.acoustic_duplicate_groups_count == 1
    with pytest.raises(ValueError):
        maintenance.find_duplicates(strategy="nope")


def test_default_duplicates_trust_the_audio_over_the_tags(tmp_path, repo, library, service):
    """Same artist and title but different audio (e.g. live and studio) are not duplicates."""
    music = tmp_path / "music"
    _song_file(music / "studio.wav", seed=11, title="Same Title")
    _song_file(music / "live.wav", seed=12, title="Same Title", bpm=96.0, tonic=9, mode="minor")
    library.scan_and_ingest(str(music))
    maintenance = LibraryMaintenanceService(repository=repo, analysis_service=service)

    # Not analysed yet: the tags are the only evidence.
    assert [g.match_type for g in maintenance.find_duplicates()] == ["METADATA"]

    service.analyze_library()
    assert service.find_exact_duplicates() == []
    assert maintenance.find_duplicates() == []
    assert len(maintenance.find_duplicates(strategy="metadata")) == 1  # still available on request


def test_default_duplicates_fall_back_to_tags_only_for_tracks_without_fingerprint(tmp_path, repo, library, service):
    music = tmp_path / "music"
    _song_file(music / "analysed.wav", seed=11, title="Same Title")
    library.scan_and_ingest(str(music))
    service.analyze_library()
    _song_file(music / "new1.wav", seed=13, title="Same Title")
    _song_file(music / "new2.wav", seed=14, title="Same Title")
    library.scan_and_ingest(str(music))

    groups = LibraryMaintenanceService(repository=repo, analysis_service=service).find_duplicates()
    assert [g.match_type for g in groups] == ["METADATA"]
    assert {Path(t.file_path).name for t in groups[0].tracks} == {"new1.wav", "new2.wav"}


@pytest.mark.skipif(not HAS_FFMPEG, reason="FFmpeg not installed")
def test_fuzzy_duplicates_find_the_same_recording_across_encodes(tmp_path, repo, library):
    service = AcousticAnalysisService(repository=repo, analyzer=AudioAnalyzer(AudioDecoder()))
    music = tmp_path / "music"
    master = _song_file(music / "master.wav", seed=13, title="Master")
    for args, name in (
        (["-c:a", "libmp3lame", "-b:a", "96k"], "web.mp3"),
        (["-c:a", "aac", "-b:a", "64k", "-ar", "22050"], "phone.m4a"),
    ):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(master), *args, str(music / name)], check=True)
    _song_file(music / "other.wav", seed=14, title="Other Song")
    library.scan_and_ingest(str(music))
    assert service.analyze_library().analyzed_ok == 4

    assert service.find_exact_duplicates() == []  # lossy encodes never match bit-exactly
    clusters = service.find_fuzzy_duplicates()
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.match_type == "FUZZY_FINGERPRINT" and 0.6 < cluster.similarity < 1.0
    paths = {Path(repo.get_track(tid).file_path).name for tid in cluster.track_ids}
    assert paths == {"master.wav", "web.mp3", "phone.m4a"}

    groups = LibraryMaintenanceService(repository=repo, analysis_service=service).find_duplicates(strategy="fuzzy")
    keep = repo.get_track(groups[0].recommended_track_id)
    assert Path(keep.file_path).name == "master.wav"  # lossless master preferred over lossy copies
