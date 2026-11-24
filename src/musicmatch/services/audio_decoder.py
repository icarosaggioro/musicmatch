"""Streaming PCM decoder used by the acoustic analysis pipeline (ADR 0014).

Design notes:
- FFmpeg is the primary backend. It already is a runtime requirement of the web ingestion
  pipeline (ADR 0010/0011) and decodes every format the scanner accepts (MP3, FLAC, M4A/AAC,
  OGG, Opus, WMA, AIFF, WAV). Audio is piped as 32-bit float WAV, so no temporary files are
  written and memory stays bounded: callers receive fixed-size chunks.
- Output is normalized to at most two channels (mono stays mono so BS.1770 loudness is not
  doubled; multichannel is downmixed to stereo) and to 44.1 kHz, which keeps analysis cost
  predictable regardless of the source sample rate.
- Without FFmpeg, the decoders bundled with the `miniaudio` wheel (dr_mp3, dr_flac,
  stb_vorbis, dr_wav — ADR 0015) still handle MP3, FLAC, Ogg Vorbis and WAV; as a last
  resort plain PCM WAV is decoded with the standard library. Fallback decoders keep the
  file's native sample rate and report any open failure as "unsupported" (they cannot tell
  a corrupt file from an unsupported variant), so FFmpeg can retry those files later.
- Cancellation is cooperative: a threading.Event is checked between chunks and kills the
  FFmpeg child process immediately, which is what a future GUI "Cancel" button needs.
"""

import os
import shutil
import struct
import subprocess
import tempfile
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

import numpy as np

from musicmatch.config import settings

DEFAULT_SAMPLE_RATE = 44100
_CHUNK_SECONDS = 2.0
_WAVE_FORMAT_PCM = 0x0001
_WAVE_FORMAT_IEEE_FLOAT = 0x0003
_WAVE_FORMAT_EXTENSIBLE = 0xFFFE


class AudioDecodeError(RuntimeError):
    """The file could not be decoded (corrupt, truncated or not audio)."""


class DecoderUnavailableError(RuntimeError):
    """No installed backend can decode this format (e.g. MP3 without FFmpeg)."""


class DecodeCancelled(RuntimeError):
    """Decoding was interrupted through the cancellation event."""


@dataclass(frozen=True)
class PcmFormat:
    sample_rate: int
    channels: int


def find_ffmpeg() -> Optional[str]:
    """Resolves the FFmpeg executable: MUSICMATCH_FFMPEG_PATH override first, then PATH."""
    configured = (settings.FFMPEG_PATH or "").strip()
    if configured:
        return configured if Path(configured).is_file() else None
    return shutil.which("ffmpeg")


class PcmStream:
    """Iterable of float32 chunks shaped (frames, channels) with a known PcmFormat."""

    backend: str = "unknown"

    def __init__(self, fmt: PcmFormat) -> None:
        self.format = fmt

    def chunks(self) -> Iterator[np.ndarray]:  # pragma: no cover - interface
        raise NotImplementedError

    def close(self) -> None:
        pass

    def __enter__(self) -> "PcmStream":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _parse_wav_header(read) -> PcmFormat:
    """Parses a RIFF/WAVE header from a byte reader until the 'data' chunk; expects float32."""
    riff = read(12)
    if len(riff) < 12 or riff[:4] != b"RIFF" or riff[8:12] != b"WAVE":
        raise AudioDecodeError("decoder produced no audio stream")
    fmt: Optional[PcmFormat] = None
    while True:
        header = read(8)
        if len(header) < 8:
            raise AudioDecodeError("decoder produced a truncated audio header")
        chunk_id, size = header[:4], struct.unpack("<I", header[4:])[0]
        if chunk_id == b"data":
            if fmt is None:
                raise AudioDecodeError("audio header has no format chunk")
            return fmt
        body = read(size + (size & 1))
        if chunk_id == b"fmt ":
            tag, channels, rate = struct.unpack("<HHI", body[:8])
            bits = struct.unpack("<H", body[14:16])[0]
            if tag == _WAVE_FORMAT_EXTENSIBLE and len(body) >= 26:
                tag = struct.unpack("<H", body[24:26])[0]
            if tag != _WAVE_FORMAT_IEEE_FLOAT or bits != 32 or channels < 1 or rate < 1:
                raise AudioDecodeError(f"unexpected decoder output (format={tag}, bits={bits})")
            fmt = PcmFormat(sample_rate=rate, channels=channels)


