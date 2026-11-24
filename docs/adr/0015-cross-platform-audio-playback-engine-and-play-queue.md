# 0015. Cross-Platform Audio Playback Engine, Output Library Selection, and Play Queue

## Context
Feature Front 3 of the roadmap ([ROADMAP](../ROADMAP.md)) asks MusicMatch to play the music it catalogs, instead of depending on external players:
1. Playback on **Windows, macOS (Apple) and Linux**.
2. Transport commands `/play <id | queue>`, `/pause`, `/stop`, `/next`, `/volume <0-100>`.
3. Queue commands `/queue-add <id>`, `/queue-add-last <id>`, `/queue-remove <id>`, `/queue-clear`.
4. **Missing tracks must be notified** to the user.

Constraints from earlier decisions:
- **Formats**: every format the scanner indexes (MP3, FLAC, M4A/AAC, OGG, Opus, WAV, WMA, AIFF), preserved natively by web ingestion ([ADR 0011](0011-web-ingestion-two-stage-staging-and-managed-library-taxonomy.md)).
- **Install story**: `pip install -e .` on Python ≥ 3.14.6. FFmpeg is already an optional system tool ([ADR 0010](0010-yt-dlp-integration-and-packaging-strategy.md), [ADR 0014](0014-acoustic-analysis-pipeline-and-fingerprint-deduplication.md)). Requiring an additional desktop application (VLC, mpv) or compiler is undesirable.
- **Non-blocking harness**: the REPL must stay responsive while music plays. Ctrl+C must leave no orphan processes.
- **GUI later**: state and notifications must be consumable by a future graphical interface.
- **Testable without sound hardware** (CI, headless servers).

## Library research
**Method.** The development environment had no general web search; network access was limited to the Python Package Index. The evaluation therefore combined:
- The PyPI JSON API, queried on 2026-11-16: latest release and date, wheel matrix (which OS/CPU/CPython versions install without compiling), licence, and declared dependencies.
- Hands-on probing: installing candidates into a Python 3.14 environment, reading their source, and running them on a headless Linux machine.

Documentation sites (python-sounddevice.readthedocs.io, github.com) were unreachable and are **not** a source for the facts below. Claims about platform audio APIs come from the libraries' source code and the project's prior knowledge of them.

| Library | Latest release | Installs on Python 3.14 via wheel | Native requirements | Decodes by itself | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **miniaudio** (pyminiaudio) | 1.71 (2026-04-29) | cp314: Windows x86/x64, macOS x86_64 + arm64, Linux x86_64 (glibc + musl) | None. WASAPI/DirectSound/WinMM, Core Audio, PulseAudio/ALSA/JACK are compiled in and loaded at run time | MP3, FLAC, Vorbis, WAV | **Chosen** |
| sounddevice (PortAudio) | 0.5.6 (2026-08-17) | py3-none: bundles PortAudio on Windows/macOS | Linux: system `libportaudio2` (could not be installed here without root; no PyPI wheel provides it) | None (raw PCM) | Runner-up; fits behind the same `AudioOutput` interface |
| python-vlc | 3.0.21203 (2024-10-07) | Pure Python | A full VLC installation with matching bitness | All | Rejected: external application per machine |
| python-mpv | 1.0.8 (2025-04-25) | Pure Python | libmpv shared library installed manually; GPL/LGPL | All | Rejected: manual native install on Windows/macOS |
| pygame-ce | 2.5.8 (2026-08-09) | cp314 on all platforms | Bundled SDL2 | MP3, OGG, FLAC, Opus, WAV (no AAC/M4A/WMA) | Rejected: formats; game framework; single music channel |
| pygame | 2.6.1 (2024-09-29) | No cp314 wheel | Bundled SDL2 | As above | Rejected |
| just-playback | 1.0.0 (2026-09-19) | cp314 on all platforms | Bundled miniaudio | MP3, FLAC, OGG, WAV; file-based only | Rejected: cannot play M4A/Opus/WMA or be fed decoded PCM |
| soundcard | 0.4.6 (2026-04-12) | Pure Python | Linux requires PulseAudio (no plain ALSA) | None | Rejected: ALSA-only Linux unsupported; blocking API |
| pyglet | 2.1.19 (2026-10-11) | Pure Python | FFmpeg shared libraries for compressed formats | Via FFmpeg libs | Rejected: windowing/game framework |
| PyAudio | 0.2.14 (2023-11-07) | Windows wheels only | PortAudio build toolchain on macOS/Linux | None | Rejected |
| simpleaudio | 1.0.4 (2019-11-29) | No cp314 wheel | — | WAV only | Rejected: unmaintained |
| playsound | 1.3.0 (2021-07-24) | sdist only | — | Blocking, no controls | Rejected |

