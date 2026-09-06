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

ALL_SCHEMA_STATEMENTS = [
    CREATE_TRACKS_TABLE,
    CREATE_INDEX_STATUS,
    CREATE_TRACKS_FTS_TABLE,
    CREATE_TRIGGER_AFTER_INSERT,
    CREATE_TRIGGER_AFTER_DELETE,
    CREATE_TRIGGER_AFTER_UPDATE,
]
