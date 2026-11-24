"""Tests for the streaming PCM decoder (FFmpeg backend + standard-library WAV fallback)."""

import shutil
import subprocess
import threading
import wave

import numpy as np
import pytest

from audio_synth import SR, sine, write_wav
from musicmatch.services import audio_decoder
from musicmatch.services.audio_decoder import (
    AudioDecodeError,
    AudioDecoder,
    DecodeCancelled,
    DecoderUnavailableError,
    find_ffmpeg,
)

HAS_FFMPEG = shutil.which("ffmpeg") is not None
requires_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="FFmpeg not installed")


def WAVE_ONLY() -> AudioDecoder:
    """Decoder restricted to the standard-library WAV fallback (no FFmpeg, no miniaudio)."""
    return AudioDecoder(ffmpeg_path=None, use_miniaudio=False)


def MINIAUDIO_ONLY() -> AudioDecoder:
    """Decoder as seen on a machine without FFmpeg (miniaudio wheel fallback)."""
    return AudioDecoder(ffmpeg_path=None)


def _read_all(decoder: AudioDecoder, path, cancel=None):
    with decoder.open(str(path), cancel) as stream:
        return stream, np.concatenate(list(stream.chunks()))


def _write_pcm_wav(path, samples: np.ndarray, width: int, channels: int = 1, sr: int = 8000):
    if width == 1:
        raw = (np.round(samples * 127) + 128).astype(np.uint8).tobytes()
    elif width == 3:
        ints = np.round(samples * 8388607).astype(np.int32)
        raw = b"".join(int(v).to_bytes(3, "little", signed=True) for v in ints)
    else:
        dtype, scale = {2: ("<i2", 32767), 4: ("<i4", 2147483647)}[width]
        raw = np.round(samples * scale).astype(dtype).tobytes()
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(sr)
        wav.writeframes(raw)
    return path


@pytest.mark.parametrize("width", [1, 2, 3, 4])
def test_wave_fallback_decodes_integer_pcm(tmp_path, width):
    samples = np.array([0.0, 0.5, -0.5, 0.25, -0.25, 0.75])
    path = _write_pcm_wav(tmp_path / f"pcm{width}.wav", samples, width)
    stream, decoded = _read_all(WAVE_ONLY(), path)
    assert stream.backend == "wave"
    assert stream.format.sample_rate == 8000 and stream.format.channels == 1
    assert decoded.shape == (6, 1)
    np.testing.assert_allclose(decoded[:, 0], samples, atol=1.0 / 100)


def test_wave_fallback_keeps_stereo_layout(tmp_path):
    path = write_wav(tmp_path / "stereo.wav", sine(440, 3.0, -6.0), channels=2)
    stream, decoded = _read_all(WAVE_ONLY(), path)
    assert stream.format.channels == 2 and decoded.shape == (3 * SR, 2)
    assert np.max(np.abs(decoded)) == pytest.approx(10 ** (-6 / 20), abs=1e-3)


def test_without_ffmpeg_or_miniaudio_only_wav_is_supported(tmp_path):
    decoder = WAVE_ONLY()
    mp3 = tmp_path / "song.mp3"
    mp3.write_bytes(b"ID3" + b"\0" * 100)
    assert not decoder.can_decode(str(mp3))
    assert decoder.supported_extensions() == {".wav"}
    with pytest.raises(DecoderUnavailableError):
        decoder.open(str(mp3))
    assert "FFmpeg" in decoder.backend_name
    bad_wav = tmp_path / "not_really.wav"
    bad_wav.write_bytes(b"RIFF\0\0\0\0WAVEjunk")
    with pytest.raises(DecoderUnavailableError):
        decoder.open(str(bad_wav))


def test_missing_file_is_a_decode_error(tmp_path):
    with pytest.raises(AudioDecodeError):
        AudioDecoder(ffmpeg_path=None).open(str(tmp_path / "nope.wav"))


def test_wave_fallback_honours_cancellation(tmp_path):
    path = write_wav(tmp_path / "long.wav", sine(440, 10.0, -6.0))
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(DecodeCancelled):
        _read_all(WAVE_ONLY(), path, cancel)


def test_configured_ffmpeg_path_must_exist(monkeypatch, tmp_path):
    monkeypatch.setattr(audio_decoder.settings, "FFMPEG_PATH", str(tmp_path / "missing-ffmpeg.exe"))
    assert find_ffmpeg() is None
    fake = tmp_path / "ffmpeg"
    fake.write_text("")
    monkeypatch.setattr(audio_decoder.settings, "FFMPEG_PATH", str(fake))
    assert find_ffmpeg() == str(fake)


@requires_ffmpeg
def test_ffmpeg_decodes_to_float_44k_and_matches_wave_backend(tmp_path):
    signal = sine(1000, 2.0, -12.0, sr=48000)
    path = write_wav(tmp_path / "tone48k.wav", signal, sr=48000, channels=2)
    stream, decoded = _read_all(AudioDecoder(), path)
    assert stream.backend == "ffmpeg"
    assert stream.format.sample_rate == 44100 and stream.format.channels == 2
    assert decoded.shape[0] == pytest.approx(2.0 * 44100, abs=64)
    assert np.max(np.abs(decoded)) == pytest.approx(10 ** (-12 / 20), abs=2e-3)


