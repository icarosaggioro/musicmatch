"""Acoustic fingerprint ("mmfp1") and fingerprint comparison.

Algorithm (a time-smoothed variant of the Haitsma-Kalker robust hash):
1. Mono audio at 11025 Hz; leading silence is trimmed so copies with different lead-in
   padding start at the same musical instant; at most the first 120 s are used.
2. 4096-sample Hann frames every 256 samples (23 ms); energy in 33 logarithmic bands
   between 300 Hz and 3 kHz (a range every lossy codec preserves, even at 48-64 kbps).
3. Log band energies are smoothed over 16 frames (0.37 s) and decimated by 4, giving one
   32-bit sub-fingerprint every ~93 ms. Smoothing is what makes the hash tolerant to the
   arbitrary sub-frame misalignment between two rips/encodes of the same recording.
4. Bit m of frame n = sign of the change, over a 4-frame (0.37 s) lag, of the energy
   difference between bands m and m+1.

Two fingerprints are compared by their bit error rate (BER) at the best frame offset.
Re-encodes of one recording (MP3 320/128/64 kbps, AAC, Opus, Vorbis, resampled, mono,
re-leveled) measured BER <= 0.11 during validation, while different recordings and
different passages of the same song stayed >= 0.43 (random bits give 0.5).

The module is pure NumPy (no I/O) so it can later be swapped for the Rust engine.
"""

import hashlib
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import get_window, resample_poly

FINGERPRINT_ALGORITHM = "mmfp1"
FINGERPRINT_SAMPLE_RATE = 11025
FINGERPRINT_MAX_SECONDS = 120.0

_FRAME = 4096
_HOP = 256
_SMOOTH = 16
_DECIMATE = 4
_LAG = 4
_BANDS = 33
_BAND_LOW_HZ = 300.0
_BAND_HIGH_HZ = 3000.0
_SILENCE_DBFS = -60.0
_FRAMES_PER_BATCH = 512

FRAME_SECONDS = _HOP * _DECIMATE / FINGERPRINT_SAMPLE_RATE  # ~0.093 s per sub-fingerprint

# Similarity policy (see ADR 0014). BER = fraction of differing bits at the best offset.
DEFAULT_MATCH_BER = 0.20
MIN_OVERLAP_FRAMES = 64  # ~6 s of common audio is required before two prints can match


def _band_matrix() -> np.ndarray:
    freqs = np.fft.rfftfreq(_FRAME, d=1.0 / FINGERPRINT_SAMPLE_RATE)
    edges = np.searchsorted(freqs, np.geomspace(_BAND_LOW_HZ, _BAND_HIGH_HZ, _BANDS + 1))
    matrix = np.zeros((freqs.size, _BANDS), dtype=np.float32)
    for band in range(_BANDS):
        matrix[edges[band]:max(edges[band + 1], edges[band] + 1), band] = 1.0
    return matrix


_BAND_MATRIX = _band_matrix()
_WINDOW = get_window("hann", _FRAME).astype(np.float32)
_BIT_WEIGHTS = (np.uint64(1) << np.arange(32, dtype=np.uint64))


