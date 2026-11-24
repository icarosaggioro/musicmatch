# 0016. Persistent Play Queue with Cursor, Pause/Stop Semantics, and Play Counting

## Context
[ADR 0015](0015-cross-platform-audio-playback-engine-and-play-queue.md) delivered playback with an in-memory queue that consumed entries as they played. The follow-up requirements were:
1. The **same track may be queued several times**.
2. The queue is **persistent**, and the user can **retrieve it and continue where they left off**.
3. **Tracks already played remain in the queue**; cleaning the queue is the user's decision.
4. **`/pause`** keeps the position (also across restarts). **`/stop`** resets to the **start of the queue**.
5. **Play counting**: once playback of a track reaches **60 seconds**, both the track's counter and the total counter increase. ("Nobody listens to more than that if not interested.")
6. Since the queue is expected to be non-empty most of the time, every start shows a **clean, one-line queue status**: queued tracks, last played track, position.

Constraints carried over:
- The player writes from background threads (auto-advance, periodic saves), while the catalog repository's SQLite connection belongs to the REPL thread.
- Counters must survive rescans, relocations and reorganizations ([ADR 0009](0009-library-idempotency-stat-cache-and-lifecycle-policy.md)).
- Counting must reflect **listening**: queueing, skipping or pausing must not inflate it.

## Decision

### 1. The queue is a persistent list with a cursor
> *Amended by [ADR 0017](0017-queue-playback-modes-repeat-consume-shuffle-and-sort.md)*: with repeat mode on, the end of the queue wraps to the first entry instead of stopping; with consume mode on, played entries leave the queue (keeping them stays the default); `/queue-shuffle` and `/queue-sort` reorder the whole queue; `/play queue` became `/queue-play`; `player_session` gained `repeat_mode` and `consume_mode`.

The queue is an ordered list of entries, and duplicates are allowed. **Playing never removes entries**; only `/queue-remove` and `/queue-clear` do. Two indices describe progress:
- `current_index`: the entry playing or paused. It is `None` for a track played by ID outside the queue.
- `next_index` (the **cursor**): the entry that plays next.

| Action | Effect |
| :--- | :--- |
| A queue entry ends, or `/next` | Play the entry at the cursor and move the cursor forward. Missing/undecodable entries are reported, skipped, and **kept**. |
| The last entry ends | `QUEUE_ENDED`: the cursor returns to the first entry and the player stops. |
| `/queue-add <id>` | Inserts **at the cursor**: plays right after the current entry. |
| `/queue-add-last <id>` | Appends. |
| `/queue-remove <id>` / `#<pos>` | Removes every copy / one entry. The cursor and current index shift so the playback order is unaffected. Removing the playing entry lets it finish outside the queue. |
| `/play <id>` | Plays the track now, from its beginning. If the queue was in progress, it continues with the next entry afterwards. From an idle player only that track plays, so a permanently filled queue does not start by surprise. |

`/queue` marks the current entry (▶ playing, ⏸ paused) and entries already played in the current pass (✓), and shows each track's play count.

### 2. Pause keeps the position; stop resets to the start
- **`/pause`** fades the output to silence (no click), releases the audio device and decoder, and keeps a **resume point**: the track, its position, the seconds already heard, and whether this play-through was counted. `/pause` again, or `/play`, continues it **from the same sample**, in the same session or after restarting MusicMatch. This is exactly what `/stop` did before this decision.
- **`/stop`** fades out, discards the resume point and **resets the cursor to the first entry**. The queue is kept.
- **Leaving the application** (`/exit`, Ctrl+C, closing the terminal) while a track plays is treated as a pause. While playing, the session is autosaved as "paused at the current position" every 5 s, so even a crash resumes there.
- Decoders seek to the saved position: FFmpeg input seek `-ss`, miniaudio `seek_frame`, and `wave.setpos`, all verified sample-accurate.

### 3. Persistence model
A single `apply_schema()` shared by every connection creates and migrates:

