# 0014. Acoustic Analysis Pipeline, Real Signal Metrics, and Fingerprint-Based Duplicate Detection

## Context
Feature Front 2 of the roadmap ([ROADMAP](../ROADMAP.md)) replaces provisional audio metrics with measurements taken from the signal itself:
- `Track.bpm` holds the ID3 tag value or a hard-coded `120.0` placeholder; `Track.lufs` is always `None`; the musical key is not known at all.
- `/audit duplicates` ([ADR 0013](0013-library-maintenance-consolidation-and-deletion-safeguards.md)) groups tracks by normalized `artist:title`. It misses the most common duplicate in real collections, the same recording under different tags or containers (a FLAC rip and a 128 kbps MP3 named "Track 01"). It can also flag live and studio versions that share a title.

The solution must respect constraints established by earlier decisions:
1. **Scans must stay fast.** [ADR 0009](0009-library-idempotency-stat-cache-and-lifecycle-policy.md) promises re-scans in milliseconds through the stat-cache. Decoding audio costs seconds per track, which for a 10,000–100,000 track library is hours of CPU.
2. **Non-destructive lifecycle.** Relocated files keep their acoustic analysis without re-running DSP (ADR 0009, Fast Relocation), and disconnected drives must never corrupt state.
3. **Future GUI and Rust engine.** Results must be consumable by a graphical interface (progress, cancellation, JSON), and algorithms must sit behind a seam the planned `musicmatch_core` (PyO3) engine can replace.

## Decision

### 1. Scan and analysis are separate steps
- `/scan` keeps reading only tags and `os.stat`. It now also reports how many tracks in the scanned folder still await analysis (`ScanResult.tracks_pending_analysis`).
- `/analyze [path] [--force] [--limit N] [--workers N]` is a separate, **incremental and resumable** pass. It selects its work with one SQL query over catalog stamps, with no filesystem access: tracks never analysed, modified since, or analysed by an older `ANALYSIS_VERSION`. Re-running it over an analysed library costs milliseconds.
- `/analyze status` reports coverage and decoder availability; `/analyze show <id>` renders every metric of one track.

### 2. One decode pass per file
Decoding dominates the cost (≈ 55–60% of analysis time in measurements), so `AudioAnalyzer` decodes each file exactly once and fans the PCM stream out:

```
FFmpeg/WAV PCM chunks ──┬─> LoudnessMeter        (whole track, streaming)
                        ├─> WaveformAccumulator  (whole track, streaming)
                        └─> mono excerpt (first 240 s) ─> 11025 Hz
                                ├─> fingerprint (first 120 s after leading silence)
                                ├─> tempo
                                └─> key
```

- **Decoder**: FFmpeg, already required by web ingestion ([ADR 0010](0010-yt-dlp-integration-and-packaging-strategy.md)), pipes 32-bit float WAV, so no temporary files are written. Output is normalized to 44.1 kHz and at most two channels. Mono stays mono so BS.1770 does not count it twice; multichannel is downmixed to stereo. Without FFmpeg, integer PCM WAV is still decoded with the standard library, and other formats are *skipped, not failed*, so they are picked up once FFmpeg is installed (`MUSICMATCH_FFMPEG_PATH` overrides discovery).
  > *Amended by [ADR 0015](0015-cross-platform-audio-playback-engine-and-play-queue.md)*: without FFmpeg, the decoders bundled with `miniaudio` now also handle MP3, FLAC and Ogg Vorbis, so only M4A/AAC, Opus, WMA and AIFF are skipped.
- **Bounded memory**: the loudness meter keeps 10 values per second, and the excerpt is capped. A two-hour DJ mix uses about as much memory as a three-minute single.
- **Decoder safety**: FFmpeg runs in its own process group or session, so a terminal Ctrl+C reaches only MusicMatch, which cancels cooperatively. A decoder that exits non-zero is never accepted, even after producing audio: a truncated stream must not be stored as the whole track. A watchdog kills hung decodes.

### 3. Layering
| Layer | Module | Rule |
| :--- | :--- | :--- |
| DSP | `musicmatch.dsp.{loudness,tempo,key,fingerprint,waveform}` | Pure NumPy/SciPy, no I/O: the seam for the Rust engine. |
| Decoding | `musicmatch.services.audio_decoder` | FFmpeg pipe / WAV fallback, cancellation, timeouts. |
| Use case (file) | `musicmatch.services.analyzer.AudioAnalyzer` | Stateless and thread-safe; never touches the database. |
| Use case (batch) | `musicmatch.services.analysis.AcousticAnalysisService` | Selection, worker pool, persistence, duplicates. |
| Domain | `musicmatch.domain.analysis`, `musicmatch.domain.music_keys` | Pydantic models; `model_dump(mode="json")` safe. |