**Probes** (headless Linux VM, no sound card):
- Default device selection fails cleanly with `MiniaudioError('failed to init device', -401)`, which is the "no audio device" path users on servers/WSL will hit.
- The miniaudio **NULL backend** consumes audio at real-time pace (90,405 frames in 2.01 s at 44.1 kHz). This makes realistic end-to-end tests possible without hardware.
- Real **ALSA** output was captured through libasound's `file` plugin. A 523 Hz tone played at volume 50 arrived intact: 1.0 s of audio, 523.8 Hz, −24.1 dBFS (−6 dB source, −18 dB from the volume taper).
- libasound prints dozens of `ALSA lib … cannot find card` lines to stderr while probing on machines without a sound card. The player installs a silent libasound error handler and reports one clear error instead.

**Why miniaudio**: it is the only candidate that installs from a wheel on all three platforms with **no system package, application or compiler**, talks to each OS's native audio API, and can be fed arbitrary PCM. It can therefore play every format through the FFmpeg pipeline MusicMatch already has. As a bonus, its bundled decoders let MusicMatch play (and analyse) MP3/FLAC/Vorbis/WAV even when FFmpeg is not installed. sounddevice is equally capable on Windows/macOS; on Linux it needs a distribution package. It remains the documented fallback behind the `AudioOutput` interface if a future platform lacks miniaudio wheels.

**Risks accepted**: miniaudio wheels are CPython-version specific, so each new Python release needs a new miniaudio release (cp314 wheels exist). There is no cp314 wheel for Linux aarch64 (Raspberry Pi) or Windows on ARM64; there, pip builds it from source, which requires a C compiler. The project has a single maintainer.

## Decision

### 1. Decoding and output are separate
```
  AudioDecoder (ADR 0014)                    _Session (per track)                   AudioOutput
  FFmpeg (all formats)      ──PCM chunks──>  decoder thread → bounded buffer  ──>  MiniaudioOutput
  miniaudio decoders (no FFmpeg:             (~4 s) → pull(): volume ramp,         (WASAPI · Core Audio ·
   MP3/FLAC/OGG/WAV)                         pause, underrun padding, EOF           PulseAudio/ALSA/JACK · NULL)
  stdlib wave (last resort)
```
- Playback reuses the analysis decoder, so whatever `/analyze` can read, `/play` can play. The FFmpeg watchdog is disabled for playback (`timeout_seconds=None`), because decoding is paced in real time. FFmpeg still runs in its own process group, so a terminal Ctrl+C never kills it behind the player's back.
- The FFmpeg-free decoder chain is extended with miniaudio's decoders. Without FFmpeg, both `/play` and `/analyze` now handle MP3/FLAC/OGG/WAV; previously only WAV. Fallback decoders keep the file's native sample rate, and miniaudio converts to the device format.
- `MUSICMATCH_AUDIO_BACKEND` forces a backend (`wasapi`, `dsound`, `winmm`, `coreaudio`, `pulseaudio`, `alsa`, `jack`, `null`); empty means automatic.

### 2. Real-time engine rules
- The device callback (`_Session.pull`) never blocks on I/O and never raises. It copies from the buffer, pads underruns with silence, and applies a **per-block gain ramp**, so pause, resume, stop and volume changes are click-free. While paused it outputs silence without consuming audio, so the position holds.
- The device cannot report the end of a track, so the engine detects it when the decoder is done and the buffer is drained. The next track is started on a short-lived helper thread, since a device cannot be closed from inside its own callback. A late end signal from a replaced session is ignored.
- **Volume** 0–100 uses a cubic taper (amplitude = (v/100)³, the mapping PulseAudio uses for software volume): 50 → −18 dB, 0 → mute. The default is 80.

### 3. Commands and queue semantics
> *Amended by [ADR 0016](0016-persistent-play-queue-resume-and-play-counting.md)*: the queue is now persistent and keeps played entries (a cursor tracks progress); `/pause` keeps the position across restarts; `/stop` resets to the first queue entry; `/queue-add` inserts at the cursor; `/queue-remove #<pos>` removes a single entry. The table below is the original ADR 0015 behaviour.

