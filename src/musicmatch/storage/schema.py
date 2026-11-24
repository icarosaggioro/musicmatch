"""Definições de Esquema (DDL) e Triggers para SQLite com FTS5.

CONCEITO ARQUITETURAL DIDÁTICO:
--------------------------------
Por que usamos uma Tabela Relacional + Tabela Virtual FTS5 com Conteúdo Externo (External Content Table)?

1. O Dilema:
   - Uma tabela FTS5 pura é ótima para texto, mas fraca para índices numéricos
     (ex: buscar faixas com BPM entre 120 e 130 ou ordenar por duração em segundos).
   - Uma tabela SQL normal é ótima para números e constraints (PRIMARY KEY, UNIQUE),
     mas péssima para texto ('LIKE %termo%' faz Full Table Scan O(N)).

2. A Solução (External Content Table):
   - 'tracks': Tabela normal que armazena os dados oficiais, constraints e números.
   - 'tracks_fts': Tabela virtual FTS5 configurada com 'content=tracks' e 'content_rowid=rowid'.
     Ela NÃO duplica o armazenamento dos textos em disco; apenas mantém os ponteiros
     do Índice Invertido apontando para o 'rowid' da tabela 'tracks'.
   - 'Triggers' (Gatilhos): Três triggers automáticos (AFTER INSERT, AFTER DELETE, AFTER UPDATE)
     sincronizam o índice invertido imediatamente a cada alteração na tabela 'tracks',
     sem exigir que a aplicação se preocupe com sincronismo manual.
"""

CREATE_TRACKS_TABLE = """
CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT NOT NULL,
    genre TEXT NOT NULL,
    duration_seconds REAL NOT NULL CHECK(duration_seconds >= 0),
    bitrate_kbps INTEGER NOT NULL CHECK(bitrate_kbps > 0),
    bpm REAL NOT NULL CHECK(bpm > 0),
    file_path TEXT UNIQUE NOT NULL,
    mood TEXT,
    lufs REAL,
    file_mtime REAL,
    file_size INTEGER,
    status TEXT DEFAULT 'AVAILABLE',
    year INTEGER,
    track_number INTEGER,
    musical_key TEXT,
    bpm_source TEXT,
    play_count INTEGER NOT NULL DEFAULT 0,
    last_played_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
"""

CREATE_INDEX_STATUS = """
CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks(status);
"""

CREATE_TRACKS_FTS_TABLE = """
CREATE VIRTUAL TABLE IF NOT EXISTS tracks_fts USING fts5(
    title,
    artist,
    album,
    genre,
    mood,
    content='tracks',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);
"""

# Trigger após inserção: insere os termos na tabela virtual FTS
CREATE_TRIGGER_AFTER_INSERT = """
CREATE TRIGGER IF NOT EXISTS trg_tracks_ai AFTER INSERT ON tracks BEGIN
    INSERT INTO tracks_fts(rowid, title, artist, album, genre, mood)
    VALUES (new.rowid, new.title, new.artist, new.album, new.genre, new.mood);
END;
"""

# Trigger após deleção: remove os termos correspondentes do FTS5
CREATE_TRIGGER_AFTER_DELETE = """
CREATE TRIGGER IF NOT EXISTS trg_tracks_ad AFTER DELETE ON tracks BEGIN
    INSERT INTO tracks_fts(tracks_fts, rowid, title, artist, album, genre, mood)
    VALUES ('delete', old.rowid, old.title, old.artist, old.album, old.genre, old.mood);
END;
"""

# Trigger após atualização: remove os termos antigos e insere os novos no FTS5
CREATE_TRIGGER_AFTER_UPDATE = """
CREATE TRIGGER IF NOT EXISTS trg_tracks_au AFTER UPDATE ON tracks BEGIN
    INSERT INTO tracks_fts(tracks_fts, rowid, title, artist, album, genre, mood)
    VALUES ('delete', old.rowid, old.title, old.artist, old.album, old.genre, old.mood);
    INSERT INTO tracks_fts(rowid, title, artist, album, genre, mood)
    VALUES (new.rowid, new.title, new.artist, new.album, new.genre, new.mood);
END;
"""

