"""Tempo (BPM) estimation from the onset-strength envelope.

Pipeline:
1. Onset strength: half-wave rectified spectral flux of log-compressed magnitudes
   (1024-sample frames, 128-sample hop at 11025 Hz -> ~86 envelope frames per second),
   with its slowly varying trend removed.
2. Periodicity: autocorrelation of the envelope, weighted by a log-normal tempo prior
   centred on 120 BPM (one octave standard deviation) to resolve the classic half/double
   tempo ambiguity towards musically common values.
3. Precision: the winning lag is refined on a sub-frame grid by summing the interpolated
   autocorrelation at up to sixteen of its multiples, so a 1-frame lag resolution (~2.8 BPM
   at 120 BPM) becomes a few hundredths of a BPM on steady material.

Known limitation: like every autocorrelation tempo estimator (librosa included), the
metrical level is ambiguous for some material: a 150 or 174 BPM track whose kick marks
every other beat may be reported at half tempo (75 / 87 BPM).

Confidence is the normalized autocorrelation at the detected period (0 = no periodicity).
Signals without impulsive onsets (drones, pads, vibrato) report no tempo at all.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import get_window

from musicmatch.dsp.fingerprint import FINGERPRINT_SAMPLE_RATE, to_fingerprint_rate

MIN_BPM = 60.0
MAX_BPM = 200.0
_PRIOR_CENTER_BPM = 120.0
_PRIOR_OCTAVES = 1.0
_FRAME = 1024
_HOP = 128
_MIN_SECONDS = 8.0
_FRAMES_PER_BATCH = 2048
_REFINE_MULTIPLES = 16
# Musical onsets make the envelope impulsive (kurtosis ~9-25 measured on music), while steady
# tones, pads and vibrato only leave a smooth, aliased ripple (kurtosis ~3-5) whose
# periodicity would otherwise be mistaken for a confident tempo.
_MIN_ONSET_KURTOSIS = 6.0


@dataclass(frozen=True)
class TempoEstimate:
    bpm: Optional[float]
    confidence: float


def onset_envelope(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    x = to_fingerprint_rate(np.asarray(samples, dtype=np.float32).reshape(-1), sample_rate)
    if x.size < _FRAME * 2:
        return np.zeros(0)
    window = get_window("hann", _FRAME).astype(np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(x, _FRAME)[::_HOP]
    n = frames.shape[0]
    flux = np.zeros(n)
    previous = None
    for start in range(0, n, _FRAMES_PER_BATCH):
        # Overlap one frame with the previous batch so the difference is continuous.
        spec = np.log1p(100.0 * np.abs(np.fft.rfft(frames[start:start + _FRAMES_PER_BATCH] * window, axis=1)))
        if previous is not None:
            spec = np.vstack([previous, spec])
            diff = np.maximum(0.0, np.diff(spec, axis=0)).sum(axis=1)
            flux[start:start + diff.size] = diff
        else:
            diff = np.maximum(0.0, np.diff(spec, axis=0)).sum(axis=1)
            flux[start + 1:start + 1 + diff.size] = diff
        previous = spec[-1:]
    fps = FINGERPRINT_SAMPLE_RATE / _HOP
    trend = uniform_filter1d(flux, size=max(1, int(fps)), mode="nearest")
    return np.maximum(0.0, flux - trend)


def _interp(acf: np.ndarray, lag: np.ndarray) -> np.ndarray:
    return np.interp(lag, np.arange(acf.size), acf, right=0.0)


def estimate_tempo(samples: np.ndarray, sample_rate: int) -> TempoEstimate:
    """Estimates the dominant tempo of a mono signal; bpm is None when no pulse is found."""
    if samples.size < _MIN_SECONDS * sample_rate:
        return TempoEstimate(bpm=None, confidence=0.0)
    env = onset_envelope(samples, sample_rate)
    if env.size == 0 or not np.any(env > 0):
        return TempoEstimate(bpm=None, confidence=0.0)
    fps = FINGERPRINT_SAMPLE_RATE / _HOP
    env = env - env.mean()
    variance = float(np.mean(env * env))
    if variance <= 0 or float(np.mean(env ** 4)) / (variance * variance) < _MIN_ONSET_KURTOSIS:
        return TempoEstimate(bpm=None, confidence=0.0)
    size = 1 << int(np.ceil(np.log2(env.size * 2)))
    spectrum = np.fft.rfft(env, size)
    acf = np.fft.irfft(spectrum * np.conj(spectrum), size)[: env.size]
    if acf[0] <= 0:
        return TempoEstimate(bpm=None, confidence=0.0)
    # Unbiased normalization so long lags are not penalized by shrinking overlap.
    acf = acf / (env.size - np.arange(env.size)) / (acf[0] / env.size)

    min_lag = int(np.floor(60.0 * fps / MAX_BPM))
    max_lag = int(np.ceil(60.0 * fps / MIN_BPM))
    if max_lag * 4 >= acf.size:
        return TempoEstimate(bpm=None, confidence=0.0)
    lags = np.arange(min_lag, max_lag + 1)
    bpms = 60.0 * fps / lags
    prior = np.exp(-0.5 * (np.log2(bpms / _PRIOR_CENTER_BPM) / _PRIOR_OCTAVES) ** 2)
    # Reward lags whose multiples are also periodic (true beat periods repeat).
    harmonic = acf[lags] + 0.5 * _interp(acf, 2.0 * lags)
    score = np.maximum(harmonic, 0.0) * prior
    best = int(lags[int(np.argmax(score))])

    # Sub-frame refinement: the k-th multiple of the period is resolved k times more finely,
    # so summing up to 16 multiples (while enough overlap remains) pins the period precisely.
    fine = np.arange(best - 1.0, best + 1.0, 0.005)
    multiples = [k for k in range(1, _REFINE_MULTIPLES + 1) if k * (best + 1) < acf.size // 2] or [1]
    refined = sum(_interp(acf, k * fine) for k in multiples)
    period = float(np.clip(fine[int(np.argmax(refined))], 60.0 * fps / MAX_BPM, 60.0 * fps / MIN_BPM))
    confidence = float(np.clip(_interp(acf, np.array([period]))[0], 0.0, 1.0))
    bpm = 60.0 * fps / period
    return TempoEstimate(bpm=round(bpm, 1), confidence=round(confidence, 3))
