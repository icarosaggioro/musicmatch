"""Streaming loudness measurement following ITU-R BS.1770-4 / EBU R128 (Tech 3341/3342).

Why a streaming meter?
----------------------
Integrated loudness must cover the whole track, but holding a decoded five-minute stereo
track in memory costs ~100 MB of float32 samples (a two-hour DJ mix would cost gigabytes).
The meter therefore consumes PCM in arbitrary chunks and only keeps one energy value per
100 ms step and channel (10 floats per second), which is all the gating stage needs:

- A 400 ms gating block with 75% overlap is exactly the mean of four consecutive 100 ms steps.
- A 3 s short-term window (used by Loudness Range) is the mean of thirty consecutive steps.

K-weighting coefficients are derived for any sample rate from the analog prototype
parameters published with libebur128, so results match the 48 kHz reference filter.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np
from scipy.signal import sosfilt

ABSOLUTE_GATE_LUFS = -70.0
RELATIVE_GATE_LU = -10.0
LRA_RELATIVE_GATE_LU = -20.0
_LOUDNESS_OFFSET = -0.691
_STEP_SECONDS = 0.1
_BLOCK_STEPS = 4  # 400 ms momentary / gating block
_SHORT_TERM_STEPS = 30  # 3 s short-term window (EBU Tech 3342)


@dataclass(frozen=True)
class LoudnessStats:
    """Result of a loudness measurement. Values are None when the signal is too short or silent."""

    integrated_lufs: Optional[float]
    loudness_range_lu: Optional[float]
    sample_peak_dbfs: Optional[float]


def k_weighting_sos(sample_rate: int) -> np.ndarray:
    """Returns the two K-weighting biquads (high-shelf pre-filter + RLB high-pass) as SOS rows."""
    # Stage 1: high-shelf (+4 dB above ~1.7 kHz) modelling the acoustic effect of the head.
    f0 = 1681.974450955533
    gain_db = 3.999843853973347
    q = 0.7071752369554196
    k = np.tan(np.pi * f0 / sample_rate)
    vh = 10.0 ** (gain_db / 20.0)
    vb = vh ** 0.4996667741545416
    a0 = 1.0 + k / q + k * k
    shelf = [
        (vh + vb * k / q + k * k) / a0,
        2.0 * (k * k - vh) / a0,
        (vh - vb * k / q + k * k) / a0,
        1.0,
        2.0 * (k * k - 1.0) / a0,
        (1.0 - k / q + k * k) / a0,
    ]
    # Stage 2: RLB high-pass (~38 Hz) removing infrasonic energy.
    f0 = 38.13547087602444
    q = 0.5003270373238773
    k = np.tan(np.pi * f0 / sample_rate)
    a0 = 1.0 + k / q + k * k
    highpass = [1.0, -2.0, 1.0, 1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / q + k * k) / a0]
    return np.array([shelf, highpass], dtype=np.float64)


def default_channel_weights(channels: int) -> List[float]:
    """BS.1770 channel weights: 1.0 for front channels, 0 for LFE, 1.41 for surrounds (5.1 order)."""
    if channels == 6:  # L, R, C, LFE, Ls, Rs
        return [1.0, 1.0, 1.0, 0.0, 1.41, 1.41]
    return [1.0] * channels


def _power_to_lufs(power: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore"):
        return _LOUDNESS_OFFSET + 10.0 * np.log10(power)


class LoudnessMeter:
    """Incremental BS.1770-4 meter: feed float PCM chunks shaped (frames, channels), then call result()."""

    def __init__(
        self,
        sample_rate: int,
        channels: int,
        channel_weights: Optional[Sequence[float]] = None,
    ) -> None:
        if sample_rate <= 0 or channels <= 0:
            raise ValueError("sample_rate and channels must be positive")
        self.sample_rate = sample_rate
        self.channels = channels
        self._weights = np.asarray(channel_weights or default_channel_weights(channels), dtype=np.float64)
        if self._weights.shape != (channels,):
            raise ValueError("channel_weights must provide one weight per channel")
        self._sos = k_weighting_sos(sample_rate)
        self._zi = np.zeros((self._sos.shape[0], 2, channels), dtype=np.float64)
        self._step = max(1, int(round(_STEP_SECONDS * sample_rate)))
        self._pending = np.zeros((0, channels), dtype=np.float64)
        self._step_power: List[np.ndarray] = []  # weighted channel-summed mean square per 100 ms step
        self._peak = 0.0

    def feed(self, samples: np.ndarray) -> None:
        block = np.asarray(samples, dtype=np.float64)
        if block.ndim == 1:
            block = block[:, None]
        if block.shape[1] != self.channels:
            raise ValueError(f"expected {self.channels} channel(s), got {block.shape[1]}")
        if block.shape[0] == 0:
            return
        self._peak = max(self._peak, float(np.max(np.abs(block))))
        filtered, self._zi = sosfilt(self._sos, block, axis=0, zi=self._zi)
        squared = filtered * filtered
        if self._pending.shape[0]:
            squared = np.concatenate([self._pending, squared], axis=0)
        n_steps = squared.shape[0] // self._step
        if n_steps:
            used = n_steps * self._step
            per_step = squared[:used].reshape(n_steps, self._step, self.channels).mean(axis=1)
            self._step_power.append(per_step @ self._weights)
        self._pending = squared[n_steps * self._step:]

    def _steps(self) -> np.ndarray:
        if not self._step_power:
            return np.zeros(0, dtype=np.float64)
        return np.concatenate(self._step_power)

    @staticmethod
    def _windowed_power(steps: np.ndarray, window: int) -> np.ndarray:
        if steps.size < window:
            return np.zeros(0, dtype=np.float64)
        csum = np.concatenate([[0.0], np.cumsum(steps)])
        return (csum[window:] - csum[:-window]) / window

    def result(self) -> LoudnessStats:
        steps = self._steps()
        peak_dbfs = round(float(20.0 * np.log10(self._peak)), 2) if self._peak > 0 else None
        return LoudnessStats(
            integrated_lufs=self._integrated(steps),
            loudness_range_lu=self._loudness_range(steps),
            sample_peak_dbfs=peak_dbfs,
        )

    def _integrated(self, steps: np.ndarray) -> Optional[float]:
        blocks = self._windowed_power(steps, _BLOCK_STEPS)
        if blocks.size == 0:
            return None
        gated = blocks[_power_to_lufs(blocks) > ABSOLUTE_GATE_LUFS]
        if gated.size == 0:
            return None
        relative_gate = float(_power_to_lufs(np.array([gated.mean()]))[0]) + RELATIVE_GATE_LU
        gated = gated[_power_to_lufs(gated) > relative_gate]
        if gated.size == 0:
            return None
        return round(float(_power_to_lufs(np.array([gated.mean()]))[0]), 2)

    def _loudness_range(self, steps: np.ndarray) -> Optional[float]:
        short_term = self._windowed_power(steps, _SHORT_TERM_STEPS)
        if short_term.size == 0:
            return None
        gated = short_term[_power_to_lufs(short_term) > ABSOLUTE_GATE_LUFS]
        if gated.size == 0:
            return None
        relative_gate = float(_power_to_lufs(np.array([gated.mean()]))[0]) + LRA_RELATIVE_GATE_LU
        loudness = _power_to_lufs(gated)
        loudness = loudness[loudness > relative_gate]
        if loudness.size == 0:
            return None
        low, high = np.percentile(loudness, [10.0, 95.0])
        return round(float(high - low), 2)
