# 0017. Queue Playback Modes: Repeat, Consume, Shuffle and Sort, and the `/queue-<action>` Command Family

## Context
[ADR 0016](0016-persistent-play-queue-resume-and-play-counting.md) made the play queue a persistent list with a cursor whose played entries stay until the user removes them. The next step toward a complete playback experience (and, later, traditional playlists) asked for more ways to operate the queue:
1. **Repeat** the entire queue.
2. **Shuffle**.
3. **Order by** track name; genre, then track name; artist, then track name; album name, then track number.
4. Shuffle and order by act on the **whole queue**, also in the middle of playback.
5. The user decides whether a track that was **already played stays in the queue or is removed**.
6. **Naming rule**: every playback-queue command follows `/queue-<action>`.

Forces:
- `/queue` must keep showing the **real play order**; the ▶/✓ markers are derived from the cursor.
- `/queue-add` ("plays next") must keep its meaning whatever the queue's order.
- "Played" already has a precise definition in the project: the play-count rule of ADR 0016.

## Decision

### 1. Repeat and consume are persistent modes; shuffle and sort are operations on the list
- **Repeat** (`/queue-repeat [on|off]`) and **consume** (`/queue-consume [on|off]`) are player modes. With no argument the command toggles the mode. They are stored in `player_session.repeat_mode` / `consume_mode`, survive restarts, and show in `/queue` and the startup line (`· 🔁 Repetir fila`, `· 🧹 Remover tocadas`).
- **Shuffle** (`/queue-shuffle`) and **sort** (`/queue-sort <title|genre|artist|album>`) **physically reorder the queue entries**. They do not set a hidden "play order" mode. What `/queue` lists is exactly what will play, `/queue-add` still inserts at the cursor, and with repeat on the next pass replays the same order.

We rejected shuffle/sort as persistent modes, which would need a play-order permutation kept alongside the list. They would conflict with `/queue-add`, and would make `/queue` show one order while playing another.

### 2. Shuffle and sort reorder the whole queue; playback continues from an anchor entry
Every entry is reordered, including the ones already played in this pass. Entries are moved by index, so each copy of a duplicated track stays a distinct entry. Playback continues from the **anchor entry**:
- The current entry (playing or paused), or
- Mid-pass with no current entry (e.g. a track played by ID interrupted the queue), the entry due next, or
- No anchor when the queue is stopped or at its start (the cursor stays on the first entry).

| Operation | The anchor | Playback continues |
| :--- | :--- | :--- |
| `/queue-sort` | Stays where the sort puts it. | From the anchor's new position; entries sorted above it count as passed (✓) in this pass. |
| `/queue-shuffle` | Goes to **position 1**; every other entry is shuffled behind it. | Through the whole shuffled queue after the anchor. |

Sort follows the classic playlist-player behaviour (Winamp, foobar2000, iTunes): the list is sorted and the current track keeps its place in the new order. Shuffle has no "right" place for the current track, so putting it first (as streaming players do) means a fresh random pass in which every other entry plays. The `QUEUE_REORDERED` message states the position playback continues from.

### 3. Consume: a played track leaves the queue when playback moves on
With consume on, a queue entry is removed **when it counted as played** and **playback moves on from it**:

| Situation | Entry |
| :--- | :--- |
| The track plays to its end | Removed (a track heard to the end always counts). |
| `/next` or `/play <id>` after it counted (60 s heard, or the whole track when shorter; `MUSICMATCH_PLAY_COUNT_SECONDS`) | Removed. |
| `/next` or `/play <id>` before it counted | **Stays**: it was skipped, not heard. |
| `/pause`, `/stop`, leaving the application | **Stays**: playback did not move on (or you can resume it). |
| Unavailable or undecodable | **Stays**, as in ADR 0015/0016, so it plays once the drive is back. |

- **"Played" reuses the play-count rule of ADR 0016**, so the queue and the play counters agree on what "played" means. The entry is removed on moving on, not at the moment the threshold is passed, so the current track stays visible in `/queue` while it plays.
- **Only that entry is removed**: other copies of the same track stay, and the cursor shifts so the order is unaffected.
- **Turning consume on does not touch entries already in the queue**: switching a mode never deletes anything by itself. `/queue-remove` and `/queue-clear` remain the explicit tools.
- **Repeat and consume exclude each other**: a queue that empties as it plays has nothing to repeat. Turning one on turns the other off, and the confirmation says so. A restored session honours the same rule.
- The console does not print `QUEUE_ENTRY_CONSUMED` (like `PLAY_COUNTED`): the entry simply leaves `/queue` without interrupting typing after every song.

