# 0018. Saved Playlists, M3U Import/Export, and the `/playlist-<action>` Command Family

## Context
With the play queue complete ([ADR 0016](0016-persistent-play-queue-resume-and-play-counting.md), [ADR 0017](0017-queue-playback-modes-repeat-consume-shuffle-and-sort.md)), MusicMatch needs traditional playlists: named, curated lists that outlive any single listening session. The requested features:
1. Save the queue to a playlist.
2. Rename a playlist.
3. Remove a playlist (not its tracks).
4. Remove a playlist **and** its tracks.
5. Fill the queue with a playlist.
6. Import and export playlists.
7. Remove a track from a playlist by ID (**every occurrence**) or by position.

The commands must follow the naming idea of the queue family (`/queue-<action>`), e.g. `/playlist-rename`.

Forces:
- The CONTEXT glossary already promises that a soft-deleted (missing) track keeps its playlists, and that the Library holds playlists.
- Deleting tracks is governed by [ADR 0013](0013-library-maintenance-consolidation-and-deletion-safeguards.md): files go to the Recycle Bin, never `os.remove`, behind confirmation gates.
- MusicMatch is Windows-first: playlist files come from other players with backslash paths, drive letters, and ANSI-encoded `.m3u`.

## Decision

### 1. The `/playlist-<action>` family
| Feature | Command |
| :--- | :--- |
| View | `/playlist` (all playlists) · `/playlist <name>` (one playlist's tracks), like `/queue` |
| Save the queue to a playlist | `/playlist-save <name>` |
| Fill the queue with a playlist | `/playlist-load <name> [--append]` |
| Rename | `/playlist-rename <name> <new name>` |
| Remove a track: by ID (all occurrences) / by position (one entry) | `/playlist-remove <name> <id>` · `/playlist-remove <name> #<position>` |
| Remove a playlist, keep its tracks | `/playlist-delete <name>` |
| Remove a playlist and its tracks | `/playlist-delete-with-tracks <name>` |
| Import / export | `/playlist-import <file> [name]` · `/playlist-export <name> [file \| folder] [--relative]` |

Naming rules:
- **`save` / `load` pair.** Each names the direction of the data between the queue and the playlist.
- **`delete`, not `remove`, for the playlist itself.** In the queue family, `remove` means taking entries out of a list (`/queue-remove`), and `/delete` already means deleting whole tracks. So `/playlist-remove` takes tracks out of a playlist, exactly as `/queue-remove` does for the queue, keeping the two families parallel.
- **Variants are suffixes, as in `/queue-add` vs `/queue-add-last`.** Hence `/playlist-delete-with-tracks`. Its destructive part is visible in the name, not hidden in a flag.
- **No aliases.** A `/lista-…` alias would break the rule. A test enforces the family over the registry.

### 2. Storage: playlists are part of the Library
Two tables in the catalog database, created and migrated by the shared `apply_schema()`:

| Table | Content |
| :--- | :--- |
| `playlists(id, name, name_key UNIQUE, created_at, updated_at)` | `name_key` is the case- and accent-folded name: `Café` and `cafe` are the same playlist. |
| `playlist_entries(playlist_id, position, track_id)` | Ordered entries; duplicates allowed. `ON DELETE CASCADE` from the playlist. |

Entries reference `tracks(id)` with the same policy as the queue:
- **Moves and renames are followed.** Fast Relocation and `/library reorganize` re-key tracks with an `UPDATE`, so entries follow through `ON UPDATE CASCADE`.
- **Missing files keep their entries.** A soft-deleted (`MISSING`) track stays in the catalog, so its entries stay too, as the glossary promises. `/playlist` flags them like `/queue` does.
- **Removing a track from the Library removes its entries.** `/unindex`, `/delete`, `/prune` and `/library clear` are the user deciding the track is gone (`ON DELETE CASCADE`).

`SQLitePlaylistRepository` uses the catalog repository's own connection. Playlists are only touched from the REPL thread, unlike the queue, which the player's background threads save.

Names are trimmed and validated: not empty, at most 100 characters, no control characters, and not starting with `--` (reserved for options). Commands find a playlist by its exact name or by a **unique prefix** (`/playlist-load road`), the same convenience as short track IDs. An ambiguous prefix lists the candidates.

### 3. Queue ↔ playlist
- **`/playlist-save`** stores the queue exactly as `/queue` lists it: every entry in order, including played ones and duplicates. Saving over an existing playlist asks first and keeps that playlist's name. Queue entries whose track has left the catalog are skipped and reported.
- **`/playlist-load`** replaces the queue with the playlist, from its first entry. When the current queue has tracks (and differs from the playlist), it asks first and suggests `/playlist-save` to keep the old one. `--append` adds to the end instead and asks nothing, since nothing is lost.
- **Loading during playback.** A playing or paused track keeps going outside the queue, and the loaded playlist starts right after it. From a stopped player nothing starts by itself (`/queue-play`). This matches `/queue-clear`, which never interrupts the current track.
- **Unavailable tracks are loaded too.** They are flagged and skipped with a notice, as everywhere in the queue. Otherwise a load/edit/save cycle would silently drop tracks from an unplugged drive.

### 4. Deleting
- **`/playlist-delete`** asks `[s/N]` and deletes only the playlist. Tracks stay in the Library, the queue and other playlists.
- **`/playlist-delete-with-tracks`** applies ADR 0013 to the playlist's tracks (each track counted once):
  - It lists them and warns about files outside the Managed Library, about other playlists that will lose those tracks, and about queue entries that will go.
  - It then requires the **Count-Verification Gate**: typing the exact number of tracks.
  - Files go to the **Recycle Bin** through the existing `LibraryMaintenanceService.delete_tracks_to_trash`, and the tracks are unindexed. Their queue entries are removed from the player.
  - If the playing track is among them, playback stops first: Windows cannot move an open file.
  - If some files cannot be moved, the playlist is **kept with exactly those tracks**, so the command can be repeated after fixing the cause. It is deleted only when it is empty.

### 5. Removing tracks from a playlist
`/playlist-remove` mirrors `/queue-remove`: one command, two forms, distinguished by the `#`.
- **`<id>` removes every occurrence** of the track. It accepts a full ID or a Short Track ID (at least 4 hex digits, `trk_` optional). The ID is matched against the **playlist's own entries**, so a prefix only has to be unique within that playlist. An ambiguous prefix is refused, and so is a track that is not in the playlist.
- **`#<position>` removes that single entry**. Positions are the 1-based order listed by `/playlist <name>`; stored positions can have gaps after tracks leave the Library, so the position is resolved against the current order. When other copies of the track remain, the confirmation says how many and shows the `<id>` form to remove them all.
- **The track reference is always the last word**, so a multi-word name needs no quotes (`/playlist-remove Road Trip #3`).
- **No confirmation**, like `/queue-remove`: only the selected entries go, and the track stays in the Library, the queue and other playlists. A playlist left empty is kept, with a hint to delete it.

### 6. M3U import and export
**M3U / extended M3U** (`#EXTM3U`, `#EXTINF`) is the format every player reads and writes. Export always writes `.m3u8` (UTF-8); import accepts `.m3u8` and `.m3u`.

**Import** resolves each entry in order:
1. **By path.** Relative paths are resolved against the playlist file's folder. `file://` URLs are decoded, and backslashes are accepted on POSIX. The lookup uses the Canonical Path Hash (ADR 0009), so it is a primary-key lookup.
2. **By tags** when the path is not in the catalog (a playlist written on another machine or drive letter). The `#EXTINF` artist and title must match, ignoring case, and the duration must be within 3 s when `#EXTINF` has one. That keeps "Intro" by the same artist on two albums apart. Among several copies, the available one with the highest bitrate wins, as the `/audit` recommendation does.
3. **Otherwise the entry is reported, never guessed:**
   - Files that exist but were never scanned are listed with the exact `/scan "<folder>"` commands to run. Import does not index files behind the user's back; scanning stays the Library's one entry door.
   - Files found neither on disk nor in the catalog are listed.
   - Stream URLs are ignored.

Other import behaviour:
- **Encoding.** `.m3u8` and files with a BOM are read as UTF-8. A classic `.m3u` is read as UTF-8 and falls back to cp1252, the ANSI code page Windows players write.
- **Naming and nothing matched.** The playlist name defaults to the file name, and an existing playlist is replaced only after confirmation. If nothing matches, no playlist is created.

**Export** writes `#EXTM3U`, `#PLAYLIST:<name>`, then `#EXTINF:<seconds>,<artist> - <title>` and the path for each entry:
- **Paths.** Absolute by default. `--relative` writes paths relative to the playlist file, so a folder with music and playlists can be copied to another drive or machine. An entry on another Windows drive has no relative path: it is written absolute and reported.
- **Destination.** Default `<Managed Library>/Playlists/<name>.m3u8`. A folder argument writes `<name>.m3u8` inside it; a `.m3u8`/`.m3u` argument is used as is. The file name is sanitized for Windows and POSIX, including reserved device names such as `CON`.
- **Safety.** Overwriting a file asks first, and the file is written atomically (temp file, then rename).

### 7. Command-line parsing (fix)
The dispatcher used `shlex.split`, whose POSIX mode treats `\` as an escape: an unquoted `C:\Users\me\Music` reached every command as `C:UsersmeMusic` (including the existing `/scan`). Import/export take Windows paths, so the dispatcher now uses a `shlex` lexer with **escapes disabled** (and, as before, no `#` comments). Quotes keep working for arguments with spaces.

Quoting is rarely needed anyway:
- A **last** argument may contain spaces (`/playlist-save Road Trip`).
- When a playlist name comes before another argument, commands take the **longest leading run of words that names an existing playlist** (`/playlist-rename Road Trip Summer Trip`).
- `/playlist-import` likewise takes the longest leading run that is an existing file (`/playlist-import D:\My Music\mix.m3u Road Trip`).

## Consequences
- Playlists are first-class Library content: they survive restarts, rescans, relocations and reorganizations, and work with the queue in both directions.
- Playlists can move between MusicMatch and other players (foobar2000, Winamp, VLC, MusicBee) and across machines, with paths resolved by tags when they differ.
- Deleting a playlist with its tracks gets the same protection as `/delete`, plus warnings specific to playlists.
- The backslash fix benefits every command that takes a path.
- The smart playlists on the roadmap (harmonic/AI generation) have a storage and a queue integration to target.

### Known limitations
- Tracks are taken out of a playlist directly (`/playlist-remove`), but they are added to it through the queue (`/playlist-load`, add with `/queue-add*`, `/playlist-save`). A direct `/playlist-add` is the natural next step.
- `/queue-remove` still accepts ID prefixes shorter than the 4 hex digits of the Short Track ID rule, which `/playlist-remove` enforces.
- `/library clear` empties every playlist, because their tracks leave the catalog. `/playlist-export` is the backup.
- Tag matching compares artist and title ignoring ASCII case only; accents must match.
- A name containing an apostrophe must be wrapped in double quotes (`"Rock 'n' Roll"`), because single quotes are quoting characters.
- Only M3U/M3U8. PLS, XSPF and iTunes XML are not supported.
