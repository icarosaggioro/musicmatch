"""Tests for /analyze, acoustic options of /audit duplicates and their console rendering (ADR 0014)."""

import io
import sys
from unittest.mock import MagicMock, patch

import pytest

from musicmatch.commands.analyze import AnalyzeCommand
from musicmatch.commands.audit import AuditCommand
from musicmatch.commands.base import CommandContext
from musicmatch.commands.scan import ScanCommand
from musicmatch.domain.analysis import (
    AnalysisCoverage,
    AnalysisProgress,
    AnalysisRunResult,
    AudioFeatures,
    TrackAnalysis,
)
from musicmatch.domain.maintenance import DuplicateGroup, LibraryAuditReport
from musicmatch.domain.models import Track
from musicmatch.ui.renderer import ConsoleUI


def _track(track_id="trk_1", title="Song", bitrate=320, **extra):
    return Track(
        id=track_id, title=title, artist="Artist", album="Album", genre="Pop", duration_seconds=200.0,
        bitrate_kbps=bitrate, bpm=120.0, file_path=f"/music/{track_id}.mp3", **extra,
    )


def _features(**overrides):
    values = dict(
        duration_seconds=200.0, sample_rate=44100, channels=2, decoder="ffmpeg", integrated_lufs=-9.4,
        loudness_range_lu=6.1, sample_peak_dbfs=-0.3, bpm=124.0, bpm_confidence=0.62, musical_key="A minor",
        camelot_key="8A", key_confidence=0.81, tuning_cents=-3.0, fingerprint_algorithm="mmfp1",
        fingerprint_hash="ab" * 32, fingerprint_frames=1284, waveform_peaks=[0.1, 0.9, 0.5], waveform_rms=[0.05, 0.4, 0.2],
    )
    values.update(overrides)
    return AudioFeatures(**values)


def _run_result(**overrides):
    values = dict(message="ok", decoder="ffmpeg", workers=4, total_candidates=3, analyzed_ok=3, remaining_pending=0)
    values.update(overrides)
    return AnalysisRunResult(**values)


@pytest.fixture
def ctx():
    context = CommandContext(ui=MagicMock(), agent=MagicMock(), db=MagicMock(), registry=None)
    context.db.count.return_value = 3
    return context


@pytest.fixture
def analysis_service():
    svc = MagicMock()
    svc.coverage.return_value = AnalysisCoverage(
        available_tracks=3, analyzed_tracks=0, failed_tracks=0, pending_tracks=3, decoder="ffmpeg", decoder_available=True
    )
    svc.analyze_library.return_value = _run_result()
    with patch("musicmatch.services.analysis.acoustic_analysis_service", svc):
        yield svc


def test_analyze_runs_pending_tracks_with_progress(ctx, analysis_service):
    assert AnalyzeCommand().execute([], ctx) is True
    kwargs = analysis_service.analyze_library.call_args.kwargs
    assert kwargs["path_prefix"] is None and kwargs["force"] is False
    assert kwargs["limit"] is None and kwargs["workers"] is None
    assert kwargs["on_progress"] == ctx.ui.render_analysis_progress
    ctx.ui.render_analysis_summary.assert_called_once()


def test_analyze_parses_path_and_flags(ctx, analysis_service, tmp_path):
    AnalyzeCommand().execute([str(tmp_path), "--force", "--limit", "10", "--workers", "2"], ctx)
    kwargs = analysis_service.analyze_library.call_args.kwargs
    assert kwargs["path_prefix"] == str(tmp_path.resolve()).replace("\\", "/")
    assert (kwargs["force"], kwargs["limit"], kwargs["workers"]) == (True, 10, 2)


@pytest.mark.parametrize("bad_args", [["--limit"], ["--limit", "x"], ["--workers", "0"]])
def test_analyze_rejects_invalid_numbers(ctx, analysis_service, bad_args):
    AnalyzeCommand().execute(bad_args, ctx)
    ctx.ui.render_error.assert_called_once()
    analysis_service.analyze_library.assert_not_called()


def test_analyze_reports_nothing_to_do_and_missing_scan(ctx, analysis_service, tmp_path):
    analysis_service.analyze_library.return_value = _run_result(total_candidates=0, analyzed_ok=0)
    AnalyzeCommand().execute([], ctx)
    ctx.ui.render_success.assert_called_once()

    analysis_service.repo.get_tracks_under_path.return_value = []
    AnalyzeCommand().execute([str(tmp_path)], ctx)
    assert "/scan" in ctx.ui.render_warning.call_args.args[0]


