"""Musical key estimation (tonic + mode) with Camelot wheel notation.

Pipeline:
1. Spectrum: 8192-sample Hann frames (0.74 s, 1.35 Hz resolution at 11025 Hz) every 2048
   samples, restricted to 55 Hz - 2 kHz where harmonic (pitched) content dominates.
2. Tuning: the magnitude-weighted circular mean of the deviation of spectral peaks from the
   equal-tempered grid estimates the reference pitch (e.g. A=432 Hz is about -32 cents).
3. Chroma: mildly log-compressed magnitudes are folded into 12 pitch classes with a triangular
   weight that fades out energy lying between two semitones.
4. Key: the time-averaged chroma is correlated with the 24 rotated Krumhansl-Kessler
   major/minor profiles; the best Pearson correlation wins and is reported as confidence.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.signal import get_window

from musicmatch.domain.music_keys import camelot_code, key_name
from musicmatch.dsp.fingerprint import FINGERPRINT_SAMPLE_RATE, to_fingerprint_rate

_KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

_FRAME = 8192
_HOP = 2048
_FMIN = 55.0
_FMAX = 2000.0
_MIN_SECONDS = 5.0
_FRAMES_PER_BATCH = 256


@dataclass(frozen=True)
class KeyEstimate:
    tonic: int  # pitch class, 0 = C
    mode: str  # "major" | "minor"
    confidence: float
    tuning_cents: float

    @property
    def name(self) -> str:
        return key_name(self.tonic, self.mode)

    @property
    def camelot(self) -> str:
        return camelot_code(self.tonic, self.mode)


def _spectrum_magnitudes(x: np.ndarray):
    freqs = np.fft.rfftfreq(_FRAME, d=1.0 / FINGERPRINT_SAMPLE_RATE)
    band = (freqs >= _FMIN) & (freqs <= _FMAX)
    window = get_window("hann", _FRAME).astype(np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(x, _FRAME)[::_HOP]
    mags = []
    for start in range(0, frames.shape[0], _FRAMES_PER_BATCH):
        spec = np.abs(np.fft.rfft(frames[start:start + _FRAMES_PER_BATCH] * window, axis=1))
        mags.append(spec[:, band].astype(np.float32))
    return freqs[band], np.vstack(mags)


def _estimate_tuning(freqs: np.ndarray, mags: np.ndarray) -> float:
    """Returns the tuning offset in semitones (-0.5..0.5) from spectral peak positions."""
    mean_spec = mags.mean(axis=0).astype(np.float64)
    if mean_spec.size < 3:
        return 0.0
    peaks = np.nonzero((mean_spec[1:-1] > mean_spec[:-2]) & (mean_spec[1:-1] >= mean_spec[2:]))[0] + 1
    if peaks.size == 0:
        return 0.0
    # Parabolic interpolation for sub-bin peak frequencies.
    a, b, c = mean_spec[peaks - 1], mean_spec[peaks], mean_spec[peaks + 1]
    denom = a - 2 * b + c
    delta = np.where(np.abs(denom) > 1e-12, 0.5 * (a - c) / denom, 0.0)
    peak_freqs = freqs[peaks] + delta * (freqs[1] - freqs[0])
    strongest = np.argsort(b)[-60:]
    midi = 69.0 + 12.0 * np.log2(peak_freqs[strongest] / 440.0)
    deviation = midi - np.round(midi)
    angle = np.angle(np.sum(b[strongest] * np.exp(2j * np.pi * deviation)))
    return float(angle / (2 * np.pi))


def estimate_key(samples: np.ndarray, sample_rate: int) -> Optional[KeyEstimate]:
    """Estimates the key of a mono signal, or None when there is no usable tonal content."""
    x = to_fingerprint_rate(np.asarray(samples, dtype=np.float32).reshape(-1), sample_rate)
    if x.size < max(_FRAME, int(_MIN_SECONDS * FINGERPRINT_SAMPLE_RATE)):
        return None
    freqs, mags = _spectrum_magnitudes(x)
    if not np.any(mags > 0):
        return None
    tuning = _estimate_tuning(freqs, mags)
    midi = 69.0 + 12.0 * np.log2(freqs / 440.0) - tuning
    nearest = np.round(midi)
    weight = np.clip(1.0 - 2.0 * np.abs(midi - nearest), 0.0, 1.0)
    pitch_class = nearest.astype(int) % 12
    fold = np.zeros((freqs.size, 12), dtype=np.float32)
    fold[np.arange(freqs.size), pitch_class] = weight

    # Mild log compression: strong enough to balance loud/quiet notes, mild enough not to
    # inflate weak upper harmonics (the 3rd harmonic would otherwise bias towards the fifth).
    compressed = np.log1p(10.0 * mags / (mags.max() + 1e-12))
    chroma = (compressed @ fold).mean(axis=0)
    if chroma.std() < 1e-9:
        return None

    best = (-2.0, 0, "major")
    for mode, profile in (("major", _KK_MAJOR), ("minor", _KK_MINOR)):
        for tonic in range(12):
            r = float(np.corrcoef(chroma, np.roll(profile, tonic))[0, 1])
            if r > best[0]:
                best = (r, tonic, mode)
    r, tonic, mode = best
    return KeyEstimate(
        tonic=tonic,
        mode=mode,
        confidence=round(max(0.0, r), 3),
        tuning_cents=round(tuning * 100.0, 1),
    )