class FfmpegPcmStream(PcmStream):
    backend = "ffmpeg"

    def __init__(
        self,
        ffmpeg_path: str,
        file_path: str,
        sample_rate: int,
        cancel_event: Optional[threading.Event],
        timeout_seconds: Optional[float],
        start_seconds: float = 0.0,
    ) -> None:
        self._cancel = cancel_event
        self._timeout_seconds = timeout_seconds
        self._timed_out = False
        self._stderr = tempfile.TemporaryFile()
        # Input-side seek (-ss before -i): FFmpeg jumps close to the target and decodes
        # accurately from there, so resuming a long track does not decode its beginning.
        seek = ["-ss", f"{start_seconds:.3f}"] if start_seconds > 0 else []
        command = [
            ffmpeg_path, "-nostdin", "-hide_banner", "-loglevel", "error", *seek,
            # 'file:' pins the local-file protocol: a path containing ':' is never parsed
            # as a network/other protocol URL.
            "-i", f"file:{file_path}",
            "-map", "0:a:0", "-vn", "-sn", "-dn",
            "-af", "aformat=sample_fmts=flt:channel_layouts=mono|stereo",
            "-ar", str(sample_rate),
            "-c:a", "pcm_f32le", "-f", "wav", "-bitexact", "-",
        ]
        # The decoder runs in its own process group/session: a terminal Ctrl+C must reach only
        # MusicMatch (which cancels cooperatively), never FFmpeg directly. Otherwise FFmpeg
        # would exit early and a truncated decode could be mistaken for the whole track.
        popen_kwargs = {}
        if os.name == "nt":
            popen_kwargs["creationflags"] = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
        else:
            popen_kwargs["start_new_session"] = True
        try:
            self._proc = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=self._stderr,
                **popen_kwargs,
            )
        except OSError as exc:
            self._stderr.close()
            raise DecoderUnavailableError(f"could not start FFmpeg: {exc}") from exc
        # Watchdog: a hung decoder must never freeze a batch run. Real-time consumers (the
        # player paces decoding at playback speed) pass timeout_seconds=None to disable it.
        self._watchdog: Optional[threading.Timer] = None
        if timeout_seconds is not None:
            self._watchdog = threading.Timer(timeout_seconds, self._on_timeout)
            self._watchdog.daemon = True
            self._watchdog.start()
        try:
            fmt = _parse_wav_header(self._proc.stdout.read)
        except AudioDecodeError as exc:
            message = self._failure_message(str(exc))
            self.close()
            raise AudioDecodeError(message) from exc
        super().__init__(fmt)

    def _failure_message(self, fallback: str) -> str:
        if self._timed_out:
            return f"decoding timed out after {self._timeout_seconds:g}s"
        try:
            self._proc.wait(timeout=5)  # let FFmpeg flush its diagnostics to stderr
        except subprocess.TimeoutExpired:
            pass
        return self._error_text() or fallback

    def _on_timeout(self) -> None:
        self._timed_out = True
        self._kill()

    def _kill(self) -> None:
        if self._proc.poll() is None:
            self._proc.kill()

    def _error_text(self) -> str:
        try:
            self._stderr.seek(0)
            text = self._stderr.read().decode("utf-8", errors="replace").strip()
        except (OSError, ValueError):
            return ""
        lines = [line for line in text.splitlines() if line.strip()]
        return lines[-1][:300] if lines else ""

    def chunks(self) -> Iterator[np.ndarray]:
        channels = self.format.channels
        frame_bytes = 4 * channels
        chunk_bytes = int(self.format.sample_rate * _CHUNK_SECONDS) * frame_bytes
        leftover = b""
        while True:
            if self._cancel is not None and self._cancel.is_set():
                self._kill()
                raise DecodeCancelled("decoding cancelled")
            data = self._proc.stdout.read(chunk_bytes)
            if not data:
                break
            data = leftover + data
            usable = len(data) - (len(data) % frame_bytes)
            leftover = data[usable:]
            if usable:
                yield np.frombuffer(data[:usable], dtype="<f4").reshape(-1, channels)
        return_code = self._proc.wait()
        if self._cancel is not None and self._cancel.is_set():
            raise DecodeCancelled("decoding cancelled")
        if self._timed_out or return_code != 0:
            # Never accept output of a decoder that died: it may be a truncated stream.
            raise AudioDecodeError(self._failure_message(f"FFmpeg exited with code {return_code}"))

    def close(self) -> None:
        if self._watchdog is not None:
            self._watchdog.cancel()
        self._kill()
        try:
            if self._proc.stdout:
                self._proc.stdout.close()
            self._proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        self._stderr.close()


