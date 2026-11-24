"""AcousticAnalysisService: batch analysis, analysis stat-cache and acoustic duplicates (ADR 0014).

Responsibilities:
- Select the tracks that need analysis with one SQL query (never analysed, file modified
  since, analysis version outdated) -> re-runs over an analysed library are instant.
- Run AudioAnalyzer on a worker pool (each worker drives its own FFmpeg process), persist
  results in small transactions as they complete, so a cancelled/interrupted run keeps
  everything finished so far and the next run resumes where it stopped.
- Emit one typed AnalysisProgress event per track through a callback and honour a
  cooperative cancellation Event: the same API serves the CLI today and a GUI worker
  thread later (the GUI only needs to marshal the callback onto its UI thread).
- Detect acoustic duplicates: exact (identical fingerprint hash, one indexed GROUP BY)
  and fuzzy (bit-error-rate matching that survives re-encoding and bitrate changes).

Threading contract: the repository (SQLite connection) is only used by the thread that
calls the service methods; worker threads run pure decoding/DSP and never touch it.
"""

import logging
import os
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Callable, Dict, Iterator, List, Optional, Tuple

from musicmatch.config import settings
from musicmatch.domain.analysis import (
    ANALYSIS_VERSION,
    AcousticDuplicateCluster,
    AnalysisCoverage,
    AnalysisOutcome,
    AnalysisProgress,
    AnalysisRunResult,
    AudioFeatures,
    TrackAnalysis,
)
from musicmatch.domain.issues import IssueKind
from musicmatch.domain.models import Track
from musicmatch.dsp.fingerprint import (
    DEFAULT_MATCH_BER,
    FINGERPRINT_ALGORITHM,
    MIN_OVERLAP_FRAMES,
    find_similar_pairs,
    fingerprint_from_bytes,
    group_matches,
)
from musicmatch.services.analyzer import AudioAnalyzer
from musicmatch.services.audio_decoder import AudioDecodeError, DecodeCancelled, DecoderUnavailableError
from musicmatch.services.issues import report_issue
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[AnalysisProgress], None]
_PERSIST_BATCH = 20
_MAX_FAILURE_SAMPLES = 10
# Duplicate candidates must have compatible decoded durations (same recording, maybe with
# a little extra/less silence): |d1 - d2| <= max(5 s, 3%).
DURATION_TOLERANCE_SECONDS = 5.0
DURATION_TOLERANCE_RATIO = 0.03


def default_worker_count() -> int:
    configured = settings.ANALYSIS_WORKERS
    if configured and configured > 0:
        return configured
    return max(1, min(4, os.cpu_count() or 1))


def _label(track: Track) -> str:
    return f"{track.artist} - {track.title}"


def _durations_compatible(a: float, b: float) -> bool:
    return abs(a - b) <= max(DURATION_TOLERANCE_SECONDS, DURATION_TOLERANCE_RATIO * max(a, b))