| Table | Content | Lifecycle |
| :--- | :--- | :--- |
| `play_queue(position, track_id)` | Ordered entries, duplicates allowed. | `ON UPDATE CASCADE` follows relocations; `ON DELETE CASCADE` drops entries of unindexed tracks. |
| `player_session` (single row) | Last played track, `position_seconds`, `listened_seconds`, `play_counted`, `volume`, `state` (`PAUSED` = resume point, `STOPPED` = start of queue), `queue_cursor`, `current_entry`. | `ON DELETE SET NULL` when the track is unindexed. |
| `playback_stats(key, value)` | `total_plays`. | Survives unindexing and `/library clear`. |
| `play_history(track_id, played_at, listened_seconds)` | One row per counted play: raw material for learning listening habits. | `ON DELETE SET NULL`. |
| `tracks.play_count`, `tracks.last_played_at` | Per-track counter. | Projected on the catalog for `/search`, `/queue` and the agent. |

`SQLitePlaybackStore` opens its own connection to the catalog database (`check_same_thread=False`, serialized by a lock); SQLite WAL mode arbitrates between connections. The queue is rewritten on every change (queues are short). The session row is saved on every transport/queue change and autosaved while playing.

**Rescans must not reset counters**: the scanner's `INSERT OR REPLACE` deleted and re-inserted rows. That would have reset `play_count` and cascade-deleted queue entries whenever a modified file was rescanned. `insert_batch` now upserts (`ON CONFLICT(id) DO UPDATE`), leaving the play statistics untouched, and explicitly drops acoustic analysis whose stamp no longer matches the file (preserving ADR 0014). `update_track` never writes the counters, so a stale `Track` snapshot cannot overwrite an increment.

### 4. Play-count rule: 60 seconds of listening
A play counts once the user has **actually heard 60 s** of the track (`MUSICMATCH_PLAY_COUNT_SECONDS`).
- **Listened time, not position**: time paused does not count, and the heard time accumulates across `/pause` and application restarts (persisted with the resume point).
- **Short tracks** (under 60 s) count when heard to the end. At the natural end of a file, the real decoded length is used, so a wrong or missing duration tag cannot prevent or fake a count.
- **Once per play-through**: a persisted `play_counted` flag prevents double counting when a paused, already-counted track is continued. Each queued copy of a duplicated track, and each pass through the queue, is a new play-through.
- **Skipping early** (`/next`, `/stop`, `/play <id>`) before 60 s does not count.
- The threshold is checked by a 1 s ticker thread (the audio callback must never do I/O), and again whenever a session ends. `record_play` updates the track counter, the total and the history **in one transaction**. The resulting `PLAY_COUNTED` event is not printed by the console, so it doesn't interrupt typing after every song; the counts appear in `/queue`, `/search` and `/status`.

### 5. Startup notice
At every start the harness reads the saved rows, without starting the audio engine, and prints one line in the interface language:

```
🎧 Fila: 12 faixa(s) · Última tocada: Band C - Long Road · Tempo: 01:23
```

`Tempo` is the paused position, or `00:00` after `/stop`. Nothing is printed when there is no queue and no last track.

### 6. Failure policy
Persistence is best-effort from the listener's point of view. A failed save emits one `PERSISTENCE_ERROR` per failing operation (queue, session, counter); identical repeats are not re-reported, and playback continues. An unavailable store lets the player start without persistence.

## Consequences
- The queue behaves like a playlist the user curates: it survives restarts, keeps played tracks and repeats, and resumes at the exact second after a pause or a closed terminal.
- Play counts measure real interest (60 s heard), survive rescans, relocations and reorganizations, and play history accumulates for future preference learning.
- Pausing releases the device, so resuming takes a device reopen plus a seek (tens of milliseconds), in exchange for identical behaviour within a session and across restarts.
- Minor latent fix: a full-text index created over pre-existing rows (very old databases) is now rebuilt before use. Previously the first update trigger could corrupt it.

### Known limitations
- One queue/session (no named queues or user profiles). Entries store track IDs: a track that is unindexed silently leaves the persisted queue, which may shift the saved cursor by the number of removed entries before it.
- Counts are recorded at ±1 s precision (ticker interval), and only while MusicMatch plays the file.
- A crash can lose up to 5 s of position (autosave interval).
