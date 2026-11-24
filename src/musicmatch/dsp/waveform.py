"""Waveform Summary: condensed peak/RMS envelope for instant UI rendering (see CONTEXT.md).

Computed during the same decode pass as the other metrics (it is nearly free there), so a
future GUI can draw track overviews without ever decoding audio again. Values are linear
amplitudes in 0..1, reduced to at most `max_points` buckets.
"""

from typing import List, Tuple

import numpy as np

_RESOLUTION_SECONDS = 0.05


class WaveformAccumulator:
    def __init__(self, sample_rate: int) -> None:
        self._step = max(1, int(round(_RESOLUTION_SECONDS * sample_rate)))
        self._pending = np.zeros(0, dtype=np.float32)
        self._peaks: List[np.ndarray] = []
        self._squares: List[np.ndarray] = []

    def feed(self, samples: np.ndarray) -> None:
        block = np.asarray(samples, dtype=np.float32)
        mono_peak = np.abs(block).max(axis=1) if block.ndim == 2 else np.abs(block)
        mono_square = (block * block).mean(axis=1) if block.ndim == 2 else block * block
        # Track peak and power side by side; keep the remainder for the next chunk.
        data = np.concatenate([self._pending, np.stack([mono_peak, mono_square], axis=1).reshape(-1)])
        pairs = data.size // 2
        steps = pairs // self._step
        if steps:
            used = data[: steps * self._step * 2].reshape(steps, self._step, 2)
            self._peaks.append(used[:, :, 0].max(axis=1))
            self._squares.append(used[:, :, 1].mean(axis=1))
        self._pending = data[steps * self._step * 2:]

    def summary(self, max_points: int = 1000) -> Tuple[List[float], List[float]]:
        if not self._peaks:
            return [], []
        peaks = np.concatenate(self._peaks)
        squares = np.concatenate(self._squares)
        points = min(max_points, peaks.size)
        edges = np.linspace(0, peaks.size, points + 1).astype(int)
        peak_out = np.maximum.reduceat(peaks, edges[:-1])
        rms_out = np.sqrt(np.add.reduceat(squares, edges[:-1]) / np.diff(edges))
        return (
            np.clip(peak_out, 0.0, 1.0).round(3).tolist(),
            np.clip(rms_out, 0.0, 1.0).round(3).tolist(),
        )


def quantize(values: List[float]) -> bytes:
    return bytes(np.clip(np.round(np.asarray(values, dtype=np.float64) * 255.0), 0, 255).astype(np.uint8))


def dequantize(blob: bytes) -> List[float]:
    if not blob:
        return []
    return (np.frombuffer(blob, dtype=np.uint8) / 255.0).round(3).tolist()
