"""Diagnostics (ADR 0019): the developer log, the Issue register and its thread-safe reporter,
the issue sources, the /issue commands and the REPL error boundary."""

import logging
import os
import sqlite3
import sys
import threading
import time
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import musicmatch.diagnostics.logging_setup as logging_setup
from audio_synth import sine, write_wav
from musicmatch.commands.base import CommandContext
from musicmatch.commands.issue import ISSUE_COMMANDS
from musicmatch.commands.registry import CommandRegistry
from musicmatch.domain.issues import IssueKind, IssueReport
from musicmatch.domain.models import Track
from musicmatch.domain.player import PlayerEvent, PlayerState
from musicmatch.services.issues import IssueReporter, current_issue_reporter, report_issue, set_issue_reporter
from musicmatch.services.scanner import AudioScanner, name_problem
from musicmatch.storage.issue_store import SQLiteIssueStore
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository
from musicmatch.ui.renderer import ConsoleUI
from test_player_service import FakeOutput, kinds, player_factory, tones, wait_for  # noqa: F401


@pytest.fixture
def reporter():
    rep = IssueReporter(SQLiteIssueStore(":memory:"))
    previous = set_issue_reporter(rep)
    yield rep
    set_issue_reporter(previous)
    rep.close()
    rep.store.close()


@pytest.fixture
def isolated_logging(tmp_path):
    """configure_logging() changes process-wide state: restore it after the test."""
    root = logging.getLogger()
    saved = (list(root.handlers), root.level, logging.getLogger("musicmatch").level, sys.excepthook,
             threading.excepthook, logging_setup._handler, logging_setup._log_path)
    yield tmp_path / "logs"
    if logging_setup._handler is not None and logging_setup._handler not in saved[0]:
        root.removeHandler(logging_setup._handler)
        logging_setup._handler.close()
    root.handlers[:] = saved[0]
    root.setLevel(saved[1])
    logging.getLogger("musicmatch").setLevel(saved[2])
    sys.excepthook, threading.excepthook = saved[3], saved[4]
    logging_setup._handler, logging_setup._log_path = saved[5], saved[6]
    logging.captureWarnings(False)


def open_issues(rep, status="OPEN"):
    rep.flush()
    return {(i.kind, i.subject_key): i for i in rep.store.list(status=status, limit=500)}


# ----------------------------------------------------------------------
# Developer log
# ----------------------------------------------------------------------


def test_developer_log_captures_tracebacks_warnings_and_uncaught_thread_errors(isolated_logging):
    path = logging_setup.configure_logging(isolated_logging, level="INFO")
    assert path == isolated_logging / "musicmatch.log" and logging_setup.log_path() == path

    try:
        1 / 0
    except ZeroDivisionError as exc:
        ref = logging_setup.log_unexpected("Something broke", exc)
    warnings.warn("deprecated thing", DeprecationWarning, stacklevel=1)

    def crash():
        raise RuntimeError("boom in a background thread")

    worker = threading.Thread(target=crash, name="musicmatch-test-worker")
    worker.start()
    worker.join()
    logging.getLogger("google_genai").info("chatty third-party info")  # limited to WARNING
    for handler in logging.getLogger().handlers:
        handler.flush()

    text = path.read_text(encoding="utf-8")
    assert f"Something broke [ref {ref}]" in text and "ZeroDivisionError: division by zero" in text
    assert "Traceback (most recent call last)" in text
    assert "deprecated thing" in text
    assert "Uncaught exception in thread musicmatch-test-worker" in text and "boom in a background thread" in text
    assert "[musicmatch-test-worker] musicmatch" in text  # the thread that failed is named in the log line
    assert "chatty third-party info" not in text
    assert len(ref) == 6


def test_only_a_damaged_database_or_exhausted_memory_is_fatal():
    assert logging_setup.is_fatal(sqlite3.DatabaseError("database disk image is malformed"))
    assert logging_setup.is_fatal(sqlite3.OperationalError("file is not a database"))
    assert logging_setup.is_fatal(MemoryError())
    for contained in (sqlite3.OperationalError("database is locked"), sqlite3.IntegrityError("UNIQUE"),
                      RuntimeError("bug"), OSError("disk"), KeyError("x")):
        assert not logging_setup.is_fatal(contained)