class AcousticAnalysisService:
    """Use-case layer for acoustic analysis, shared by /analyze, /audit and future GUI views."""

    def __init__(
        self,
        repository: Optional[SQLiteTrackRepository] = None,
        analyzer: Optional[AudioAnalyzer] = None,
    ) -> None:
        self._repo = repository
        self.analyzer = analyzer or AudioAnalyzer()

    @property
    def repo(self) -> SQLiteTrackRepository:
        """Opened on first use, not at import (see LibraryMaintenanceService.repo)."""
        if self._repo is None:
            self._repo = SQLiteTrackRepository()
        return self._repo

    @repo.setter
    def repo(self, value: SQLiteTrackRepository) -> None:
        self._repo = value

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def coverage(self) -> AnalysisCoverage:
        counts = self.repo.get_analysis_counts()
        decoder = self.analyzer.decoder
        return AnalysisCoverage(
            available_tracks=counts["available"],
            analyzed_tracks=counts["analyzed"],
            failed_tracks=counts["failed"],
            pending_tracks=counts["pending"],
            decoder=decoder.backend_name,
            decoder_available=bool(decoder.ffmpeg_path),
            supported_formats=sorted(ext.lstrip(".").upper() for ext in (decoder.supported_extensions() or ())),
        )

    def count_pending(self, path_prefix: Optional[str] = None) -> int:
        return self.repo.count_pending_analysis(path_prefix)

    def get_analysis(self, track_id: str) -> Optional[TrackAnalysis]:
        return self.repo.get_analysis(track_id)

    # ------------------------------------------------------------------
    # Batch analysis
    # ------------------------------------------------------------------

    def analyze_library(
        self,
        path_prefix: Optional[str] = None,
        track_ids: Optional[List[str]] = None,
        force: bool = False,
        limit: Optional[int] = None,
        workers: Optional[int] = None,
        on_progress: Optional[ProgressCallback] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> AnalysisRunResult:
        """Analyses pending tracks (or all selected tracks when force=True).

        KeyboardInterrupt during the run is treated as a cancellation request: running
        decoders are stopped, finished results are persisted and a 'cancelled' result is
        returned instead of unwinding the caller's event loop.
        """
        started = time.perf_counter()
        cancel = cancel_event or threading.Event()
        worker_count = max(1, workers or default_worker_count())
        decoder_name = self.analyzer.decoder.backend_name

        tracks = self.repo.get_tracks_pending_analysis(
            path_prefix=path_prefix, force=force, limit=limit, track_ids=track_ids
        )
        total = len(tracks)
        counters: Dict[str, int] = {"OK": 0, "ERROR": 0, "SKIPPED": 0}
        failures: List[str] = []
        buffer: List[TrackAnalysis] = []
        completed = 0

        def record(track: Track, outcome: AnalysisOutcome, message: Optional[str]) -> None:
            nonlocal completed
            completed += 1
            if outcome in counters:
                counters[outcome] += 1
            if outcome == "ERROR" and len(failures) < _MAX_FAILURE_SAMPLES:
                failures.append(f"{track.file_path}: {message}")
            if outcome == "ERROR":
                report_issue(IssueKind.AUDIO_UNDECODABLE, track.id, message or "Falha na análise acústica.",
                             subject_type="track", subject_label=f"{track.artist} - {track.title}",
                             source="analysis", details={"arquivo": track.file_path})
            if on_progress is not None:
                elapsed = time.perf_counter() - started
                eta = (elapsed / completed) * (total - completed) if completed else None
                on_progress(
                    AnalysisProgress(
                        completed=completed,
                        total=total,
                        track_id=track.id,
                        file_path=track.file_path,
                        label=_label(track),
                        outcome=outcome,
                        message=message,
                        elapsed_seconds=round(elapsed, 2),
                        eta_seconds=round(eta, 1) if eta is not None else None,
                    )
                )

        def flush() -> None:
            if buffer:
                self.repo.save_analyses(list(buffer))
                buffer.clear()

        def pending_work() -> Iterator[Track]:
            for track in tracks:
                if not self.analyzer.decoder.can_decode(track.file_path):
                    record(track, "SKIPPED", "formato não suportado sem FFmpeg")
                    continue
                yield track

        work = pending_work()
        in_flight: Dict[Future, Track] = {}
        executor = ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="musicmatch-analysis")

        def submit_next() -> bool:
            if cancel.is_set():
                return False
            track = next(work, None)
            if track is None:
                return False
            in_flight[executor.submit(self._analyze_one, track, cancel)] = track
            return True

        try:
            for _ in range(worker_count * 2):
                if not submit_next():
                    break
            while in_flight:
                # Short timeout keeps Ctrl+C responsive (blocking waits ignore it on Windows).
                done, _ = wait(list(in_flight), timeout=0.25, return_when=FIRST_COMPLETED)
                for future in done:
                    track = in_flight.pop(future)
                    analysis, outcome, message = future.result()
                    if analysis is not None:
                        buffer.append(analysis)
                    if outcome != "CANCELLED":
                        record(track, outcome, message)
                    submit_next()
                if len(buffer) >= _PERSIST_BATCH:
                    flush()
        except KeyboardInterrupt:
            cancel.set()
        finally:
            cancel_requested = cancel.is_set()
            executor.shutdown(wait=True, cancel_futures=True)
            for future, track in list(in_flight.items()):
                if future.done() and not future.cancelled():
                    analysis, outcome, message = future.result()
                    if analysis is not None and outcome != "CANCELLED":
                        buffer.append(analysis)
                        record(track, outcome, message)
            flush()

        remaining = self.repo.count_pending_analysis(path_prefix)
        status = "cancelled" if cancel_requested else "success"
        if total == 0:
            message = "Nenhuma faixa pendente de análise acústica."
        elif cancel_requested:
            message = f"Análise interrompida: {completed}/{total} faixa(s) processada(s) e salva(s)."
        else:
            message = f"Análise acústica concluída para {completed}/{total} faixa(s)."
        return AnalysisRunResult(
            status=status,
            message=message,
            decoder=decoder_name,
            workers=worker_count,
            total_candidates=total,
            analyzed_ok=counters["OK"],
            failed=counters["ERROR"],
            skipped=counters["SKIPPED"],
            cancelled=cancel_requested,
            remaining_pending=remaining,
            duration_ms=round((time.perf_counter() - started) * 1000.0, 2),
            failures=failures,
        )

    def _analyze_one(
        self, track: Track, cancel: threading.Event
    ) -> Tuple[Optional[TrackAnalysis], AnalysisOutcome, Optional[str]]:
        """Worker body: never raises, never touches the database."""
        if cancel.is_set():
            return None, "CANCELLED", None
        if not os.path.isfile(track.file_path):
            # Not persisted: the drive may simply be disconnected (ADR 0009 Soft Delete).
            return None, "SKIPPED", "arquivo indisponível no disco"
        try:
            features: AudioFeatures = self.analyzer.analyze_file(track.file_path, cancel_event=cancel)
        except DecodeCancelled:
            return None, "CANCELLED", None
        except DecoderUnavailableError as exc:
            return None, "SKIPPED", str(exc)
        except AudioDecodeError as exc:
            return self._error_record(track, str(exc)), "ERROR", str(exc)
        except Exception as exc:  # a DSP bug on one file must not abort the whole batch
            logger.exception("Unexpected analysis failure on %s", track.file_path)  # worker thread: logging is thread-safe
            message = f"erro interno de análise: {type(exc).__name__}: {exc}"
            return self._error_record(track, message), "ERROR", message
        analysis = TrackAnalysis(
            track_id=track.id,
            status="OK",
            analysis_version=ANALYSIS_VERSION,
            source_mtime=track.file_mtime,
            source_size=track.file_size,
            features=features,
        )
        return analysis, "OK", None

    @staticmethod
    def _error_record(track: Track, message: str) -> TrackAnalysis:
        return TrackAnalysis(
            track_id=track.id,
            status="ERROR",
            error_message=message[:500],
            analysis_version=ANALYSIS_VERSION,
            source_mtime=track.file_mtime,
            source_size=track.file_size,
        )

    # ------------------------------------------------------------------
    # Acoustic duplicates
    # ------------------------------------------------------------------

    def find_exact_duplicates(self) -> List[AcousticDuplicateCluster]:
        """Tracks with bit-identical fingerprints and compatible durations (cheap, indexed)."""
        clusters: List[AcousticDuplicateCluster] = []
        for rows in self.repo.get_exact_fingerprint_groups(FINGERPRINT_ALGORITHM):
            # Rows arrive sorted by duration: split wherever the duration gap is too large
            # (e.g. same intro but a different edit of the song).
            current = [rows[0]]
            for row in rows[1:]:
                if _durations_compatible(current[-1]["duration_seconds"] or 0.0, row["duration_seconds"] or 0.0):
                    current.append(row)
                else:
                    self._append_exact(clusters, current)
                    current = [row]
            self._append_exact(clusters, current)
        return clusters

    @staticmethod
    def _append_exact(clusters: List[AcousticDuplicateCluster], rows: List[Dict]) -> None:
        if len(rows) < 2:
            return
        clusters.append(
            AcousticDuplicateCluster(
                track_ids=[r["track_id"] for r in rows],
                match_type="EXACT_FINGERPRINT",
                similarity=1.0,
                signature=f"fingerprint:{rows[0]['fingerprint_hash'][:16]}",
            )
        )

    def find_fuzzy_duplicates(
        self,
        max_bit_error_rate: float = DEFAULT_MATCH_BER,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> List[AcousticDuplicateCluster]:
        """Same recording across encodes/bitrates/containers (includes exact duplicates)."""
        records = [
            r for r in self.repo.get_fingerprint_records(FINGERPRINT_ALGORITHM)
            if r["fingerprint"] and len(r["fingerprint"]) // 4 >= MIN_OVERLAP_FRAMES
        ]
        prints = [fingerprint_from_bytes(r["fingerprint"]) for r in records]
        durations = [float(r["duration_seconds"] or 0.0) for r in records]
        matches = find_similar_pairs(
            prints,
            durations,
            max_ber=max_bit_error_rate,
            duration_tolerance_seconds=DURATION_TOLERANCE_SECONDS,
            duration_tolerance_ratio=DURATION_TOLERANCE_RATIO,
            on_progress=on_progress,
        )
        similarity: Dict[Tuple[int, int], float] = {
            (m.index_a, m.index_b): m.comparison.similarity for m in matches
        }
        clusters: List[AcousticDuplicateCluster] = []
        for members in group_matches(len(records), list(similarity)):
            member_set = set(members)
            edges = [s for (a, b), s in similarity.items() if a in member_set and b in member_set]
            hashes = {records[i]["fingerprint_hash"] for i in members}
            exact = len(hashes) == 1
            clusters.append(
                AcousticDuplicateCluster(
                    track_ids=[records[i]["track_id"] for i in members],
                    match_type="EXACT_FINGERPRINT" if exact else "FUZZY_FINGERPRINT",
                    similarity=1.0 if exact else round(min(edges), 3),
                    signature=f"acoustic:{records[members[0]]['fingerprint_hash'][:16]}",
                )
            )
        return clusters


# Default singleton (same pattern as library_service / library_maintenance_service).
acoustic_analysis_service = AcousticAnalysisService()