### 4. Sort keys
All sorts are **stable**: ties keep their current relative order. Text comparisons are **case- and accent-insensitive** (`Écho` sorts with `echo`). The scanner's missing-tag placeholders (`Unknown Artist`, `Unknown Album`, `Unknown Genre`) and empty values sort **after** every real value.

| `/queue-sort` | Key |
| :--- | :--- |
| `title` | Track name. |
| `genre` | Genre, then track name. |
| `artist` | Artist, then track name. |
| `album` | Album name, then **containing folder**, then track number (entries without a number last), then track name. |

The folder in the album key keeps **same-named albums apart**: two "Greatest Hits" by different artists would otherwise interleave as 1, 1, 2, 2, … A compilation shares one folder across artists, so it stays in track-number order, which grouping by artist would break. Portuguese key names are accepted too (`titulo`, `genero`, `artista`, `álbum`).

Shuffle uses a per-player `random.Random` (injectable for deterministic tests). It redraws, a bounded number of times, when the result equals the previous order, so the command visibly changes the queue whenever it can.

### 5. Repeat semantics
- When the last entry ends (or `/next` is used on it) with repeat on, the cursor wraps to the first entry and playback continues. A background `QUEUE_REPEATED` event tells the user. Each pass is a new play-through for play counting (ADR 0016).
- Unavailable or undecodable entries are still skipped with a notice. Each `_advance` call tries **each entry at most once**, so a repeating queue in which nothing can play (e.g. the drive was unplugged) stops with `QUEUE_ENDED` ("Nenhuma faixa da fila pôde ser reproduzida") instead of spinning forever.
- A track played by ID from an idle player stays outside the queue, and repeat does not apply to it.
- Turning repeat off during playback lets the current pass finish, then the queue stops as usual.

### 6. The `/queue-<action>` family
Every playback-queue command is named `/queue` or `/queue-<action>`:

`/queue`, `/queue-play`, `/queue-add`, `/queue-add-last`, `/queue-remove`, `/queue-clear`, `/queue-repeat`, `/queue-consume`, `/queue-shuffle`, `/queue-sort`.

`/play queue` was the one exception. It is replaced by **`/queue-play`**; `/play` is documented as `/play [id]`. `/play queue` (and `/play fila`) is still accepted but no longer advertised. The new commands get no aliases: a `/fila-…` alias would break the rule. `/queue` keeps its existing `/fila` alias. A test enforces the naming rule over the registry.

### 7. Events
New `PlayerEventKind`s keep the player UI-agnostic: `QUEUE_REORDERED`, `QUEUE_REPEATED`, `REPEAT_CHANGED`, `CONSUME_CHANGED` and `QUEUE_ENTRY_CONSUMED`. `PlayerStatus.repeat` / `.consume` expose the modes. The console now prints the message carried by `QUEUE_ENDED`, so the reason a repeating queue stopped is visible.

## Consequences
- The queue can be looped, shuffled and sorted as a whole, and `/queue` always matches the real play order.
- The user chooses the queue's character: a kept, curated list (default, ADR 0016) or a to-play list that empties as it is heard. Named playlists can later take the "curated" role while the queue works in consume mode.
- Existing databases gain `player_session.repeat_mode` and `consume_mode` (both off) through the usual idempotent migration.

### Known limitations
- After a mid-pass sort, entries that land above the current track count as passed (✓) and are not played in this pass. They play in the next pass with repeat, or after `/stop`.
- After a mid-pass shuffle, entries already played in this pass can play again in it: the shuffled queue is a fresh pass starting from the current track.
- Shuffle is one-shot: with repeat on, each pass replays the same shuffled order (run `/queue-shuffle` again to reshuffle).
- There is no disc number in the catalog, so the tracks of a multi-disc album stored in one folder interleave by track number in `album` order.
- Sorting is lexical: "Track 10" sorts before "Track 2".