# ----------------------------------------------------------------------
# Issue register: identity, dismiss vs delete, retention
# ----------------------------------------------------------------------


def test_one_issue_per_kind_and_subject_counts_recurrences(reporter):
    for _ in range(3):
        report_issue(IssueKind.TAGS_UNREADABLE, "/m/a.mp3", "corrompido", subject_type="file", source="scan")
    report_issue(IssueKind.FILE_EMPTY, "/m/a.mp3", "vazio", subject_type="file")  # same file, other kind
    issues = open_issues(reporter)
    assert len(issues) == 2 and reporter.take_new_count() == 2 and reporter.take_new_count() == 0
    tags = issues[(IssueKind.TAGS_UNREADABLE, "/m/a.mp3")]
    assert (tags.occurrences, tags.category, tags.severity, tags.source) == (3, "RESOURCE", "ERROR", "scan")


def test_dismissed_issues_stay_silent_and_deleted_ones_come_back(reporter):
    report_issue(IssueKind.PLAYLIST_EMPTY, "playlist:1", "vazia", subject_type="playlist", subject_label="Mix")
    issue = next(iter(open_issues(reporter).values()))
    reporter.take_new_count()

    assert reporter.store.dismiss([issue.id]) == 1
    report_issue(IssueKind.PLAYLIST_EMPTY, "playlist:1", "vazia de novo", subject_type="playlist")
    dismissed = open_issues(reporter, "DISMISSED")[(IssueKind.PLAYLIST_EMPTY, "playlist:1")]
    assert dismissed.occurrences == 2 and dismissed.message == "vazia de novo" and dismissed.dismissed_at
    assert reporter.take_new_count() == 0 and reporter.store.count("OPEN") == 0  # not raised again

    assert reporter.store.delete([issue.id]) == 1
    report_issue(IssueKind.PLAYLIST_EMPTY, "playlist:1", "vazia", subject_type="playlist")
    reborn = open_issues(reporter)[(IssueKind.PLAYLIST_EMPTY, "playlist:1")]
    assert reborn.id != issue.id and reborn.occurrences == 1 and reporter.take_new_count() == 1


def test_startup_retention_never_purges_open_issues(reporter):
    store = reporter.store
    for i in range(4):
        report_issue(IssueKind.FILE_EMPTY, f"/m/{i}.mp3", "vazio", subject_type="file")
    reporter.flush()
    ids = [i.id for i in store.list(limit=10)]
    store.dismiss(ids[:3])
    with store._lock, store._conn:  # two dismissed issues were last seen long ago
        store._conn.execute("UPDATE issues SET last_seen = datetime('now', '-400 days') WHERE id IN (?, ?);",
                            (ids[0], ids[3]))
    assert store.purge(retention_days=180) == 1  # the old dismissed one; the old OPEN one stays
    assert store.count("OPEN") == 1 and store.count("DISMISSED") == 2
    assert store.purge(retention_days=180, max_dismissed=1) == 1  # cap: least recently seen go first
    assert store.count("DISMISSED") == 1 and store.count("OPEN") == 1


# ----------------------------------------------------------------------
# The reporter is the thread-safe front door
# ----------------------------------------------------------------------