@requires_ffmpeg
def test_ffmpeg_keeps_mono_and_downmixes_surround(tmp_path):
    mono = write_wav(tmp_path / "mono.wav", sine(440, 1.0, -6.0), channels=1)
    assert _read_all(AudioDecoder(), mono)[0].format.channels == 1
    surround = tmp_path / "surround.flac"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=1", "-af", "pan=5.1|c0=c0|c1=c0|c2=c0|c3=c0|c4=c0|c5=c0",
         str(surround)],
        check=True,
    )
    stream, decoded = _read_all(AudioDecoder(), surround)
    assert stream.format.channels == 2 and decoded.shape[1] == 2


@requires_ffmpeg
def test_ffmpeg_reports_corrupt_files(tmp_path):
    corrupt = tmp_path / "corrupt.mp3"
    corrupt.write_bytes(np.random.default_rng(0).integers(0, 256, 4096, dtype=np.uint8).tobytes())
    with pytest.raises(AudioDecodeError):
        _read_all(AudioDecoder(), corrupt)


@requires_ffmpeg
def test_ffmpeg_cancellation_kills_the_decoder(tmp_path):
    path = write_wav(tmp_path / "long.wav", sine(440, 30.0, -6.0))
    cancel = threading.Event()
    with AudioDecoder().open(str(path), cancel) as stream:
        chunks = stream.chunks()
        next(chunks)
        cancel.set()
        with pytest.raises(DecodeCancelled):
            list(chunks)
        process = stream._proc
    assert process.poll() is not None  # FFmpeg child is gone


@requires_ffmpeg
def test_ffmpeg_dying_mid_stream_is_never_accepted_as_complete(tmp_path):
    # A decoder killed externally (e.g. by a signal) produces a truncated stream: that must
    # surface as an error, never as a successful (but shortened) decode.
    path = write_wav(tmp_path / "long.wav", sine(440, 30.0, -6.0))
    with AudioDecoder().open(str(path)) as stream:
        chunks = stream.chunks()
        next(chunks)
        stream._proc.kill()
        with pytest.raises(AudioDecodeError):
            list(chunks)


@requires_ffmpeg
def test_ffmpeg_watchdog_times_out_hung_decodes(tmp_path):
    path = write_wav(tmp_path / "long.wav", sine(440, 30.0, -6.0))
    # Depending on timing the watchdog fires while reading the header or mid-stream.
    with pytest.raises(AudioDecodeError, match="timed out"):
        with AudioDecoder(timeout_seconds=0.01).open(str(path)) as stream:
            list(stream.chunks())

def test_miniaudio_fallback_decodes_wav_at_native_rate(tmp_path):
    path = write_wav(tmp_path / "tone.wav", sine(440, 2.0, -6.0, sr=22050), sr=22050, channels=1)
    decoder = MINIAUDIO_ONLY()
    assert decoder.supported_extensions() == {".mp3", ".flac", ".ogg", ".wav"}
    assert decoder.can_decode("x.FLAC") and not decoder.can_decode("x.m4a")
    stream, decoded = _read_all(decoder, path)
    assert stream.backend == "miniaudio"
    assert (stream.format.sample_rate, stream.format.channels) == (22050, 1)
    assert decoded.shape == (2 * 22050, 1)
    assert np.max(np.abs(decoded)) == pytest.approx(10 ** (-6 / 20), abs=1e-3)


def test_miniaudio_fallback_rejects_unknown_content_as_unsupported(tmp_path):
    fake = tmp_path / "not_audio.mp3"
    fake.write_bytes(b"this is not an mp3 file" * 100)
    with pytest.raises(DecoderUnavailableError):
        MINIAUDIO_ONLY().open(str(fake))
    m4a = tmp_path / "song.m4a"
    m4a.write_bytes(b"x")
    with pytest.raises(DecoderUnavailableError, match="FFmpeg"):
        MINIAUDIO_ONLY().open(str(m4a))


def test_miniaudio_fallback_honours_cancellation(tmp_path):
    path = write_wav(tmp_path / "long.wav", sine(440, 10.0, -6.0))
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(DecodeCancelled):
        _read_all(MINIAUDIO_ONLY(), path, cancel)


@requires_ffmpeg
@pytest.mark.parametrize("codec_args,suffix", [(["-c:a", "libmp3lame", "-b:a", "128k"], ".mp3"),
                                               (["-c:a", "flac"], ".flac"),
                                               (["-c:a", "libvorbis", "-q:a", "4"], ".ogg")])
def test_miniaudio_fallback_matches_ffmpeg_for_common_formats(tmp_path, codec_args, suffix):
    source = write_wav(tmp_path / "tone.wav", sine(1000, 3.0, -12.0))
    encoded = tmp_path / f"tone{suffix}"
    if subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source), *codec_args, str(encoded)]).returncode:
        pytest.skip("FFmpeg build lacks this encoder")
    fallback_stream, fallback = _read_all(MINIAUDIO_ONLY(), encoded)
    _, reference = _read_all(AudioDecoder(), encoded)
    assert fallback_stream.backend == "miniaudio"
    assert abs(fallback.shape[0] - reference.shape[0]) < 44100 * 0.1
    rms = lambda x: float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
    assert rms(fallback) == pytest.approx(rms(reference), rel=0.02)
