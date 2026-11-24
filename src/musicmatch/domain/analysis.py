"""Acoustic Analysis Domain Models (ADR 0014).

Everything the analysis pipeline exposes is a Pydantic model so the same objects can be
rendered by the console today and serialized to JSON for a GUI (IPC/WebSocket) later:
`model.model_dump(mode="json")` is safe for every model in this module (the raw
fingerprint bytes are excluded from serialization on purpose).
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# Bump whenever a DSP algorithm changes in a way that alters stored results: every track
# analysed with an older version becomes pending again on the next /analyze run.
ANALYSIS_VERSION = 1

AnalysisStatus = Literal["OK", "ERROR"]
AnalysisOutcome = Literal["OK", "ERROR", "SKIPPED", "CANCELLED"]
DuplicateMatchType = Literal["METADATA", "EXACT_FINGERPRINT", "FUZZY_FINGERPRINT"]


class AudioFeatures(BaseModel):
    """Signal-derived measurements of one audio file (one decode pass)."""

    duration_seconds: float = Field(ge=0, description="Decoded audio duration in seconds")
    sample_rate: int = Field(gt=0, description="Analysis sample rate in Hz")
    channels: int = Field(gt=0, description="Analysed channel count (multichannel is downmixed to stereo)")
    decoder: str = Field(..., description="Decoder backend used ('ffmpeg' | 'wave')")

    integrated_lufs: Optional[float] = Field(default=None, description="Integrated loudness (EBU R128 / BS.1770-4) in LUFS")
    loudness_range_lu: Optional[float] = Field(default=None, description="Loudness Range (EBU Tech 3342) in LU")
    sample_peak_dbfs: Optional[float] = Field(default=None, description="Sample peak level in dBFS")

    bpm: Optional[float] = Field(default=None, gt=0, description="Detected tempo in beats per minute")
    bpm_confidence: float = Field(default=0.0, ge=0, le=1, description="Tempo periodicity strength (0..1)")

    musical_key: Optional[str] = Field(default=None, description="Detected key, e.g. 'A minor'")
    camelot_key: Optional[str] = Field(default=None, description="Camelot wheel code, e.g. '8A'")
    key_confidence: Optional[float] = Field(default=None, ge=0, le=1, description="Key profile correlation (0..1)")
    tuning_cents: Optional[float] = Field(default=None, description="Estimated deviation from A=440 Hz in cents")

    fingerprint_algorithm: str = Field(..., description="Acoustic fingerprint algorithm identifier")
    fingerprint_hash: Optional[str] = Field(default=None, description="SHA-256 of the exact fingerprint (None if silent/too short)")
    fingerprint_frames: int = Field(default=0, ge=0, description="Number of 32-bit sub-fingerprints")
    fingerprint: Optional[bytes] = Field(default=None, exclude=True, repr=False, description="Packed uint32 fingerprint")

    waveform_peaks: List[float] = Field(default_factory=list, description="Waveform Summary peak envelope (0..1)")
    waveform_rms: List[float] = Field(default_factory=list, description="Waveform Summary RMS envelope (0..1)")

    processing_ms: float = Field(default=0.0, ge=0, description="Wall-clock time spent decoding and analysing")


class TrackAnalysis(BaseModel):
    """Persisted analysis record of a catalog track, stamped with the file state it describes."""

    track_id: str
    status: AnalysisStatus = "OK"
    error_message: Optional[str] = None
    analysis_version: int = ANALYSIS_VERSION
    analyzed_at: Optional[str] = None
    source_mtime: Optional[float] = Field(default=None, description="Track file_mtime the analysis was computed for")
    source_size: Optional[int] = Field(default=None, description="Track file_size the analysis was computed for")
    features: Optional[AudioFeatures] = None


class AnalysisProgress(BaseModel):
    """Progress event emitted once per processed track (GUI progress bars, CLI status line)."""

    completed: int = Field(ge=0)
    total: int = Field(ge=0)
    track_id: str
    file_path: str
    label: str = Field(..., description="Human readable 'Artist - Title'")
    outcome: AnalysisOutcome
    message: Optional[str] = None
    elapsed_seconds: float = Field(ge=0)
    eta_seconds: Optional[float] = Field(default=None, ge=0)

    @property
    def percent(self) -> float:
        return 100.0 * self.completed / self.total if self.total else 100.0


class AnalysisRunResult(BaseModel):
    """Summary of one batch analysis run."""

    status: Literal["success", "cancelled", "error"] = "success"
    message: str
    decoder: str
    workers: int = Field(ge=0)
    total_candidates: int = Field(ge=0, description="Tracks selected for analysis in this run")
    analyzed_ok: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0, description="Files that could not be decoded/analysed (recorded as ERROR)")
    skipped: int = Field(default=0, ge=0, description="Files not processed (unsupported without FFmpeg, missing on disk)")
    cancelled: bool = False
    remaining_pending: int = Field(default=0, ge=0, description="Tracks still pending analysis after the run")
    duration_ms: float = Field(default=0.0, ge=0)
    failures: List[str] = Field(default_factory=list, description="Sample of failure messages")


class AnalysisCoverage(BaseModel):
    """How much of the catalog has up-to-date acoustic analysis."""

    available_tracks: int = Field(ge=0)
    analyzed_tracks: int = Field(ge=0, description="AVAILABLE tracks with a current, successful analysis")
    failed_tracks: int = Field(ge=0, description="AVAILABLE tracks whose current analysis is an ERROR record")
    pending_tracks: int = Field(ge=0, description="AVAILABLE tracks never analysed, modified since, or outdated")
    decoder: str
    decoder_available: bool = Field(..., description="True when FFmpeg is available (all formats decodable)")
    supported_formats: List[str] = Field(
        default_factory=list, description="Decodable formats without FFmpeg (e.g. ['FLAC', 'MP3']); empty = all formats"
    )


class AcousticDuplicateCluster(BaseModel):
    """Tracks that share the same recording according to their acoustic fingerprints."""

    track_ids: List[str] = Field(..., min_length=2)
    match_type: DuplicateMatchType
    similarity: float = Field(ge=0, le=1, description="Lowest pairwise similarity inside the cluster (1 = identical)")
    signature: str
