"""Acoustic fingerprint robustness and matching tests (ADR 0014)."""

import shutil
import subprocess
import time

import numpy as np
import pytest

from audio_synth import SR, silence, synth_song, write_wav
from musicmatch.dsp.fingerprint import (
    DEFAULT_MATCH_BER,
    FRAME_SECONDS,
    compare_fingerprints,
    compute_fingerprint,
    find_similar_pairs,
    fingerprint_digest,
    fingerprint_from_bytes,
    fingerprint_to_bytes,
    group_matches,
)

HAS_FFMPEG = shutil.which("ffmpeg") is not None


def _fp(signal, sr=SR):
    return compute_fingerprint(np.asarray(signal, dtype=np.float32), sr)


def _ber(a, b):
    return compare_fingerprints(_fp(a), _fp(b)).bit_error_rate


@pytest.fixture(scope="module")
def song():
    return synth_song(seconds=30, bpm=118, tonic=4, mode="minor", seed=21)


def test_fingerprint_is_deterministic_and_compact(song):
    first, second = _fp(song), _fp(song)
    assert first.dtype == np.uint32
    assert np.array_equal(first, second)
    assert fingerprint_digest(first) == fingerprint_digest(second)
    # ~10.8 sub-fingerprints per second of audio (4 bytes each).
    assert abs(first.size - 30 / FRAME_SECONDS) < 12
    assert np.array_equal(fingerprint_from_bytes(fingerprint_to_bytes(first)), first)


def test_leading_silence_gain_and_misalignment_do_not_change_identity(song):
    padded = np.concatenate([silence(1.7), song])
    comparison = compare_fingerprints(_fp(song), _fp(padded))
    assert comparison.bit_error_rate < 0.02 and comparison.offset_frames == 0
    assert _ber(song, np.asarray(song) * 0.4) < 0.02  # re-levelled (-8 dB)
    for shift in (97, 311, 700):  # arbitrary sub-frame offsets between two rips
        assert _ber(song, song[shift:]) < 0.15


def test_noise_and_resampling_are_tolerated(song):
    noisy = song + np.random.default_rng(1).standard_normal(song.size) * 0.02  # ~25 dB SNR
    assert _ber(song, noisy) < DEFAULT_MATCH_BER
    from scipy.signal import resample_poly

    as_22k = resample_poly(np.asarray(song), 1, 2)
    assert compare_fingerprints(_fp(song), _fp(as_22k, 22050)).bit_error_rate < 0.1


def test_low_level_noise_at_40_db_snr_is_grouped_and_unrelated_signals_are_not(song):
    signal = np.asarray(song, dtype=np.float64)
    rms = float(np.sqrt(np.mean(signal ** 2)))
    noisy = signal + np.random.default_rng(7).standard_normal(signal.size) * rms * 10 ** (-40 / 20)
    unrelated = synth_song(seconds=30, bpm=96, tonic=9, mode="major", seed=77)
    matches = find_similar_pairs([_fp(signal), _fp(noisy), _fp(unrelated)], [30.0, 30.0, 30.0])
    assert [(m.index_a, m.index_b) for m in matches] == [(0, 1)]


def test_matching_a_library_of_ten_thousand_tracks_stays_under_two_minutes():
    """Issue #30: realistic track lengths (mean 230 s, deviation 60 s), full-size fingerprints."""
    rng = np.random.default_rng(30)
    count, frames = 10_000, 1_290
    prints = [rng.integers(0, 2 ** 32, frames, dtype=np.uint32) for _ in range(count)]
    prints[-1] = prints[0].copy()  # one real duplicate to find among them
    durations = np.clip(rng.normal(230, 60, count), 45, 900)
    durations[-1] = durations[0]
    started = time.perf_counter()
    matches = find_similar_pairs(prints, durations)
    elapsed = time.perf_counter() - started
    assert [(m.index_a, m.index_b) for m in matches] == [(0, count - 1)]
    assert elapsed < 120, f"took {elapsed:.0f} s"


def test_different_songs_are_far_apart(song):
    other_key = synth_song(seconds=30, bpm=118, tonic=9, mode="major", seed=4)
    other_tempo = synth_song(seconds=30, bpm=96, tonic=4, mode="minor", seed=5)
    assert _ber(song, other_key) > 0.35
    assert _ber(song, other_tempo) > 0.35


def test_silence_and_short_clips_have_no_fingerprint():
    assert _fp(np.zeros(SR * 10)).size == 0
    assert _fp(synth_song(seconds=30, seed=2)[: int(SR * 0.5)]).size == 0


def test_compare_requires_minimum_overlap(song):
    fp = _fp(song)
    assert compare_fingerprints(fp[:20], fp[:20]) is None
    exact = compare_fingerprints(fp, fp)
    assert exact.bit_error_rate == 0.0 and exact.similarity == 1.0 and exact.offset_seconds == 0.0


def test_find_similar_pairs_uses_duration_blocking_and_verification(song):
    variants = [
        _fp(song),                                                        # 0 original
        _fp(np.concatenate([silence(0.8), np.asarray(song) * 0.5])),     # 1 same recording
        _fp(synth_song(seconds=30, bpm=118, tonic=9, mode="major", seed=4)),  # 2 different song
        _fp(song[523:]),                                                  # 3 same recording, shifted
        _fp(song),                                                        # 4 identical print, but
    ]
    durations = [30.0, 30.8, 30.0, 30.0, 200.0]                           #   incompatible duration
    progress = []
    matches = find_similar_pairs(variants, durations, on_progress=lambda done, total: progress.append((done, total)))
    pairs = {(m.index_a, m.index_b) for m in matches}
    assert pairs == {(0, 1), (0, 3), (1, 3)}
    assert all(m.comparison.bit_error_rate <= DEFAULT_MATCH_BER for m in matches)
    assert progress[-1] == (5, 5)
    assert group_matches(5, sorted(pairs)) == [[0, 1, 3]]
    assert find_similar_pairs(variants[:1], durations[:1]) == []


def test_group_matches_is_transitive():
    assert group_matches(6, [(4, 5), (0, 2), (2, 3)]) == [[0, 2, 3], [4, 5]]
    assert group_matches(3, []) == []


@pytest.mark.skipif(not HAS_FFMPEG, reason="FFmpeg not installed")
@pytest.mark.parametrize(
    "codec_args,suffix",
    [
        (["-c:a", "libmp3lame", "-b:a", "64k"], ".mp3"),
        (["-c:a", "aac", "-b:a", "96k"], ".m4a"),
        (["-c:a", "libopus", "-b:a", "48k"], ".opus"),
    ],
)
def test_lossy_codecs_preserve_identity(tmp_path, song, codec_args, suffix):
    from musicmatch.services.audio_decoder import AudioDecoder

    excerpt = np.asarray(song)[: SR * 15]
    source = write_wav(tmp_path / "source.wav", excerpt)
    encoded = tmp_path / f"encoded{suffix}"
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(source), *codec_args, str(encoded)], capture_output=True
    )
    if result.returncode != 0:
        pytest.skip(f"FFmpeg build lacks encoder: {codec_args[1]}")
    with AudioDecoder().open(str(encoded)) as stream:
        decoded = np.concatenate([chunk.mean(axis=1) for chunk in stream.chunks()])
    assert compare_fingerprints(_fp(excerpt), _fp(decoded, stream.format.sample_rate)).bit_error_rate < 0.15