def test_analyze_warns_without_ffmpeg_and_on_cancellation(ctx, analysis_service):
    analysis_service.coverage.return_value = AnalysisCoverage(
        available_tracks=3, analyzed_tracks=0, failed_tracks=0, pending_tracks=3, decoder="wave", decoder_available=False
    )
    analysis_service.analyze_library.return_value = _run_result(
        status="cancelled", cancelled=True, analyzed_ok=1, remaining_pending=2
    )
    AnalyzeCommand().execute([], ctx)
    warnings = " ".join(call.args[0] for call in ctx.ui.render_warning.call_args_list)
    assert "FFmpeg" in warnings and "2 faixa(s) pendente(s)" in warnings


def test_analyze_status_and_show(ctx, analysis_service):
    AnalyzeCommand().execute(["status"], ctx)
    ctx.ui.render_analysis_coverage.assert_called_once_with(analysis_service.coverage.return_value)

    AnalyzeCommand().execute(["show"], ctx)
    ctx.ui.render_error.assert_called_once()

    ctx.db.get_track.return_value = None
    AnalyzeCommand().execute(["show", "trk_x"], ctx)
    assert "não encontrada" in ctx.ui.render_error.call_args.args[0]

    ctx.db.get_track.return_value = _track()
    analysis_service.get_analysis.return_value = None
    AnalyzeCommand().execute(["show", "trk_1"], ctx)
    assert "ainda não foi analisada" in ctx.ui.render_warning.call_args.args[0]

    analysis = TrackAnalysis(track_id="trk_1", features=_features())
    analysis_service.get_analysis.return_value = analysis
    AnalyzeCommand().execute(["show", "trk_1"], ctx)
    ctx.ui.render_track_analysis.assert_called_once_with(ctx.db.get_track.return_value, analysis)


def test_audit_duplicates_strategies(ctx):
    group = DuplicateGroup(
        signature="acoustic:abcd", tracks=[_track("trk_a"), _track("trk_b", bitrate=128)],
        recommended_track_id="trk_a", recommendation_reason="best", match_type="FUZZY_FINGERPRINT", similarity=0.84,
    )
    with patch("musicmatch.commands.audit.library_maintenance_service") as maintenance:
        maintenance.repo.get_analysis_counts.return_value = {"available": 2, "analyzed": 0, "failed": 0, "pending": 2}
        AuditCommand().execute(["duplicates", "--fuzzy"], ctx)
        assert "análise acústica" in ctx.ui.render_warning.call_args.args[0]
        maintenance.find_duplicates.assert_not_called()

        maintenance.repo.get_analysis_counts.return_value = {"available": 3, "analyzed": 2, "failed": 0, "pending": 1}
        maintenance.find_duplicates.return_value = [group]
        AuditCommand().execute(["duplicates", "--fuzzy"], ctx)
        maintenance.find_duplicates.assert_called_with(strategy="fuzzy")
        ctx.ui.render_duplicate_groups.assert_called_with([group])

        AuditCommand().execute(["dups", "--exact"], ctx)
        maintenance.find_duplicates.assert_called_with(strategy="exact")

        maintenance.find_duplicates.return_value = []
        AuditCommand().execute(["duplicates", "--exact"], ctx)
        assert "--fuzzy" in ctx.ui.render_info.call_args.args[0]
        AuditCommand().execute(["duplicates", "--tags"], ctx)
        assert "--fuzzy" in ctx.ui.render_info.call_args.args[0]
        maintenance.find_duplicates.assert_called_with(strategy="metadata")
        AuditCommand().execute(["duplicates"], ctx)
        maintenance.find_duplicates.assert_called_with(strategy="auto")
        assert "por tags" in "".join(c.args[0] for c in ctx.ui.render_info.call_args_list)

        ctx.ui.reset_mock()  # not analysed yet: the default still works, by tags
        maintenance.repo.get_analysis_counts.return_value = {"available": 2, "analyzed": 0, "failed": 0, "pending": 2}
        maintenance.find_duplicates.return_value = [group]
        AuditCommand().execute(["duplicates"], ctx)
        maintenance.find_duplicates.assert_called_with(strategy="auto")
        ctx.ui.render_duplicate_groups.assert_called_once_with([group])
        assert "por tags" in ctx.ui.render_info.call_args_list[0].args[0]

        ctx.ui.reset_mock()
        AuditCommand().execute(["duplicates", "--bogus"], ctx)
        ctx.ui.render_error.assert_called_once()


