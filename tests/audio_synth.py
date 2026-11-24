"""Deterministic synthetic music for DSP tests (no binary fixtures in the repository).

`synth_song` renders a short multi-instrument arrangement (kick/snare/hi-hat, bass, chord pad
and a melody) with a known tempo and key, so BPM, key and fingerprint behaviour can be tested
against ground truth. Different seeds produce different melodies/rhythms ("different songs").
"""

import wave
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np

SR = 44100
_MAJOR = [0, 2, 4, 5, 7, 9, 11]
_MINOR = [0, 2, 3, 5, 7, 8, 10]
# Cadential progressions that establish the key unambiguously (0-based scale degrees):
# I-IV-V-I in major and i-iv-V-i in minor (V uses the raised leading tone).
_PROGRESSIONS = {"major": [0, 3, 4, 0], "minor": [0, 3, 4, 0]}


def _note(freq: float, dur: float, sr: int, harmonics: int = 6, decay: float = 3.0) -> np.ndarray:
    t = np.arange(int(dur * sr)) / sr
    tone = sum(np.sin(2 * np.pi * freq * k * t) / k for k in range(1, harmonics + 1))
    env = np.exp(-decay * t) * np.minimum(1.0, t * 200.0)
    return tone * env


def _midi_to_hz(midi: float) -> float:
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


@lru_cache(maxsize=64)
def _synth_song_cached(seconds: float, bpm: float, tonic: int, mode: str, seed: int, sr: int, drums: bool) -> np.ndarray:
    song = _render_song(seconds, bpm, tonic, mode, seed, sr, drums)
    song.setflags(write=False)  # shared between tests: must never be mutated in place
    return song


def synth_song(
    seconds: float = 30.0,
    bpm: float = 120.0,
    tonic: int = 0,
    mode: str = "major",
    seed: int = 0,
    sr: int = SR,
    drums: bool = True,
) -> np.ndarray:
    """Returns a read-only mono float signal (peak ~0.8). tonic: pitch class (0=C ... 11=B).

    Renders are cached per test session because synthesis dominates DSP test time.
    """
    return _synth_song_cached(float(seconds), float(bpm), int(tonic), mode, int(seed), int(sr), bool(drums))


def _render_song(
    seconds: float = 30.0,
    bpm: float = 120.0,
    tonic: int = 0,
    mode: str = "major",
    seed: int = 0,
    sr: int = SR,
    drums: bool = True,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    out = np.zeros(n + sr * 2)
    beat = 60.0 / bpm
    scale = _MAJOR if mode == "major" else _MINOR
    progression = _PROGRESSIONS[mode]
    beats_total = int(seconds / beat)

    def add(sig: np.ndarray, at: float, gain: float) -> None:
        i = int(at * sr)
        out[i:i + sig.size] += gain * sig[: max(0, out.size - i)]

    for b in range(beats_total):
        t0 = b * beat
        bar, beat_in_bar = divmod(b, 4)
        degree = progression[bar % len(progression)]
        root_pc = (tonic + scale[degree]) % 12
        chord = [(tonic + scale[(degree + step) % 7]) % 12 for step in (0, 2, 4)]
        if mode == "minor" and degree == 4:
            chord[1] = (chord[1] + 1) % 12  # harmonic minor: major dominant chord
        if beat_in_bar == 0:
            # Chord pad: triad held for one bar.
            for pc in chord:
                add(_note(_midi_to_hz(60 + pc), beat * 4, sr, decay=0.6), t0, 0.10)
        # Bass on every beat.
        add(_note(_midi_to_hz(36 + root_pc), beat * 0.9, sr, harmonics=4, decay=4.0), t0, 0.22)
        # Melody on eighth notes: mostly chord tones, sometimes passing scale tones (seed = tune).
        for half in (0, 1):
            if rng.random() < 0.8:
                if rng.random() < 0.7:
                    pc = chord[int(rng.integers(0, 3))]
                else:
                    pc = (tonic + scale[int(rng.integers(0, 7))]) % 12
                octave = 72 if rng.random() < 0.7 else 84
                add(_note(_midi_to_hz(octave + pc), beat * 0.45, sr, decay=5.0), t0 + half * beat / 2, 0.12)
        if drums:
            tk = np.arange(int(0.15 * sr)) / sr
            kick = np.sin(2 * np.pi * (50 + 80 * np.exp(-tk * 30)) * tk) * np.exp(-tk * 18)
            if beat_in_bar in (0, 2) or rng.random() < 0.15:
                add(kick, t0, 0.6)
            noise = rng.standard_normal(int(0.12 * sr)) * np.exp(-np.arange(int(0.12 * sr)) / sr * 30)
            if beat_in_bar in (1, 3):
                add(noise, t0, 0.25)
            hat = rng.standard_normal(int(0.03 * sr))
            hat = np.diff(hat, prepend=0.0) * np.exp(-np.arange(hat.size) / sr * 150)
            add(hat, t0, 0.08)
            add(hat, t0 + beat / 2, 0.05)
    out = out[:n]
    peak = np.max(np.abs(out)) or 1.0
    return 0.8 * out / peak


def write_wav(path: Path, samples: np.ndarray, sr: int = SR, channels: int = 2) -> Path:
    """Writes 16-bit PCM WAV (mono signal duplicated to `channels`)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.clip(np.asarray(samples, dtype=np.float64), -1.0, 1.0)
    pcm = (data * 32767.0).astype("<i2")
    if channels > 1:
        pcm = np.repeat(pcm[:, None], channels, axis=1).reshape(-1)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(pcm.tobytes())
    return path


def sine(freq: float, seconds: float, amplitude_dbfs: float, sr: int = SR) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    return 10.0 ** (amplitude_dbfs / 20.0) * np.sin(2 * np.pi * freq * t)


def silence(seconds: float, sr: int = SR) -> np.ndarray:
    return np.zeros(int(seconds * sr))


def tag_file(path: Path, title: str, artist: str, album: str = "Album", genre: Optional[str] = "Pop",
             bpm: Optional[int] = None) -> Path:
    import mediafile

    mf = mediafile.MediaFile(str(path))
    mf.title = title
    mf.artist = artist
    mf.album = album
    mf.genre = genre
    if bpm is not None:
        mf.bpm = bpm
    mf.save()
    return path


__all__ = ["SR", "synth_song", "write_wav", "sine", "silence", "tag_file"]
