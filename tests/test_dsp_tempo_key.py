"""Ground-truth tests for tempo (BPM) and musical key estimation (ADR 0014)."""

import numpy as np
import pytest
from scipy.signal import resample

from audio_synth import SR, synth_song
from musicmatch.domain.music_keys import camelot_code, camelot_for_key_name, key_name, parse_key_name
from musicmatch.dsp.key import estimate_key
from musicmatch.dsp.tempo import estimate_tempo


@pytest.mark.parametrize("bpm", [90.0, 97.5, 123.4, 140.0])
def test_tempo_of_synthetic_songs_is_precise(bpm):
    # Steady, sample-exact beats: the harmonic refinement should land within a few hundredths.
    estimate = estimate_tempo(synth_song(seconds=24, bpm=bpm, seed=int(bpm)), SR)
    assert estimate.bpm == pytest.approx(bpm, abs=0.15)
    assert estimate.confidence > 0.3


def test_tempo_of_plain_click_track():
    signal = np.zeros(SR * 20)
    period = int(SR * 60 / 100.0)
    for start in range(0, signal.size - 200, period):
        signal[start:start + 200] = np.hanning(200)
    assert estimate_tempo(signal, SR).bpm == pytest.approx(100.0, abs=0.2)


def test_tempo_is_none_without_a_pulse():
    assert estimate_tempo(np.zeros(SR * 12), SR).bpm is None
    assert estimate_tempo(synth_song(seconds=5, seed=1), SR).bpm is None  # too short
    t = np.arange(SR * 12) / SR
    drone = np.sin(2 * np.pi * 220 * t)
    pad = sum(np.sin(2 * np.pi * f * t) for f in (220.0, 277.2, 329.6))
    vibrato = np.sin(2 * np.pi * 220 * t + 3 * np.sin(2 * np.pi * 5 * t))
    for steady in (drone, pad, vibrato):
        assert estimate_tempo(steady, SR).bpm is None
    noise = np.random.default_rng(0).standard_normal(t.size) * 0.1
    estimate = estimate_tempo(noise, SR)
    assert estimate.confidence < 0.2  # below the catalog projection threshold
    assert estimate.bpm is None or 60.0 <= estimate.bpm <= 200.0


@pytest.mark.parametrize(
    "tonic,mode",
    [(0, "major"), (9, "minor"), (6, "minor"), (3, "major"), (11, "major"), (7, "minor")],
)
def test_key_of_synthetic_songs(tonic, mode):
    estimate = estimate_key(synth_song(seconds=16, bpm=110, tonic=tonic, mode=mode, seed=tonic * 7 + (mode == "minor")), SR)
    assert (estimate.tonic, estimate.mode) == (tonic, mode), estimate.name
    assert estimate.confidence > 0.5


def test_key_survives_non_440_tuning():
    song = synth_song(seconds=16, bpm=100, tonic=2, mode="major", seed=5)
    detuned = resample(song, int(song.size * 440 / 432))  # played back at A=432 Hz
    estimate = estimate_key(detuned, SR)
    assert estimate.name == "D major"
    assert estimate.tuning_cents == pytest.approx(-31.8, abs=4.0)


def test_key_is_none_for_silence_or_short_audio():
    assert estimate_key(np.zeros(SR * 10), SR) is None
    assert estimate_key(synth_song(seconds=2, seed=1), SR) is None


def test_camelot_wheel_mapping():
    assert camelot_code(9, "minor") == "8A"  # A minor
    assert camelot_code(9, "major") == "11B"  # A major
    assert camelot_code(0, "major") == "8B"  # C major
    assert camelot_code(0, "minor") == "5A"  # C minor
    codes = {camelot_code(t, m) for t in range(12) for m in ("major", "minor")}
    assert len(codes) == 24
    # Relative major/minor pairs share the Camelot number (e.g. C major 8B / A minor 8A).
    for tonic in range(12):
        assert camelot_code(tonic, "major")[:-1] == camelot_code((tonic + 9) % 12, "minor")[:-1]


def test_key_name_round_trip():
    for tonic in range(12):
        for mode in ("major", "minor"):
            assert parse_key_name(key_name(tonic, mode)) == (tonic, mode)
    assert key_name(1, "minor") == "C# minor" and key_name(1, "major") == "Db major"
    assert camelot_for_key_name("F# minor") == "11A"
    assert parse_key_name("nonsense") is None and camelot_for_key_name(None) is None