| Command | Behaviour |
| :--- | :--- |
| `/play <id>` | Plays the track now; the queue is kept. |
| `/play queue` | Plays the queue from its first entry. `/play` without arguments resumes a paused track or starts the queue. |
| `/pause` | Toggles pause/resume. |
| `/stop` | Stops; the queue is kept. |
| `/next` | Skips to the next queued track; reaching the end stops with an "end of queue" notice. |
| `/volume [0-100]` | Sets the volume, or shows it when no value is given. |
| `/queue-add <id>` | Inserts the track to play **next** (after the current one). |
| `/queue-add-last <id>` | Appends to the **end** of the queue. |
| `/queue-remove <id>` | Removes every queued occurrence of the track (matched against the queue, so it works even if the track left the catalog). |
| `/queue-clear` | Empties the queue (the current track keeps playing). |
| `/queue` | Shows state, position bar, volume, output API and upcoming tracks. Not required, but needed to inspect the queue. |

Track IDs are 68 characters long, so every command accepts any **unique prefix** of at least 4 hex digits, with or without `trk_`. The lookup is a primary-key range scan. `/list` and `/search` now show the short form (`ID: trk_3fa2b9c1`).

> *Amended by issue #9*: `/play` also takes a search text. An ID or a search with a single match (or a single exact title) plays; otherwise the candidates are listed and nothing plays. Words in the text are always literal, never FTS5 operators. `/resume` continues a paused track, `/status` shows the playback state without starting the engine, and the agent has a `play_track` tool with the same lookup rules.

### 4. Missing tracks
A track is playable only if its status is not `MISSING` **and** its file exists at play time. The check covers:
- `/play <id>`: a notice is shown and the current track keeps playing.
- `/queue-add*`: the track is refused with a notice.
- `/queue`: unavailable entries are flagged ⚠️.
- Auto-advance and `/next`: the entry is skipped with a notice.

The notice names the file path and suggests reconnecting the drive or running `/scan`. Undecodable files (`TRACK_ERROR`) are likewise reported and skipped. A missing audio device (`DEVICE_ERROR`) stops playback and puts the track back at the head of the queue, because it is not the track's fault.

The player **does not write to the catalog**. It works on `Track` snapshots, so SQLite is never touched from playback threads, and `/scan` remains the single authority for `MISSING` states (ADR 0009).

### 5. GUI-ready contract
`PlayerService` is thread-safe. It publishes typed `PlayerEvent`s (`TRACK_STARTED`, `TRACK_MISSING`, `TRACK_ERROR`, `DEVICE_ERROR`, `QUEUE_ENDED`, …) to listeners, with a `background` flag for events raised by auto-advance. `status()` returns a `PlayerStatus` snapshot. All are Pydantic models. Events are emitted outside the player lock, so listeners may call back into the player. The console listener redraws the `MusicMatch >` prompt after background notifications. The player is created lazily on first use and shut down by the harness on `/exit` or Ctrl+C, and at interpreter exit.

## Consequences
- Music plays on Windows, macOS and Linux from a plain `pip install`. Installing FFmpeg extends it from MP3/FLAC/OGG/WAV to every indexed format.
- The REPL stays interactive during playback, and Ctrl+C or `/exit` release the device and decoder (verified: no orphan FFmpeg processes).
- The engine is tested end to end on the samples themselves: a fake device records what the engine outputs, and miniaudio's NULL backend runs the real device stack in real time.

### Known limitations
- Not gapless: each track opens its own device, which adds a short gap (tens of milliseconds). No crossfade or seek yet.
- Loudness normalization is not applied yet, even though ADR 0014 measures integrated LUFS per track. A ReplayGain-style gain (e.g. towards −14 LUFS, capped by the sample peak) is a natural next step.
- The queue and volume live in memory and are not persisted across sessions. *(Superseded by [ADR 0016](0016-persistent-play-queue-resume-and-play-counting.md): queue, cursor, paused position, volume and play counters are now persistent.)*
- macOS was not exercised in this environment. Support relies on miniaudio's Core Audio backend and its published universal macOS wheels.
- The player reports missing files but does not mark them `MISSING`; run `/scan` to reconcile the catalog.