# Acoustic analysis (ADR 0014) lives in its own table instead of extra 'tracks' columns:
# - Fingerprint and waveform blobs stay out of the hot 'SELECT * FROM tracks' paths
#   (/list, /search, stat-cache), keeping catalog queries and re-scans fast.
# - ON DELETE CASCADE: when the scanner re-persists a modified file (INSERT OR REPLACE) or a
#   track is unindexed/deleted, its now-stale analysis disappears with it.
# - ON UPDATE CASCADE: Fast Relocation and /library reorganize rewrite 'tracks.id'; the
#   analysis follows the file to its new identity without re-running DSP (ADR 0009).
# - source_mtime/source_size stamp the file state the analysis describes (analysis stat-cache).
CREATE_TRACK_ANALYSIS_TABLE = """
CREATE TABLE IF NOT EXISTS track_analysis (
    track_id TEXT PRIMARY KEY REFERENCES tracks(id) ON DELETE CASCADE ON UPDATE CASCADE,
    analysis_version INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('OK', 'ERROR')),
    error_message TEXT,
    analyzed_at TEXT NOT NULL DEFAULT (datetime('now')),
    source_mtime REAL,
    source_size INTEGER,
    decoder TEXT,
    duration_seconds REAL,
    sample_rate INTEGER,
    channels INTEGER,
    integrated_lufs REAL,
    loudness_range_lu REAL,
    sample_peak_dbfs REAL,
    bpm REAL,
    bpm_confidence REAL,
    musical_key TEXT,
    camelot_key TEXT,
    key_confidence REAL,
    tuning_cents REAL,
    fingerprint_algorithm TEXT,
    fingerprint_hash TEXT,
    fingerprint_frames INTEGER,
    fingerprint BLOB,
    waveform_peaks BLOB,
    waveform_rms BLOB,
    processing_ms REAL
);
"""

# Exact acoustic duplicates are a GROUP BY on this column.
CREATE_INDEX_FINGERPRINT_HASH = """
CREATE INDEX IF NOT EXISTS idx_track_analysis_fingerprint_hash ON track_analysis(fingerprint_hash);
"""

# Persistent playback (ADR 0016). Queue entries are rows, not a set: the same track may be
# queued several times. Foreign keys follow the track through Fast Relocation/reorganize
# (ON UPDATE CASCADE) and drop entries of unindexed tracks (ON DELETE CASCADE / SET NULL).
CREATE_PLAY_QUEUE_TABLE = """
CREATE TABLE IF NOT EXISTS play_queue (
    position INTEGER PRIMARY KEY,
    track_id TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE ON UPDATE CASCADE
);
"""

# Single-row table: the last played track and its position, the player state (PAUSED keeps a
# resume point, STOPPED means "restart from the beginning of the queue"), the queue cursor and
# the queue modes repeat and consume (ADR 0017).
CREATE_PLAYER_SESSION_TABLE = """
CREATE TABLE IF NOT EXISTS player_session (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_track_id TEXT REFERENCES tracks(id) ON DELETE SET NULL ON UPDATE CASCADE,
    position_seconds REAL NOT NULL DEFAULT 0,
    listened_seconds REAL NOT NULL DEFAULT 0,
    play_counted INTEGER NOT NULL DEFAULT 0,
    volume INTEGER,
    state TEXT NOT NULL DEFAULT 'STOPPED',
    queue_cursor INTEGER NOT NULL DEFAULT 0,
    current_entry INTEGER,
    repeat_mode INTEGER NOT NULL DEFAULT 0,
    consume_mode INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now'))
);
"""

