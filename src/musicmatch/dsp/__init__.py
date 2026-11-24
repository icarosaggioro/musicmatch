"""Pure DSP layer of MusicMatch (ADR 0014).

Every module here is NumPy/SciPy only: no file I/O, database or UI code. Inputs are PCM
arrays, outputs are small immutable results. This is deliberately the seam where the
planned Rust engine (musicmatch_core via PyO3) can replace individual algorithms.
"""

from musicmatch.dsp.fingerprint import (
    FINGERPRINT_ALGORITHM,
    FingerprintComparison,
    compare_fingerprints,
    compute_fingerprint,
)
from musicmatch.dsp.key import KeyEstimate, estimate_key
from musicmatch.dsp.loudness import LoudnessMeter, LoudnessStats
from musicmatch.dsp.tempo import TempoEstimate, estimate_tempo
from musicmatch.dsp.waveform import WaveformAccumulator

__all__ = [
    "FINGERPRINT_ALGORITHM",
    "FingerprintComparison",
    "KeyEstimate",
    "LoudnessMeter",
    "LoudnessStats",
    "TempoEstimate",
    "WaveformAccumulator",
    "compare_fingerprints",
    "compute_fingerprint",
    "estimate_key",
    "estimate_tempo",
]