The roadmap's `AudioDSPService` is split into these pieces.

### 4. Signal metrics
- **Loudness (EBU R128 / ITU-R BS.1770-4)**: integrated loudness with absolute (−70 LUFS) and relative (−10 LU) gating, Loudness Range (EBU Tech 3342), and sample peak. K-weighting coefficients are derived for any sample rate from the analog prototype (libebur128 parameters) and match the 48 kHz reference table. The meter is streaming: 400 ms blocks are the mean of four 100 ms steps, and 3 s short-term windows are the mean of thirty.
- **Tempo**: half-wave rectified spectral flux, then autocorrelation weighted by a log-normal prior (120 BPM, one octave). The period is refined with up to 16 of its multiples for sub-BPM precision. An impulsiveness gate (onset-envelope kurtosis ≥ 6) makes drones, pads and vibrato report *no* tempo instead of a confident artefact. The catalog `bpm` is only overwritten when confidence ≥ 0.2; otherwise the tag value stays.
- **Key**: 8192-sample spectra between 55 Hz and 2 kHz, tuning estimated from spectral peaks (A = 432 Hz reads as about −32 cents and is compensated), mildly compressed chroma, and correlation with the 24 Krumhansl–Kessler profiles. Keys are stored as names (`A minor`) and rendered with Camelot codes (`8A`) for harmonic mixing.
- **Waveform Summary** (see CONTEXT.md): up to 1,000 peak/RMS points stored as 8-bit blobs. It is nearly free during the decode pass and lets a future GUI draw overviews without decoding anything again.

### 5. Acoustic fingerprint `mmfp1`
The fingerprint is a time-smoothed variant of the Haitsma–Kalker robust hash:
1. Mono at 11025 Hz, with leading silence trimmed so copies with different lead-in padding align at offset zero. The first 120 s are used.
2. 4096-sample Hann frames every 256 samples, with energy in 33 log-spaced bands between 300 Hz and 3 kHz (a range every lossy codec keeps).
3. Log energies smoothed over 0.37 s and decimated to one 32-bit sub-fingerprint every ≈ 93 ms (≈ 5 KB per track).
4. Bit *m* is the sign of the change, over a 0.37 s lag, of the energy difference between bands *m* and *m+1*.

Fingerprints are compared by **bit error rate (BER)** at the best frame offset; `similarity = 1 − 2·BER`.