# Playlists (ADR 0018): named, ordered lists of library tracks; duplicates allowed. 'name_key'
# (case- and accent-folded) makes names unique the way users type them. Entries follow the
# track through Fast Relocation/reorganize (ON UPDATE CASCADE); removing a track from the
# library (/unindex, /delete, /prune) removes its entries. Soft-deleted (MISSING) tracks stay.
CREATE_PLAYLISTS_TABLE = """
CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_PLAYLIST_ENTRIES_TABLE = """
CREATE TABLE IF NOT EXISTS playlist_entries (
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    track_id TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE ON UPDATE CASCADE,
    PRIMARY KEY (playlist_id, position)
);
"""

# "Which playlists contain these tracks?" (warnings before deleting tracks) and FK cascades.
CREATE_INDEX_PLAYLIST_ENTRIES_TRACK = """
CREATE INDEX IF NOT EXISTS idx_playlist_entries_track ON playlist_entries(track_id);
"""

# Issues (ADR 0019): foreseen problems with resources/environment, for the user to review.
# One row per (kind, subject): a recurrence bumps 'occurrences'/'last_seen' instead of adding
# rows. No FK to the subject (files that never entered the catalog, devices, playlist files),
# and no CHECK on 'status' so new states (e.g. RESOLVED, ADR 0020) need no table rebuild.
CREATE_ISSUES_TABLE = """
CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_key TEXT NOT NULL,
    subject_label TEXT,
    message TEXT NOT NULL,
    details TEXT,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN',
    occurrences INTEGER NOT NULL DEFAULT 1,
    first_seen TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen TEXT NOT NULL DEFAULT (datetime('now')),
    dismissed_at TEXT,
    UNIQUE (kind, subject_key)
);
"""

CREATE_INDEX_ISSUES_STATUS = """
CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status, last_seen);
"""

# Library-wide counters that must survive unindexing tracks (e.g. 'total_plays').
CREATE_PLAYBACK_STATS_TABLE = """
CREATE TABLE IF NOT EXISTS playback_stats (
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
"""

# Append-only log of counted plays: the raw material for future listening-habit learning.
CREATE_PLAY_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS play_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id TEXT REFERENCES tracks(id) ON DELETE SET NULL ON UPDATE CASCADE,
    played_at TEXT NOT NULL DEFAULT (datetime('now')),
    listened_seconds REAL NOT NULL
);
"""

CREATE_INDEX_PLAY_HISTORY_TRACK = """
CREATE INDEX IF NOT EXISTS idx_play_history_track ON play_history(track_id);
"""

ALL_SCHEMA_STATEMENTS = [
    CREATE_TRACKS_TABLE,
    CREATE_INDEX_STATUS,
    CREATE_TRACKS_FTS_TABLE,
    CREATE_TRIGGER_AFTER_INSERT,
    CREATE_TRIGGER_AFTER_DELETE,
    CREATE_TRIGGER_AFTER_UPDATE,
    CREATE_TRACK_ANALYSIS_TABLE,
    CREATE_INDEX_FINGERPRINT_HASH,
    CREATE_PLAY_QUEUE_TABLE,
    CREATE_PLAYER_SESSION_TABLE,
    CREATE_PLAYBACK_STATS_TABLE,
    CREATE_PLAY_HISTORY_TABLE,
    CREATE_INDEX_PLAY_HISTORY_TRACK,
    CREATE_PLAYLISTS_TABLE,
    CREATE_PLAYLIST_ENTRIES_TABLE,
    CREATE_INDEX_PLAYLIST_ENTRIES_TRACK,
    CREATE_ISSUES_TABLE,
    CREATE_INDEX_ISSUES_STATUS,
]

# Columns added to 'tracks' after its first release; applied idempotently to existing databases.
TRACKS_COLUMN_MIGRATIONS = [
    ("file_mtime", "REAL"),
    ("file_size", "INTEGER"),
    ("status", "TEXT DEFAULT 'AVAILABLE'"),
    ("year", "INTEGER"),
    ("track_number", "INTEGER"),
    ("musical_key", "TEXT"),
    ("bpm_source", "TEXT"),
    ("play_count", "INTEGER NOT NULL DEFAULT 0"),
    ("last_played_at", "TEXT"),
]


# Columns added to 'player_session' after its first version.
PLAYER_SESSION_COLUMN_MIGRATIONS = [
    ("state", "TEXT NOT NULL DEFAULT 'PAUSED'"),  # earlier rows were resume points
    ("queue_cursor", "INTEGER NOT NULL DEFAULT 0"),
    ("current_entry", "INTEGER"),
    ("repeat_mode", "INTEGER NOT NULL DEFAULT 0"),  # ADR 0017
    ("consume_mode", "INTEGER NOT NULL DEFAULT 0"),  # ADR 0017
]


def apply_schema(conn) -> None:
    """Creates/migrates every table, index and trigger (idempotent; shared by all connections)."""
    with conn:
        conn.execute(CREATE_TRACKS_TABLE)
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(tracks);").fetchall()}
        for col_name, col_type in TRACKS_COLUMN_MIGRATIONS:
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE tracks ADD COLUMN {col_name} {col_type};")
        had_fts = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'tracks_fts';").fetchone() is not None
        for statement in ALL_SCHEMA_STATEMENTS:
            if statement != CREATE_TRACKS_TABLE:
                conn.execute(statement)
        session_cols = {row[1] for row in conn.execute("PRAGMA table_info(player_session);").fetchall()}
        for col_name, col_type in PLAYER_SESSION_COLUMN_MIGRATIONS:
            if col_name not in session_cols:
                conn.execute(f"ALTER TABLE player_session ADD COLUMN {col_name} {col_type};")
        # An FTS5 external-content index created over existing rows starts empty; the first
        # UPDATE/DELETE trigger would then "delete" never-indexed entries and corrupt it.
        if not had_fts and conn.execute("SELECT 1 FROM tracks LIMIT 1;").fetchone() is not None:
            conn.execute("INSERT INTO tracks_fts(tracks_fts) VALUES ('rebuild');")