MINIAUDIO_EXTENSIONS = frozenset({".mp3", ".flac", ".ogg", ".wav"})


def _load_miniaudio():
    try:
        import miniaudio  # noqa: WPS433 - optional native wheel, imported lazily
    except ImportError:  # pragma: no cover - depends on the platform wheel
        return None
    return miniaudio


class MiniaudioPcmStream(PcmStream):
    """FFmpeg-free decoding of MP3/FLAC/Ogg Vorbis/WAV through the miniaudio wheel."""

    backend = "miniaudio"

    def __init__(
        self,
        miniaudio_module,
        file_path: str,
        cancel_event: Optional[threading.Event],
        start_seconds: float = 0.0,
    ) -> None:
        self._cancel = cancel_event
        ma = miniaudio_module
        try:
            info = ma.get_file_info(file_path)
        except ma.DecodeError as exc:
            raise DecoderUnavailableError(f"cannot decode without FFmpeg ({exc})") from exc
        channels = 1 if info.nchannels == 1 else 2  # multichannel is downmixed to stereo
        super().__init__(PcmFormat(int(info.sample_rate), channels))
        self._generator = ma.stream_file(
            file_path,
            output_format=ma.SampleFormat.FLOAT32,
            nchannels=channels,
            sample_rate=int(info.sample_rate),
            frames_to_read=int(info.sample_rate * _CHUNK_SECONDS),
            seek_frame=min(int(start_seconds * info.sample_rate), max(0, int(info.num_frames) - 1)),
        )
        self._decode_error = ma.DecodeError

    def chunks(self) -> Iterator[np.ndarray]:
        channels = self.format.channels
        try:
            for block in self._generator:
                if self._cancel is not None and self._cancel.is_set():
                    raise DecodeCancelled("decoding cancelled")
                data = np.frombuffer(block, dtype=np.float32)
                usable = data.size - (data.size % channels)
                if usable:
                    yield data[:usable].reshape(-1, channels)
        except self._decode_error as exc:
            raise AudioDecodeError(str(exc)) from exc

    def close(self) -> None:
        self._generator.close()


