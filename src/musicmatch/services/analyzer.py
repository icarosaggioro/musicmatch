"""AudioAnalyzer: one decode pass -> every acoustic metric of a file (ADR 0014).

Single-pass design (decoding dominates the cost, so each file is decoded exactly once):

    FFmpeg/WAV PCM chunks ──┬─> LoudnessMeter        (whole track, streaming, O(1) memory)
                            ├─> WaveformAccumulator  (whole track, streaming)
                            └─> mono excerpt (first EXCERPT_SECONDS) ─> 11025 Hz
                                    ├─> compute_fingerprint (first 120 s after silence)
                                    ├─> estimate_tempo
                                    └─> estimate_key

The analyzer is stateless and thread-safe: it never touches the database, so the batch
service can run several instances of `analyze_file` concurrently (one FFmpeg child each).
"""

import threading
import time
from typing import List, Optional

import numpy as np

from musicmatch.domain.analysis import AudioFeatures
from musicmatch.dsp.fingerprint import (
    FINGERPRINT_ALGORITHM,
    FINGERPRINT_SAMPLE_RATE,
    compute_fingerprint,
    fingerprint_digest,
    fingerprint_to_bytes,
    to_fingerprint_rate,
)
from musicmatch.dsp.key import estimate_key
from musicmatch.dsp.loudness import LoudnessMeter
from musicmatch.dsp.tempo import estimate_tempo
from musicmatch.dsp.waveform import WaveformAccumulator
from musicmatch.services.audio_decoder import AudioDecodeError, AudioDecoder

EXCERPT_SECONDS = 240.0


class AudioAnalyzer:
    """Computes loudness, tempo, key, fingerprint and waveform summary for one audio file."""

    def __init__(self, decoder: Optional[AudioDecoder] = None, excerpt_seconds: float = EXCERPT_SECONDS) -> None:
        self.decoder = decoder or AudioDecoder()
        self.excerpt_seconds = excerpt_seconds

    def analyze_file(self, file_path: str, cancel_event: Optional[threading.Event] = None) -> AudioFeatures:
        """Decodes and analyses a file.

        Raises:
            DecoderUnavailableError: no installed backend can decode the format.
            AudioDecodeError: the file is unreadable/corrupt or contains no audio.
            DecodeCancelled: cancel_event was set while decoding.
        """
        started = time.perf_counter()
        excerpt: List[np.ndarray] = []
        excerpt_frames = 0
        total_frames = 0
        with self.decoder.open(file_path, cancel_event) as stream:
            fmt = stream.format
            backend = stream.backend
            meter = LoudnessMeter(fmt.sample_rate, fmt.channels)
            waveform = WaveformAccumulator(fmt.sample_rate)
            excerpt_limit = int(self.excerpt_seconds * fmt.sample_rate)
            for chunk in stream.chunks():
                meter.feed(chunk)
                waveform.feed(chunk)
                total_frames += chunk.shape[0]
                if excerpt_frames < excerpt_limit:
                    mono = chunk.mean(axis=1) if chunk.shape[1] > 1 else chunk[:, 0]
                    part = np.array(mono[: excerpt_limit - excerpt_frames], dtype=np.float32)
                    excerpt.append(part)
                    excerpt_frames += part.size

        if total_frames == 0:
            raise AudioDecodeError("no audio samples could be decoded")

        mono = to_fingerprint_rate(np.concatenate(excerpt), fmt.sample_rate)
        loudness = meter.result()
        peaks, rms = waveform.summary()
        fingerprint = compute_fingerprint(mono, FINGERPRINT_SAMPLE_RATE)
        tempo = estimate_tempo(mono, FINGERPRINT_SAMPLE_RATE)
        key = estimate_key(mono, FINGERPRINT_SAMPLE_RATE)

        return AudioFeatures(
            duration_seconds=round(total_frames / fmt.sample_rate, 3),
            sample_rate=fmt.sample_rate,
            channels=fmt.channels,
            decoder=backend,
            integrated_lufs=loudness.integrated_lufs,
            loudness_range_lu=loudness.loudness_range_lu,
            sample_peak_dbfs=loudness.sample_peak_dbfs,
            bpm=tempo.bpm,
            bpm_confidence=tempo.confidence,
            musical_key=key.name if key else None,
            camelot_key=key.camelot if key else None,
            key_confidence=key.confidence if key else None,
            tuning_cents=key.tuning_cents if key else None,
            fingerprint_algorithm=FINGERPRINT_ALGORITHM,
            fingerprint_hash=fingerprint_digest(fingerprint) if fingerprint.size else None,
            fingerprint_frames=int(fingerprint.size),
            fingerprint=fingerprint_to_bytes(fingerprint) if fingerprint.size else None,
            waveform_peaks=peaks,
            waveform_rms=rms,
            processing_ms=round((time.perf_counter() - started) * 1000.0, 1),
        )