**Why not Chromaprint (`fpcalc`) for deduplication?** (Accepted by the project owner, amending issue #28.) It adds a second native binary on Windows and a second decode of every file. Fuzzy matching also needs raw integer fingerprints, which pyacoustid exposes only through `libchromaprint`. `pyacoustid` stays a dependency for a future AcoustID/MusicBrainz metadata lookup. Fingerprints are stored with an algorithm identifier, so the algorithm can be replaced (for example by the Rust engine) without ambiguity.

**Validation** on real recordings re-encoded with FFmpeg (FLAC, MP3 320/128/64 kbps at 22 kHz, AAC 96 kbps, Opus 48 kbps, Vorbis q2, mono, −6 dB plus a 37 ms shift, and 1.3 s of added silence): BER ≤ 0.09 in every case. Arbitrary sub-frame misalignments stayed ≤ 0.11. Different songs measured ≥ 0.47. Different passages of the same song measured ≥ 0.37, except a passage the track itself repeats bar-for-bar (0.30). The hardest synthetic negative is the same backing track with a different melody (≈ 0.30).

### 6. Duplicate detection
- **Exact** (`/audit duplicates --exact`, and the `/audit` dashboard): identical fingerprint SHA-256. This is one indexed `GROUP BY`, split where decoded durations are incompatible. It finds the same decoded audio under any tags or container.
- **Fuzzy** (`/audit duplicates --fuzzy`): the same recording across encodes and bitrates, matched at **BER ≤ 0.20**, roughly midway between the worst positive and the hardest negative. It scales without comparing every pair:
  1. Blocking: tracks are sorted by decoded duration and compared only within max(5 s, 3%).
  2. Prefilter: one vectorized XOR/popcount (`np.bitwise_count`) over a mid-track window at ±6 frames, per track, against all of its neighbours.
  3. Verification: full-overlap BER with a ±32-frame offset search.
  4. Union-find clustering. Each group reports its lowest pairwise similarity.
- Both strategies reuse the ADR 0013 quality heuristic: prefer the available file with the highest bitrate, so lossless masters are kept over lossy copies. The audio comes first: by default, analysed tracks are grouped by fingerprint and only tracks without one fall back to tags, so two recordings with equal tags but different audio (live and studio) are never grouped. `--tags` forces tag grouping (issue #28).

### 7. Storage and lifecycle
- A `track_analysis` table (one row per track) holds the measurements, fingerprint and waveform blobs, the `analysis_version`, and the **analysis stamp**: the catalog `file_mtime`/`file_size` the analysis describes. Blobs stay out of the hot `SELECT * FROM tracks` paths (`/list`, `/search`, stat-cache).
- Foreign key `ON DELETE CASCADE`: when the scanner re-persists a modified file (`INSERT OR REPLACE`), or a track is unindexed or deleted, the stale analysis disappears with it.
  > *Amended by [ADR 0016](0016-persistent-play-queue-resume-and-play-counting.md)*: re-persistence is now an upsert that keeps play counters and queue entries; `insert_batch` deletes the analysis whose stamp no longer matches the file explicitly, so the observable behaviour is unchanged.
- `ON UPDATE CASCADE`: Fast Relocation and `/library reorganize` rewrite `tracks.id`, and the analysis follows. `relocate_track` also rebases the stamp when the analysis was current, so moved files are not re-decoded (ADR 0009).
- Headline metrics are projected onto `tracks` (`lufs`, `musical_key`, and `bpm` when confident), so `/search`, BPM filters, FTS queries and the agent's `search_tracks` tool use real values without joins. Existing databases gain the `musical_key` column and the new table through the idempotent migration in `init_db`.
- Outcomes: `OK` and `ERROR` (undecodable or corrupt, including unexpected DSP exceptions) are persisted. `ERROR` is not retried until the file changes, the version is bumped, or `--force` is used. `SKIPPED` (file missing on disk, format unsupported without FFmpeg) is **never** persisted, so reconnecting a drive or installing FFmpeg resumes naturally.

### 8. Concurrency and GUI readiness
- A thread pool (default `min(4, CPU count)`, or `MUSICMATCH_ANALYSIS_WORKERS`) runs one FFmpeg process per worker, with at most two tasks in flight per worker. NumPy, SciPy and the decoder pipe release the GIL, and 4 workers were several times faster than 1 in measurements.
- Only the calling thread touches SQLite: results are persisted in transactions of 20 as they complete, so an interrupted run keeps its finished work.
- The service emits one typed `AnalysisProgress` event per track and honours a `threading.Event` for cancellation. A GUI worker thread calls the same API and marshals events to its UI thread. In the CLI, Ctrl+C is converted into a cancellation instead of exiting the REPL.
- Every result (`AnalysisRunResult`, `TrackAnalysis`, `AnalysisCoverage`, `AcousticDuplicateCluster`) is a Pydantic model. Raw fingerprint bytes are excluded from JSON.

## Consequences
- **Real metrics**: loudness matches FFmpeg's `ebur128` reference within 0.05 LU on real material. Tempo on steady material is exact to a few hundredths of a BPM. Key detection passes all 24 keys on tonal test material and is stable across codecs.
- **Duplicates by sound, not by name**: retagged, renamed, transcoded and re-ripped copies are grouped, and the best copy is recommended.
- **Scans stay fast**: `/scan` never decodes audio. Analysis is opt-in, incremental, parallel and resumable.
- **Schema migration**: columns and tables are added by the idempotent column list in `schema.apply_schema`; `PRAGMA user_version` was not adopted, since every change so far is additive.
- **Dependencies**: NumPy (≥ 2.0 for `bitwise_count`) and SciPy become runtime dependencies. FFmpeg is needed for non-WAV formats (already needed for downloads).

### Known limitations
- Multichannel audio is downmixed to stereo before measuring loudness, so BS.1770 surround weights are not applied to 5.1 sources. Peak is sample peak, not true peak.
- Tempo has the usual metrical-level ambiguity: a 150/174 BPM track whose kick marks every other beat may read as 75/87 BPM. librosa shows the same behaviour on the same material.
- Key profiles assume Western tonal music. Relative major/minor keys (same key signature) can be confused on weakly tonal material.
- The fingerprint covers the first 120 s, combined with a duration check. Two edits that share their first two minutes and differ in length by less than the duration tolerance would be grouped.
- Fuzzy matching costs O(N · k), where k is the number of tracks with a similar duration. That is fine for the targeted 10,000–100,000 tracks; an inverted index over sub-fingerprints is the next step beyond that.
- Any write to a file (including `/retag`) changes its stamp and schedules a re-analysis. This is safe by default at the cost of one extra decode.