class WavePcmStream(PcmStream):
    """Standard-library fallback for integer PCM WAV files (8/16/24/32-bit)."""

    backend = "wave"

    def __init__(self, file_path: str, cancel_event: Optional[threading.Event], start_seconds: float = 0.0) -> None:
        self._cancel = cancel_event
        try:
            self._wav = wave.open(file_path, "rb")
        except OSError as exc:
            raise AudioDecodeError(str(exc)) from exc
        except Exception as exc:  # wave.Error, EOFError, or RuntimeError on malformed chunks
            raise DecoderUnavailableError(
                f"unsupported WAV encoding without FFmpeg ({type(exc).__name__}: {exc})"
            ) from exc
        self._width = self._wav.getsampwidth()
        if self._width not in (1, 2, 3, 4):
            self._wav.close()
            raise DecoderUnavailableError(f"unsupported WAV sample width: {self._width} bytes")
        super().__init__(PcmFormat(self._wav.getframerate(), self._wav.getnchannels()))
        if start_seconds > 0:
            self._wav.setpos(min(int(start_seconds * self._wav.getframerate()), self._wav.getnframes()))

    def _to_float(self, raw: bytes) -> np.ndarray:
        width = self._width
        if width == 1:
            data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        elif width == 2:
            data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        elif width == 3:
            b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
            ints = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
            ints = np.where(ints & 0x800000, ints - 0x1000000, ints)
            data = ints.astype(np.float32) / 8388608.0
        else:
            data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
        return data.reshape(-1, self.format.channels)

    def chunks(self) -> Iterator[np.ndarray]:
        frames_per_chunk = int(self.format.sample_rate * _CHUNK_SECONDS)
        while True:
            if self._cancel is not None and self._cancel.is_set():
                raise DecodeCancelled("decoding cancelled")
            raw = self._wav.readframes(frames_per_chunk)
            if not raw:
                return
            usable = len(raw) - (len(raw) % (self._width * self.format.channels))
            if usable:
                yield self._to_float(raw[:usable])

    def close(self) -> None:
        self._wav.close()


class AudioDecoder:
    """Opens audio files as PCM streams, preferring FFmpeg and falling back to stdlib WAV."""

    _AUTO = object()

    def __init__(
        self,
        ffmpeg_path=_AUTO,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        timeout_seconds: Optional[float] = 600.0,
        use_miniaudio: bool = True,
    ) -> None:
        """ffmpeg_path: explicit executable, None to disable FFmpeg, or omitted for auto-discovery.

        timeout_seconds=None disables the watchdog (real-time playback); use_miniaudio=False
        restricts the FFmpeg-free fallback to standard-library WAV decoding.
        """
        self.ffmpeg_path: Optional[str] = find_ffmpeg() if ffmpeg_path is AudioDecoder._AUTO else ffmpeg_path
        self.sample_rate = sample_rate
        self.timeout_seconds = timeout_seconds
        self._miniaudio = _load_miniaudio() if use_miniaudio else None

    @property
    def backend_name(self) -> str:
        if self.ffmpeg_path:
            return "ffmpeg"
        if self._miniaudio is not None:
            return "miniaudio (FFmpeg não encontrado: MP3/FLAC/OGG/WAV)"
        return "wave (FFmpeg não encontrado: apenas WAV)"

    def supported_extensions(self) -> Optional[frozenset]:
        """File extensions this decoder can open, or None when every format is supported (FFmpeg)."""
        if self.ffmpeg_path:
            return None
        return MINIAUDIO_EXTENSIONS if self._miniaudio is not None else frozenset({".wav"})

    def can_decode(self, file_path: str) -> bool:
        supported = self.supported_extensions()
        return supported is None or Path(file_path).suffix.lower() in supported

    def open(
        self,
        file_path: str,
        cancel_event: Optional[threading.Event] = None,
        start_seconds: float = 0.0,
    ) -> PcmStream:
        """Opens a PCM stream, optionally starting `start_seconds` into the file (resume)."""
        if not os.path.isfile(file_path):
            raise AudioDecodeError(f"file not found: {file_path}")
        start_seconds = max(0.0, float(start_seconds))
        if self.ffmpeg_path:
            return FfmpegPcmStream(
                self.ffmpeg_path, file_path, self.sample_rate, cancel_event, self.timeout_seconds, start_seconds
            )
        suffix = Path(file_path).suffix.lower()
        if self._miniaudio is not None and suffix in MINIAUDIO_EXTENSIONS:
            return MiniaudioPcmStream(self._miniaudio, file_path, cancel_event, start_seconds)
        if suffix == ".wav":
            return WavePcmStream(file_path, cancel_event, start_seconds)
        supported = ", ".join(sorted(ext.lstrip(".").upper() for ext in self.supported_extensions() or ()))
        raise DecoderUnavailableError(
            f"FFmpeg não encontrado: sem ele apenas {supported} podem ser decodificados. "
            "Instale o FFmpeg (ou defina MUSICMATCH_FFMPEG_PATH) para os demais formatos."
        )
