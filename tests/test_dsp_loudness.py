"""EBU R128 / ITU-R BS.1770-4 conformance tests for the streaming LoudnessMeter (ADR 0014)."""

import re
import shutil
import subprocess

import numpy as np
import pytest

from audio_synth import sine, synth_song, write_wav
from musicmatch.dsp.loudness import LoudnessMeter, k_weighting_sos

HAS_FFMPEG = shutil.which("ffmpeg") is not None


def _measure(signal: np.ndarray, sr: int, channels: int = 2, chunk: int = 0):
    meter = LoudnessMeter(sr, channels)
    data = np.repeat(signal[:, None], channels, axis=1) if signal.ndim == 1 else signal
    if chunk:
        for start in range(0, data.shape[0], chunk):
            meter.feed(data[start:start + chunk])
    else:
        meter.feed(data)
    return meter.result()


def test_k_weighting_matches_bs1770_reference_at_48k():
    sos = k_weighting_sos(48000)
    # Coefficients published in ITU-R BS.1770-4, Tables 1 and 2.
    np.testing.assert_allclose(sos[0, :3], [1.53512485958697, -2.69169618940638, 1.19839281085285], atol=1e-9)
    np.testing.assert_allclose(sos[0, 4:], [-1.69065929318241, 0.73248077421585], atol=1e-9)
    np.testing.assert_allclose(sos[1, :3], [1.0, -2.0, 1.0], atol=1e-12)
    np.testing.assert_allclose(sos[1, 4:], [-1.99004745483398, 0.99007225036621], atol=1e-9)


@pytest.mark.parametrize("level", [-23.0, -33.0])
def test_ebu_tech3341_stereo_sine_reads_its_level(level):
    # EBU Tech 3341 cases 1/2: 1 kHz stereo sine at -23 / -33 dBFS -> -23.0 / -33.0 LUFS (+/-0.1).
    result = _measure(sine(1000, 20, level, sr=48000), 48000)
    assert result.integrated_lufs == pytest.approx(level, abs=0.1)
    assert result.sample_peak_dbfs == pytest.approx(level, abs=0.05)


def test_relative_gate_ignores_quiet_passages():
    sr = 48000
    signal = np.concatenate([sine(1000, 4, -36, sr), sine(1000, 20, -23, sr), sine(1000, 4, -36, sr)])
    assert _measure(signal, sr).integrated_lufs == pytest.approx(-23.0, abs=0.1)


@pytest.mark.parametrize("second_level,expected_lra", [(-30.0, 10.0), (-15.0, 5.0)])
def test_ebu_tech3342_loudness_range(second_level, expected_lra):
    # EBU Tech 3342 cases 1/2: 20 s at -20 dBFS followed by 20 s at -30 / -15 dBFS.
    sr = 48000
    signal = np.concatenate([sine(1000, 20, -20, sr), sine(1000, 20, second_level, sr)])
    assert _measure(signal, sr).loudness_range_lu == pytest.approx(expected_lra, abs=1.0)


def test_mono_counts_one_channel_and_other_sample_rates_work():
    stereo = _measure(sine(1000, 10, -23, sr=44100), 44100, channels=2).integrated_lufs
    mono = _measure(sine(1000, 10, -23, sr=44100), 44100, channels=1).integrated_lufs
    assert stereo == pytest.approx(-23.0, abs=0.1)
    assert mono == pytest.approx(stereo - 3.01, abs=0.05)


def test_streaming_is_independent_of_chunk_boundaries():
    signal = synth_song(seconds=12, seed=3)
    whole = _measure(signal, 44100)
    chunked = _measure(signal, 44100, chunk=7777)
    assert chunked == whole


def test_silence_and_too_short_audio_yield_none():
    silent = _measure(np.zeros(44100 * 3), 44100)
    assert silent.integrated_lufs is None and silent.loudness_range_lu is None and silent.sample_peak_dbfs is None
    short = _measure(sine(1000, 0.2, -20), 44100)
    assert short.integrated_lufs is None
    assert short.sample_peak_dbfs == pytest.approx(-20.0, abs=0.05)


def test_meter_validates_channel_layout():
    meter = LoudnessMeter(44100, 2)
    with pytest.raises(ValueError):
        meter.feed(np.zeros((100, 3)))
    with pytest.raises(ValueError):
        LoudnessMeter(44100, 2, channel_weights=[1.0])
    with pytest.raises(ValueError):
        LoudnessMeter(0, 2)


@pytest.mark.skipif(not HAS_FFMPEG, reason="FFmpeg not installed")
def test_matches_ffmpeg_ebur128_reference(tmp_path):
    signal = np.concatenate([synth_song(seconds=12, seed=11) * 0.5, synth_song(seconds=12, seed=3)])
    path = write_wav(tmp_path / "song.wav", signal)
    ours = _measure(signal, 44100)
    stderr = subprocess.run(
        ["ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=True,
    ).stderr
    reference_i = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", stderr)[-1])
    reference_lra = float(re.findall(r"LRA:\s+([\d.]+) LU", stderr)[-1])
    assert ours.integrated_lufs == pytest.approx(reference_i, abs=0.15)
    assert ours.loudness_range_lu == pytest.approx(reference_lra, abs=0.5)