def test_audit_dashboard_uses_renderer(ctx):
    report = LibraryAuditReport(total_tracks=1, available_tracks=1, missing_tracks=0, untagged_tracks=0,
                                low_bitrate_tracks=0, duplicate_groups_count=0)
    with patch("musicmatch.commands.audit.library_maintenance_service") as maintenance:
        maintenance.audit_library.return_value = report
        AuditCommand().execute([], ctx)
    ctx.ui.render_audit_report.assert_called_once_with(report)


def test_scan_suggests_analysis_when_tracks_are_pending(ctx, monkeypatch):
    result = {"status": "success", "total_files_scanned": 2, "tracks_indexed": 2, "tracks_added": 2,
              "duration_ms": 5.0, "tracks_pending_analysis": 2}
    monkeypatch.setattr("musicmatch.commands.scan.scan_library", lambda path: result)
    ScanCommand().execute(["/music"], ctx)
    assert "/analyze" in ctx.ui.render_info.call_args.args[0]


# ----------------------------------------------------------------------
# ConsoleUI rendering
# ----------------------------------------------------------------------


def _progress(completed, total=4, outcome="OK", message=None):
    return AnalysisProgress(completed=completed, total=total, track_id="trk_1", file_path="/m/a.mp3",
                            label="Artist - A very long title " * 3, outcome=outcome, message=message,
                            elapsed_seconds=1.0, eta_seconds=3.0)


def test_progress_rendering_in_terminal_and_in_logs(capsys, monkeypatch):
    ui = ConsoleUI()
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    ui.render_analysis_progress(_progress(1))
    ui.render_analysis_progress(_progress(2, outcome="ERROR", message="Invalid data"))
    ui.render_analysis_progress(_progress(4))
    out = capsys.readouterr().out
    assert "\r" in out and "[1/4]" in out and "Falha" in out and "Invalid data" in out and out.endswith("\n")

    monkeypatch.setattr(sys.stdout, "isatty", lambda: False, raising=False)
    for i in range(1, 41):
        ui.render_analysis_progress(_progress(i, total=40))
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 20 and "\r" not in "".join(lines) and "[40/40] 100%" in lines[-1]


def test_summary_coverage_and_track_detail_rendering(capsys):
    ui = ConsoleUI()
    ui.render_analysis_summary(_run_result(failed=1, failures=["/m/x.mp3: Invalid data"], duration_ms=65000))
    ui.render_analysis_coverage(AnalysisCoverage(available_tracks=3, analyzed_tracks=1, failed_tracks=0,
                                                 pending_tracks=2, decoder="wave", decoder_available=False))
    ui.render_track_analysis(_track(), TrackAnalysis(track_id="trk_1", features=_features(), analyzed_at="2026-01-01"))
    ui.render_track_analysis(_track(), TrackAnalysis(track_id="trk_1", status="ERROR", error_message="corrupt"))
    out = capsys.readouterr().out
    assert "01:05" in out and "Invalid data" in out
    assert "MUSICMATCH_FFMPEG_PATH" in out
    assert "-9.4 LUFS" in out and "124.0 BPM" in out and "A minor · Camelot 8A" in out and "mmfp1" in out
    assert "corrupt" in out


def test_duplicate_groups_and_audit_rendering(capsys):
    ui = ConsoleUI()
    group = DuplicateGroup(
        signature="acoustic:abcd", tracks=[_track("trk_a"), _track("trk_b", bitrate=128)],
        recommended_track_id="trk_a", recommendation_reason="Highest fidelity", match_type="FUZZY_FINGERPRINT",
        similarity=0.84,
    )
    ui.render_duplicate_groups([group])
    report = LibraryAuditReport(total_tracks=2, available_tracks=2, missing_tracks=0, untagged_tracks=0,
                                low_bitrate_tracks=0, duplicate_groups_count=0, analyzed_tracks=1,
                                pending_analysis_tracks=1, acoustic_duplicate_groups_count=1)
    ui.render_audit_report(report)
    out = capsys.readouterr().out
    assert "fingerprint acústico similar, similaridade 84%" in out and "PRESERVAR" in out
    assert "1 analisada(s), 1 pendente(s)" in out and "/analyze" in out


def test_search_results_show_acoustic_metrics(capsys):
    ConsoleUI().render_search_results([_track(musical_key="F# minor", lufs=-8.26), _track("trk_2")])
    out = capsys.readouterr().out
    assert "120 BPM · F# minor (11A) · -8.3 LUFS" in out
    assert "(120 BPM)" in out  # unanalysed tracks keep the previous format