def test_reports_from_many_threads_are_all_persisted(reporter):
    def burst():
        for i in range(200):
            report_issue(IssueKind.TAGS_UNREADABLE, f"/m/{i % 50}.mp3", "x", subject_type="file")

    threads = [threading.Thread(target=burst) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    issues = open_issues(reporter)
    assert len(issues) == 50 and {i.occurrences for i in issues.values()} == {24}
    assert reporter.take_new_count() == 50


def test_reporting_never_blocks_while_the_database_is_busy(reporter):
    store = reporter.store
    with store._lock:  # e.g. a long write by another operation
        started = time.perf_counter()
        report_issue(IssueKind.FILE_EMPTY, "/m/a.mp3", "vazio", subject_type="file")
        elapsed = time.perf_counter() - started
        assert reporter.flush(timeout=0.2) is False  # still queued: the writer is the one waiting
    assert elapsed < 0.05
    assert reporter.flush(timeout=5) and store.count() == 1


def test_a_failing_store_never_breaks_the_caller_nor_kills_the_writer(reporter, caplog):
    real_record = reporter.store.record
    calls = {"n": 0}

    def flaky(batch):
        calls["n"] += 1
        if calls["n"] == 1:
            raise sqlite3.OperationalError("disk I/O error")
        return real_record(batch)

    with patch.object(reporter.store, "record", side_effect=flaky):
        report_issue(IssueKind.FILE_EMPTY, "/m/lost.mp3", "vazio", subject_type="file")
        reporter.flush()
        report_issue(IssueKind.FILE_EMPTY, "/m/kept.mp3", "vazio", subject_type="file")
        reporter.flush()
    assert [i.subject_key for i in reporter.store.list()] == ["/m/kept.mp3"]
    assert any("Could not persist 1 issue report(s)" in r.getMessage() for r in caplog.records)


def test_without_a_reporter_reporting_is_a_no_op():
    previous = set_issue_reporter(None)
    try:
        report_issue(IssueKind.FILE_EMPTY, "/m/a.mp3", "vazio", subject_type="file")  # no error, no database
        assert current_issue_reporter() is None
    finally:
        set_issue_reporter(previous)


def test_closing_persists_what_is_still_queued():
    rep = IssueReporter(SQLiteIssueStore(":memory:"))
    for i in range(100):
        rep.report(IssueReport(kind=IssueKind.FILE_EMPTY, subject_type="file", subject_key=f"/m/{i}", message="x"))
    rep.close()
    assert rep.store.count() == 100
    rep.store.close()


# ----------------------------------------------------------------------
# Sources
# ----------------------------------------------------------------------


def test_scanner_turns_bad_files_and_names_into_issues(tmp_path, reporter):
    lib = tmp_path / "lib"
    write_wav(lib / "fine.wav", sine(440, 0.3, -6.0))
    write_wav(lib / "CON" / "what?.wav", sine(440, 0.3, -6.0))  # indexed, but not portable
    (lib / "empty.wav").write_bytes(b"")
    (lib / "corrupt.mp3").write_bytes(b"not audio" * 200)
    write_wav(lib / "silence.wav", sine(440, 0.0, -6.0))  # valid file, no audio frames
    deep = lib / ("d" * 120) / ("e" * 120)
    write_wav(deep / "long.wav", sine(440, 0.3, -6.0))
    undecodable_name = None
    if sys.platform.startswith("linux"):
        undecodable_name = os.fsencode(str(lib)) + b"/bad\xff.wav"
        with open(undecodable_name, "wb") as handle:
            handle.write((lib / "fine.wav").read_bytes())

    repo = SQLiteTrackRepository(":memory:")
    result = AudioScanner(repo).scan_directory(str(lib))
    issues = open_issues(reporter)
    by_kind = {}
    for (kind, key), issue in issues.items():
        by_kind.setdefault(kind, []).append(key.replace(str(lib), ""))

    assert by_kind[IssueKind.FILE_EMPTY] == ["/empty.wav"]
    assert by_kind[IssueKind.TAGS_UNREADABLE] == ["/corrupt.mp3"]
    assert by_kind[IssueKind.AUDIO_EMPTY] == ["/silence.wav"]
    assert sorted(by_kind[IssueKind.NAME_NOT_PORTABLE]) == sorted(
        ["/CON", "/CON/what?.wav"] + (["/bad\\xff.wav"] if undecodable_name else []))
    assert [k.endswith("long.wav") for k in by_kind[IssueKind.PATH_TOO_LONG]] == [True]
    indexed = {Path(t.file_path).name for t in repo.get_all_tracks()}
    assert indexed == {"fine.wav", "what?.wav", "silence.wav", "long.wav"}  # bad bytes / empty / corrupt stay out
    assert result.errors_count == 2 + (1 if undecodable_name else 0)
    assert all(i.source == "scan" and "sugestão" in i.details for i in issues.values())

    AudioScanner(repo).scan_directory(str(lib))  # a rescan refreshes, never duplicates
    again = open_issues(reporter)
    assert again.keys() == issues.keys()
    assert again[(IssueKind.TAGS_UNREADABLE, str(lib / "corrupt.mp3"))].occurrences == 2
    repo.close()


def test_name_rules():
    assert name_problem("Björk - Jóga.flac") is None
    assert "Windows" in name_problem("AC:DC.mp3") and "reservado" in name_problem("nul.wav")
    assert "termina" in name_problem("Album. ") and "UTF-8" in name_problem("bad\udcff.wav")


def test_scanner_bugs_go_to_the_developer_log_not_to_issues(tmp_path, reporter, caplog):
    write_wav(tmp_path / "a.wav", sine(440, 0.3, -6.0))
    with patch("musicmatch.services.scanner.mediafile.MediaFile", side_effect=RuntimeError("parser bug")):
        result = AudioScanner(SQLiteTrackRepository(":memory:")).scan_directory(str(tmp_path))
    assert result.errors_count == 1 and open_issues(reporter) == {}
    record = next(r for r in caplog.records if "Unexpected error scanning" in r.getMessage())
    assert record.exc_info[0] is RuntimeError


def test_playback_problems_become_issues_from_any_thread(tones, player_factory, reporter, tmp_path, caplog):
    player, events = player_factory()
    ok, gone = tones("ok", 440.0, 0.3), tones("gone", 550.0)
    player.queue_add_last(ok)
    player.queue_add_last(gone)
    Path(gone.file_path).unlink()  # disappears after being queued: found missing on the auto-advance thread
    player.add_listener(MagicMock(side_effect=ValueError("broken view")))
    player.play_queue()
    assert wait_for(lambda: "QUEUE_ENDED" in kinds(events))
    missing = open_issues(reporter)[(IssueKind.TRACK_FILE_MISSING, "trk_gone")]
    assert missing.subject_label == "Tester - gone" and missing.details["arquivo"] == gone.file_path
    assert any("Player listener failed" in r.getMessage() for r in caplog.records)  # logged, playback went on

    broken, _ = player_factory(FakeOutput(fail=True))
    broken.play_track(tones("x", 440.0))
    device = open_issues(reporter)[(IssueKind.AUDIO_DEVICE_UNAVAILABLE, "audio-output")]
    assert device.category == "ENVIRONMENT" and device.subject_type == "device"


def test_analysis_failures_become_issues_and_crashes_are_logged(tmp_path, reporter, caplog):
    from musicmatch.services.analysis import AcousticAnalysisService
    from musicmatch.services.library import LibraryService
    from test_acoustic_analysis_service import _FaultyAnalyzer, _song_file

    repo = SQLiteTrackRepository(":memory:")
    _song_file(tmp_path / "corrupt.wav", seed=15, title="Corrupt")
    _song_file(tmp_path / "trigger.wav", seed=16, title="Trigger")
    LibraryService(repository=repo).scan_and_ingest(str(tmp_path))
    service = AcousticAnalysisService(repository=repo, analyzer=_FaultyAnalyzer(
        decode_errors={"corrupt.wav"}, crashes={"trigger.wav"}))
    service.analyze_library()
    undecodable = [i for (kind, _), i in open_issues(reporter).items() if kind == IssueKind.AUDIO_UNDECODABLE]
    assert sorted(i.subject_label.split(" - ")[1] for i in undecodable) == ["Corrupt", "Trigger"]
    crash = next(r for r in caplog.records if "Unexpected analysis failure" in r.getMessage())
    assert crash.exc_info[0] is ZeroDivisionError and crash.threadName.startswith("musicmatch-analysis")
    repo.close()


def test_playlist_problems_become_issues(tmp_path, reporter):
    from musicmatch.services.playlists import PlaylistService

    repo = SQLiteTrackRepository(":memory:")
    path = write_wav(tmp_path / "a.wav", sine(440, 0.3, -6.0))
    track = Track(id=Track.generate_id(str(path)), title="a", artist="b", album="c", genre="d",
                  duration_seconds=0.3, bitrate_kbps=1411, bpm=120, file_path=str(path))
    repo.insert_track(track)
    service = PlaylistService(repo)
    m3u = tmp_path / "mix.m3u8"
    m3u.write_text(f"{path}\n/nowhere/x.mp3\nhttp://radio/y\n", encoding="utf-8")
    service.import_m3u(m3u, "Mix")
    incomplete = open_issues(reporter)[(IssueKind.PLAYLIST_IMPORT_INCOMPLETE, str(m3u))]
    assert "2 de 3 entrada(s) não resolvida(s); playlist 'Mix' criada com 1" in incomplete.message
    assert incomplete.details["URLs ignoradas"] == ["http://radio/y"] and len(incomplete.details["não encontrados"]) == 1

    empty = service.save("Mix", [], existing=service.find_exact("Mix"))
    assert service.report_empty_playlists() == 1
    issue = open_issues(reporter)[(IssueKind.PLAYLIST_EMPTY, f"playlist:{empty.id}")]
    assert issue.subject_label == "Mix" and "/playlist-delete Mix" in issue.details["sugestão"]
    repo.close()


def test_recycle_bin_failures_become_issues(tmp_path, reporter):
    from musicmatch.services.maintenance import LibraryMaintenanceService

    repo = SQLiteTrackRepository(":memory:")
    path = write_wav(tmp_path / "locked.wav", sine(440, 0.3, -6.0))
    repo.insert_track(Track(id="trk_locked", title="Locked", artist="Band", album="c", genre="d", duration_seconds=0.3,
                            bitrate_kbps=1411, bpm=120, file_path=str(path)))
    with patch("musicmatch.services.maintenance.send2trash.send2trash", side_effect=OSError("file in use")):
        deleted, errors = LibraryMaintenanceService(repository=repo).delete_tracks_to_trash(["trk_locked"])
    assert deleted == 0 and errors
    issue = open_issues(reporter)[(IssueKind.TRASH_FAILED, "trk_locked")]
    assert "file in use" in issue.message and issue.subject_label == "Band - Locked"
    repo.close()


# ----------------------------------------------------------------------
# /issue commands
# ----------------------------------------------------------------------


@pytest.fixture
def run(reporter):
    registry = CommandRegistry()
    ui = MagicMock()
    ctx = CommandContext(ui=ui, agent=MagicMock(), db=MagicMock(db_path=":memory:"), registry=registry)

    def dispatch(line, *answers):
        replies = iter(answers)
        with patch("builtins.input", side_effect=lambda _prompt="": next(replies)):
            registry.dispatch(line, ctx)
        return ui

    return dispatch


def seed(reporter, count=3):
    for i in range(count):
        report_issue(IssueKind.TAGS_UNREADABLE, f"/m/{i}.mp3", f"corrompido {i}", subject_type="file")
    reporter.flush()
    return sorted(i.id for i in reporter.store.list(limit=50))


def texts(method):
    return " | ".join(str(c.args[0]) for c in method.call_args_list)


def test_issue_commands_follow_the_issue_dash_naming_rule():
    names = {cls().get_name() for cls in ISSUE_COMMANDS}
    assert names == {"/issue", "/issue-dismiss", "/issue-delete"}
    assert all(cls().get_aliases() == [] for cls in ISSUE_COMMANDS)


def test_listing_and_showing_issues(run, reporter):
    first, second, third = seed(reporter)
    ui = run("/issue")
    listed, counts, total = ui.render_issues.call_args.args
    assert [i.id for i in listed] == [third, second, first] and total == 3
    assert counts == {IssueKind.TAGS_UNREADABLE: 3} and ui.render_issues.call_args.kwargs["status"] == "OPEN"
    run(f"/issue #{second}")
    assert ui.render_issue.call_args.args[0].message == "corrompido 1"
    run("/issue 999")
    assert "Problema #999 não encontrado" in texts(ui.render_error)
    run("/issue abc")
    assert "'abc' não é o número de um problema" in texts(ui.render_error)
    run("/issue --bogus")
    assert "Opção desconhecida: --bogus" in texts(ui.render_error)


def test_dismiss_and_delete_commands(run, reporter):
    first, second, third = seed(reporter)
    ui = run(f"/issue-dismiss {first} #{second} 999")
    assert "2 problema(s) dispensado(s)" in texts(ui.render_success) and "#999" in texts(ui.render_error)
    run(f"/issue-dismiss {first}")
    assert f"Já estavam dispensados: #{first}" in texts(ui.render_info)
    run("/issue --dismissed")
    assert [i.id for i in ui.render_issues.call_args.args[0]] == [second, first]

    run("/issue-delete --dismissed", "n")
    assert reporter.store.count("DISMISSED") == 2
    run("/issue-delete --dismissed", "s")
    assert reporter.store.count("DISMISSED") == 0 and reporter.store.count("OPEN") == 1
    run(f"/issue-delete {third}")
    assert reporter.store.count(None) == 0
    run("/issue-delete --all")
    assert "Nenhum problema a apagar" in texts(ui.render_info)
    seed(reporter, 2)
    run("/issue-dismiss --all")
    assert reporter.store.count("DISMISSED") == 2
    run("/issue-delete --all", "s")
    assert reporter.store.count(None) == 0
    run("/issue-delete 1 --all")
    assert "não ambos" in texts(ui.render_error)
    run("/issue-dismiss")
    assert "Uso: /issue-dismiss" in texts(ui.render_error)


# ----------------------------------------------------------------------
# REPL: error boundary, fatal exit, summaries, startup
# ----------------------------------------------------------------------


def make_harness(db=None, ui=None):
    from musicmatch.harness.loop import Harness

    agent = MagicMock()
    agent.model_name = "test"
    return Harness(agent=agent, ui=ui or MagicMock(), registry=CommandRegistry(), database=db or MagicMock())


def drive(harness, *lines):
    with patch("builtins.input", side_effect=list(lines) + [EOFError()]):
        harness.start()


def test_a_fatal_error_exits_gracefully_and_saves_the_playback_state(monkeypatch):
    import musicmatch.services.player as player_module

    shutdown = MagicMock()
    monkeypatch.setattr(player_module, "shutdown_player_service", shutdown)
    harness = make_harness()
    harness.registry.dispatch = MagicMock(side_effect=sqlite3.DatabaseError("database disk image is malformed"))
    drive(harness, "/list", "/status")
    assert harness.exit_code == 1 and harness.registry.dispatch.call_count == 1  # stopped at once
    harness.ui.render_fatal_error.assert_called_once()
    shutdown.assert_called_once()


def test_each_command_ends_with_one_summary_line_for_new_issues(reporter):
    harness = make_harness()

    def noisy_command(raw, ctx):
        for i in range(40):
            report_issue(IssueKind.FILE_EMPTY, f"/m/{i}.mp3", "vazio", subject_type="file")
        if raw == "/boom":
            raise RuntimeError("bug after reporting")
        return True

    harness.registry.dispatch = noisy_command
    drive(harness, "/scan x", "/scan x", "/boom")
    counts = [c.args[0] for c in harness.ui.render_issue_notice.call_args_list]
    assert counts == [40, 0, 0]  # one line with 40; a rescan opens nothing new; failing commands still summarise
    harness.ui.render_unexpected_error.assert_called_once()


def test_startup_purges_checks_playlists_and_shows_the_open_count(tmp_path, reporter):
    from musicmatch.services.playlists import PlaylistService

    repo = SQLiteTrackRepository(":memory:")
    PlaylistService(repo).save("Ghost", [])
    report_issue(IssueKind.FILE_EMPTY, "/m/a.mp3", "vazio", subject_type="file")
    harness = make_harness(db=repo)
    drive(harness)
    harness.ui.render_open_issues.assert_called_once_with(2)
    assert reporter.take_new_count() == 0  # startup findings are in the startup line, not "new" later
    repo.close()


def test_the_entry_point_wires_diagnostics_and_propagates_the_exit_code(tmp_path):
    from musicmatch import cli

    harness = MagicMock()
    harness.db.db_path = str(tmp_path / "musicmatch.db")
    harness.exit_code = 1
    with patch.object(cli, "configure_logging", return_value=tmp_path / "log"), \
            patch.object(cli, "Harness", return_value=harness), \
            patch.object(cli, "configure_issue_reporter") as configure, \
            patch.object(cli, "shutdown_issue_reporter") as shutdown:
        with pytest.raises(SystemExit) as exited:
            cli.main()
    assert exited.value.code == 1
    configure.assert_called_once_with(str(tmp_path / "musicmatch.db"))
    shutdown.assert_called_once()


# ----------------------------------------------------------------------
# Console output from several threads
# ----------------------------------------------------------------------


def test_background_output_never_interleaves_with_a_foreground_block(monkeypatch):
    ui = ConsoleUI()
    lines, inside, release = [], threading.Event(), threading.Event()

    def fake_print(*args, **kwargs):
        lines.append(" ".join(str(a) for a in args))
        if threading.current_thread() is threading.main_thread() and not inside.is_set():
            inside.set()
            release.wait(2)  # the foreground block is half printed

    monkeypatch.setattr("builtins.print", fake_print)
    track = Track(id="trk_1", title="Song", artist="Band", album="A", genre="G", duration_seconds=60,
                  bitrate_kbps=320, bpm=120, file_path="/m/1.mp3")
    background = threading.Thread(target=ui.render_player_event, args=(
        PlayerEvent(kind="TRACK_STARTED", state=PlayerState.PLAYING, track=track, background=True),))

    def start_background_then_release():
        inside.wait(2)
        background.start()
        time.sleep(0.1)  # give it every chance to print in the middle
        release.set()

    helper = threading.Thread(target=start_background_then_release)
    helper.start()
    ui.render_issues([], {}, 0)
    helper.join()
    background.join()
    block_end = max(i for i, line in enumerate(lines) if line.startswith("="))
    playing = next(i for i, line in enumerate(lines) if "Tocando agora" in line)
    assert playing > block_end


def test_issue_rendering(capsys):
    from musicmatch.domain.issues import Issue

    ui = ConsoleUI()
    issue = Issue(id=7, kind=IssueKind.PLAYLIST_IMPORT_INCOMPLETE, category="RESOURCE", severity="WARNING",
                  subject_type="playlist_file", subject_key="/x/mix.m3u8", subject_label="mix.m3u8 → 'Mix'",
                  message="2 de 3 entrada(s) não resolvida(s)", details={"não encontrados": [f"/n/{i}" for i in range(12)]},
                  source="playlist", occurrences=2, first_seen="2026-01-01 10:00:00", last_seen="2026-01-02 10:00:00")
    ui.render_issues([issue], {IssueKind.PLAYLIST_IMPORT_INCOMPLETE: 1}, 1, other_count=4)
    out = capsys.readouterr().out
    assert "PROBLEMAS EM ABERTO (1)" in out and "dispensados: 4" in out and "#7" in out
    assert "1× Importação de playlist incompleta" in out and "mix.m3u8 → 'Mix' · 2x" in out
    ui.render_issue(issue)
    out = capsys.readouterr().out
    assert "Problema #7" in out and "Referência:   /x/mix.m3u8" in out and "não encontrados: (12)" in out
    assert "… e mais 2." in out and "/issue-dismiss 7" in out
    ui.render_issue_notice(3)
    ui.render_issue_notice(1, background=True)
    ui.render_issue_notice(0)
    out = capsys.readouterr().out
    assert "🩺  3 novos problemas registrados — veja /issue" in out and "1 novo problema registrado" in out
    ui.render_unexpected_error("/scan", "a1b2c3", "/logs/musicmatch.log", reason="RuntimeError: " + "x" * 300)
    out = capsys.readouterr().out
    assert "Erro inesperado ao executar '/scan' (RuntimeError: " in out and "…)" in out
    assert "(ref. a1b2c3)" in out and "/logs/musicmatch.log" in out
    ui.render_open_issues(0)
    ui.render_open_issues(5)
    assert capsys.readouterr().out == "🩺 Problemas em aberto: 5 · /issue para revisar\n\n"