def to_fingerprint_rate(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    """Resamples mono audio to the 11025 Hz fingerprint/analysis rate (polyphase, anti-aliased)."""
    x = np.asarray(samples, dtype=np.float32)
    if sample_rate == FINGERPRINT_SAMPLE_RATE:
        return x
    g = np.gcd(int(sample_rate), FINGERPRINT_SAMPLE_RATE)
    return resample_poly(x, FINGERPRINT_SAMPLE_RATE // g, int(sample_rate) // g).astype(np.float32)


def trim_leading_silence(samples: np.ndarray, sample_rate: int, threshold_dbfs: float = _SILENCE_DBFS) -> np.ndarray:
    """Drops the digital-silence lead-in (10 ms windows below threshold_dbfs RMS)."""
    window = max(1, int(sample_rate * 0.01))
    n = samples.size // window
    if n == 0:
        return samples[:0]
    frames = samples[: n * window].reshape(n, window).astype(np.float64)
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    loud = np.nonzero(rms > 10.0 ** (threshold_dbfs / 20.0))[0]
    if loud.size == 0:
        return samples[:0]
    return samples[loud[0] * window:]


def _band_energies(x: np.ndarray) -> np.ndarray:
    n_frames = 1 + (x.size - _FRAME) // _HOP
    out = np.empty((n_frames, _BANDS), dtype=np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(x, _FRAME)[::_HOP]
    for start in range(0, n_frames, _FRAMES_PER_BATCH):
        batch = frames[start:start + _FRAMES_PER_BATCH] * _WINDOW
        spectrum = np.fft.rfft(batch, axis=1)
        power = (spectrum.real ** 2 + spectrum.imag ** 2).astype(np.float32)
        out[start:start + batch.shape[0]] = power @ _BAND_MATRIX
    return out


def compute_fingerprint(samples: np.ndarray, sample_rate: int = FINGERPRINT_SAMPLE_RATE) -> np.ndarray:
    """Computes the uint32 sub-fingerprint sequence of a mono signal (empty if silent/too short)."""
    x = to_fingerprint_rate(np.asarray(samples, dtype=np.float32).reshape(-1), sample_rate)
    x = trim_leading_silence(x, FINGERPRINT_SAMPLE_RATE)
    x = x[: int(FINGERPRINT_MAX_SECONDS * FINGERPRINT_SAMPLE_RATE)]
    min_samples = _FRAME + _HOP * _DECIMATE * (_LAG + 1)
    if x.size < min_samples:
        return np.zeros(0, dtype=np.uint32)
    energies = np.log(_band_energies(x).astype(np.float64) + 1e-10)
    energies = uniform_filter1d(energies, _SMOOTH, axis=0, mode="nearest")[::_DECIMATE]
    diff = energies[:, :-1] - energies[:, 1:]
    bits = (diff[_LAG:] - diff[:-_LAG]) > 0
    return (bits.astype(np.uint64) @ _BIT_WEIGHTS).astype(np.uint32)


def fingerprint_to_bytes(fingerprint: np.ndarray) -> bytes:
    return np.asarray(fingerprint, dtype="<u4").tobytes()


def fingerprint_from_bytes(blob: Optional[bytes]) -> np.ndarray:
    if not blob:
        return np.zeros(0, dtype=np.uint32)
    return np.frombuffer(blob, dtype="<u4").astype(np.uint32)


def fingerprint_digest(fingerprint: np.ndarray) -> str:
    """Stable hash of the exact fingerprint: equal digests = exact acoustic duplicates."""
    return hashlib.sha256(FINGERPRINT_ALGORITHM.encode() + fingerprint_to_bytes(fingerprint)).hexdigest()


@dataclass(frozen=True)
class FingerprintComparison:
    bit_error_rate: float
    offset_frames: int  # positive: b starts later inside a
    overlap_frames: int

    @property
    def similarity(self) -> float:
        """1.0 = identical, 0.0 = as different as random bits."""
        return max(0.0, 1.0 - 2.0 * self.bit_error_rate)

    @property
    def offset_seconds(self) -> float:
        return self.offset_frames * FRAME_SECONDS


def compare_fingerprints(
    a: np.ndarray,
    b: np.ndarray,
    max_offset_frames: int = 32,
    min_overlap_frames: int = MIN_OVERLAP_FRAMES,
) -> Optional[FingerprintComparison]:
    """Bit error rate between two fingerprints at the best alignment within +/- max_offset_frames."""
    a = np.asarray(a, dtype=np.uint32)
    b = np.asarray(b, dtype=np.uint32)
    best: Optional[FingerprintComparison] = None
    for offset in range(-max_offset_frames, max_offset_frames + 1):
        if offset >= 0:
            seg_a, seg_b = a[offset:], b
        else:
            seg_a, seg_b = a, b[-offset:]
        n = min(seg_a.size, seg_b.size)
        if n < min_overlap_frames:
            continue
        errors = int(np.bitwise_count(seg_a[:n] ^ seg_b[:n]).sum(dtype=np.int64))
        ber = errors / (32.0 * n)
        if best is None or ber < best.bit_error_rate:
            best = FingerprintComparison(bit_error_rate=ber, offset_frames=offset, overlap_frames=n)
    return best


@dataclass(frozen=True)
class FingerprintMatch:
    index_a: int
    index_b: int
    comparison: FingerprintComparison


def find_similar_pairs(
    fingerprints: Sequence[np.ndarray],
    durations: Sequence[float],
    max_ber: float = DEFAULT_MATCH_BER,
    duration_tolerance_seconds: float = 5.0,
    duration_tolerance_ratio: float = 0.03,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> List[FingerprintMatch]:
    """Finds all pairs of fingerprints whose BER is <= max_ber (library-scale fuzzy matching).

    Scales to large libraries without comparing every pair:
    1. Blocking: items are sorted by duration and only compared with neighbours whose duration
       is within max(duration_tolerance_seconds, duration_tolerance_ratio * duration).
    2. Prefilter: one vectorized XOR/popcount over a mid-track window at small offsets
       rejects nearly all non-matching neighbours in a single NumPy call per item.
    3. Verification: survivors are compared over their full overlap with a wider offset search.
    """
    n = len(fingerprints)
    if n < 2:
        return []
    order = np.argsort(np.asarray(durations, dtype=np.float64), kind="stable")
    sorted_durations = np.asarray(durations, dtype=np.float64)[order]
    prints = [np.asarray(fingerprints[i], dtype=np.uint32) for i in order]

    # Prefilter window: frames [start, start + width) compared at offsets within +/- shift.
    start, width, shift = 32, 160, 6
    span = width + 2 * shift
    window = np.zeros((n, span), dtype=np.uint32)
    has_window = np.zeros(n, dtype=bool)
    for idx, fp in enumerate(prints):
        seg = fp[start - shift:start - shift + span]
        if seg.size == span:
            window[idx] = seg
            has_window[idx] = True
    prefilter_ber = min(0.5, max_ber + 0.12)  # generous: only rejects clear non-matches

    matches: List[FingerprintMatch] = []
    for i in range(n):
        if on_progress is not None:
            on_progress(i, n)
        if prints[i].size < MIN_OVERLAP_FRAMES:
            continue
        limit = sorted_durations[i] + max(duration_tolerance_seconds, duration_tolerance_ratio * sorted_durations[i])
        end = int(np.searchsorted(sorted_durations, limit, side="right"))
        if end <= i + 1:
            continue
        candidates = np.arange(i + 1, end)
        candidates = candidates[[prints[j].size >= MIN_OVERLAP_FRAMES for j in candidates]]
        if candidates.size == 0:
            continue

        if has_window[i]:
            windowed = candidates[has_window[candidates]]
            others = candidates[~has_window[candidates]]
            survivors = list(others)
            if windowed.size:
                ref = window[i, shift:shift + width]
                block = window[windowed]
                best = np.full(windowed.size, 1.0)
                for offset in range(-shift, shift + 1):
                    seg = block[:, shift + offset:shift + offset + width]
                    ber = np.bitwise_count(seg ^ ref).sum(axis=1, dtype=np.int64) / (32.0 * width)
                    best = np.minimum(best, ber)
                survivors.extend(windowed[best <= prefilter_ber])
        else:
            survivors = list(candidates)

        for j in survivors:
            comparison = compare_fingerprints(prints[i], prints[j])
            if comparison is not None and comparison.bit_error_rate <= max_ber:
                a, b = int(order[i]), int(order[j])
                matches.append(FingerprintMatch(index_a=min(a, b), index_b=max(a, b), comparison=comparison))
    if on_progress is not None:
        on_progress(n, n)
    return matches


def group_matches(count: int, pairs: Sequence[Tuple[int, int]]) -> List[List[int]]:
    """Union-find clustering of matched index pairs into groups (size >= 2), sorted by first index."""
    parent = list(range(count))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    groups: dict = {}
    for idx in range(count):
        groups.setdefault(find(idx), []).append(idx)
    return sorted((members for members in groups.values() if len(members) > 1), key=lambda g: g[0])
