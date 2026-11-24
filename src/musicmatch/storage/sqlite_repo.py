"""Repositório SQLite com suporte a Full-Text Search (FTS5).

CONCEITO ARQUITETURAL DIDÁTICO:
--------------------------------
O 'Repository Pattern' abstrai o mecanismo de persistência. A aplicação consome
objetos de domínio tipados ('Track') sem precisar escrever SQL em controladores,
comandos ou ferramentas do agente.

Destaques da Implementação:
1. Conexão Segura & WAL: No disco, utiliza 'PRAGMA journal_mode = WAL' para concorrência e velocidade.
2. Suporte a ':memory:': Para testes unitários relâmpago com pytest.
3. Busca Híbrida: Combina o índice invertido do FTS5 (ranqueado com Okapi BM25)
   com filtros relacionais tradicionais (gênero exato, faixa de BPM, duração).
"""

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from musicmatch.config import settings
from musicmatch.domain.analysis import ANALYSIS_VERSION, AudioFeatures, TrackAnalysis
from musicmatch.domain.models import Track
from musicmatch.storage.schema import apply_schema

# Current-analysis predicate shared by the pending/coverage queries: an analysis row is
# current when it was produced by this ANALYSIS_VERSION for the exact file state (mtime and
# size) recorded in the catalog. 'IS' keeps the comparison NULL-safe.
_ANALYSIS_IS_CURRENT = """
    a.track_id IS NOT NULL
    AND a.analysis_version >= :version
    AND a.source_size IS t.file_size
    AND a.source_mtime IS t.file_mtime
"""

def row_to_track(row: sqlite3.Row) -> Track:
    """Maps a 'tracks' row (sqlite3.Row) to the Track domain model; tolerant to older schemas."""
    keys = row.keys() if hasattr(row, "keys") else []
    return Track(
        id=row["id"],
        title=row["title"],
        artist=row["artist"],
        album=row["album"],
        genre=row["genre"],
        duration_seconds=row["duration_seconds"],
        bitrate_kbps=row["bitrate_kbps"],
        bpm=row["bpm"],
        file_path=row["file_path"],
        mood=row["mood"] if "mood" in keys else None,
        lufs=row["lufs"] if "lufs" in keys else None,
        file_mtime=row["file_mtime"] if "file_mtime" in keys else None,
        file_size=row["file_size"] if "file_size" in keys else None,
        status=row["status"] if "status" in keys and row["status"] else "AVAILABLE",
        year=row["year"] if "year" in keys else None,
        track_number=row["track_number"] if "track_number" in keys else None,
        musical_key=row["musical_key"] if "musical_key" in keys else None,
        play_count=(row["play_count"] or 0) if "play_count" in keys else 0,
        last_played_at=row["last_played_at"] if "last_played_at" in keys else None,
    )


class SQLiteTrackRepository:
    """Repositório de persistência para faixas musicais com SQLite e FTS5."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None) -> None:
        self.db_path = str(db_path or settings.DATABASE_PATH)
        
        # Garante que a pasta de destino exista no disco (se não for banco em memória)
        if self.db_path != ":memory:":
            path_obj = Path(self.db_path)
            path_obj.parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

        # Habilita constraints e performance
        self.conn.execute("PRAGMA foreign_keys = ON;")
        if self.db_path != ":memory:":
            self.conn.execute("PRAGMA journal_mode = WAL;")

        self.init_db()

    def init_db(self) -> None:
        """Cria/migra tabelas, índices e triggers de forma idempotente (ver schema.apply_schema)."""
        apply_schema(self.conn)

    def _row_to_track(self, row: sqlite3.Row) -> Track:
        """Converte uma linha do SQLite (sqlite3.Row) para uma entidade Pydantic Track."""
        return row_to_track(row)

    def insert_track(self, track: Track) -> None:
        """Insere uma única faixa no banco de dados.
        
        Os triggers do SQLite sincronizam automaticamente a tabela 'tracks_fts'.
        """
        sql = """
        INSERT INTO tracks (
            id, title, artist, album, genre, duration_seconds,
            bitrate_kbps, bpm, file_path, mood, lufs,
            file_mtime, file_size, status, year, track_number, musical_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self.conn:
            self.conn.execute(
                sql,
                (
                    track.id, track.title, track.artist, track.album,
                    track.genre, track.duration_seconds, track.bitrate_kbps,
                    track.bpm, track.file_path, track.mood, track.lufs,
                    track.file_mtime, track.file_size, track.status,
                    track.year, track.track_number, track.musical_key
                )
            )

    def insert_batch(self, tracks: List[Track]) -> int:
        """Insere ou atualiza uma lista de faixas em lote dentro de uma única transação.

        Usa UPSERT (e não INSERT OR REPLACE): REPLACE apaga e recria a linha, o que zeraria
        'play_count'/'last_played_at' e, via cascata, removeria a faixa da fila persistente
        sempre que o arquivo fosse modificado (ex.: tags editadas e novo /scan). Com UPSERT,
        as estatísticas de reprodução sobrevivem; apenas a análise acústica que deixou de
        corresponder ao arquivo (carimbo mtime/tamanho) é descartada (ADR 0014 / ADR 0016).
        """
        if not tracks:
            return 0

        sql = """
        INSERT INTO tracks (
            id, title, artist, album, genre, duration_seconds,
            bitrate_kbps, bpm, file_path, mood, lufs,
            file_mtime, file_size, status, year, track_number, musical_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title, artist = excluded.artist, album = excluded.album,
            genre = excluded.genre, duration_seconds = excluded.duration_seconds,
            bitrate_kbps = excluded.bitrate_kbps, bpm = excluded.bpm, file_path = excluded.file_path,
            mood = excluded.mood, lufs = excluded.lufs, file_mtime = excluded.file_mtime,
            file_size = excluded.file_size, status = excluded.status, year = excluded.year,
            track_number = excluded.track_number, musical_key = excluded.musical_key,
            updated_at = datetime('now');
        """
        data = [
            (
                t.id, t.title, t.artist, t.album, t.genre,
                t.duration_seconds, t.bitrate_kbps, t.bpm,
                t.file_path, t.mood, t.lufs,
                t.file_mtime, t.file_size, t.status,
                t.year, t.track_number, t.musical_key
            )
            for t in tracks
        ]
        with self.conn:
            self.conn.executemany(sql, data)
            self.conn.executemany(
                """
                DELETE FROM track_analysis
                WHERE track_id = ? AND (source_mtime IS NOT ? OR source_size IS NOT ?);
                """,
                [(t.id, t.file_mtime, t.file_size) for t in tracks],
            )
        return len(tracks)

    def update_track(self, track: Track) -> bool:
        """Atualiza os metadados de uma faixa existente.
        
        O trigger 'trg_tracks_au' atualiza o índice FTS5 automaticamente.
        """
        sql = """
        UPDATE tracks SET
            title = ?, artist = ?, album = ?, genre = ?,
            duration_seconds = ?, bitrate_kbps = ?, bpm = ?,
            file_path = ?, mood = ?, lufs = ?,
            file_mtime = ?, file_size = ?, status = ?,
            year = ?, track_number = ?, musical_key = ?, updated_at = datetime('now')
        WHERE id = ?;
        """
        with self.conn:
            cursor = self.conn.execute(
                sql,
                (
                    track.title, track.artist, track.album, track.genre,
                    track.duration_seconds, track.bitrate_kbps, track.bpm,
                    track.file_path, track.mood, track.lufs,
                    track.file_mtime, track.file_size, track.status,
                    track.year, track.track_number, track.musical_key, track.id
                )
            )
            return cursor.rowcount > 0

    def get_tracks_under_path(self, path_prefix: str) -> List[Track]:
        """Recupera faixas cujo caminho de arquivo esteja contido no diretório ou prefixo informado."""
        norm_prefix = path_prefix.replace("\\", "/").rstrip("/")
        pattern_folder = f"{norm_prefix}/%"
        sql = """
        SELECT * FROM tracks
        WHERE replace(file_path, '\\', '/') = ?
           OR replace(file_path, '\\', '/') LIKE ?;
        """
        cursor = self.conn.execute(sql, (norm_prefix, pattern_folder))
        return [self._row_to_track(row) for row in cursor.fetchall()]

    def mark_missing_by_ids(self, track_ids: List[str]) -> int:
        """Executa soft-delete marcando faixas como 'MISSING' sem apagar histórico ou métricas."""
        if not track_ids:
            return 0
        placeholders = ",".join("?" for _ in track_ids)
        sql = f"UPDATE tracks SET status = 'MISSING', updated_at = datetime('now') WHERE id IN ({placeholders});"
        with self.conn:
            cursor = self.conn.execute(sql, track_ids)
            return cursor.rowcount

    def find_relocation_candidate(
        self,
        file_size: int,
        duration_seconds: float,
        title: str,
        artist: str,
        duration_delta: float = 1.0,
    ) -> Optional[Track]:
        """Localiza faixa com status 'MISSING' compatível com a heurística de Fast Relocation (ADR 0009)."""
        sql = """
        SELECT * FROM tracks
        WHERE status = 'MISSING'
          AND file_size = ?
          AND abs(duration_seconds - ?) <= ?
          AND LOWER(title) = LOWER(?)
          AND LOWER(artist) = LOWER(?)
        LIMIT 1;
        """
        cursor = self.conn.execute(sql, (file_size, duration_seconds, duration_delta, title, artist))
        row = cursor.fetchone()
        return self._row_to_track(row) if row else None

    def relocate_track(self, old_id: str, new_track: Track) -> bool:
        """Migra um registro de faixa com status 'MISSING' para seu novo caminho/ID canônico (ADR 0009).

        A análise acústica acompanha a faixa via ON UPDATE CASCADE; se ela estava atualizada
        para o arquivo antigo, seu carimbo (mtime/tamanho) é rebaseado para o arquivo movido,
        preservando as métricas de DSP sem reprocessar o áudio (ADR 0014).
        """
        sql = """
        UPDATE tracks SET
            id = ?,
            file_path = ?,
            file_mtime = ?,
            file_size = ?,
            status = 'AVAILABLE',
            updated_at = datetime('now')
        WHERE id = ?;
        """
        with self.conn:
            old = self.conn.execute(
                "SELECT file_mtime, file_size FROM tracks WHERE id = ?;", (old_id,)
            ).fetchone()
            cursor = self.conn.execute(
                sql,
                (
                    new_track.id,
                    new_track.file_path,
                    new_track.file_mtime,
                    new_track.file_size,
                    old_id,
                ),
            )
            if cursor.rowcount > 0 and old is not None:
                self.conn.execute(
                    """
                    UPDATE track_analysis SET source_mtime = ?, source_size = ?
                    WHERE track_id = ? AND source_mtime IS ? AND source_size IS ?;
                    """,
                    (
                        new_track.file_mtime,
                        new_track.file_size,
                        new_track.id,
                        old["file_mtime"],
                        old["file_size"],
                    ),
                )
            return cursor.rowcount > 0

    def get_stat_cache_map(self, path_prefix: Optional[str] = None) -> Dict[str, Any]:
        """Mapeia caminhos canônicos para seus dados de stat-cache para re-scans O(1)."""
        if path_prefix:
            tracks = self.get_tracks_under_path(path_prefix)
        else:
            tracks = self.get_all_tracks()
        
        cache_map = {}
        for t in tracks:
            canonical = Track.canonicalize_path(t.file_path)
            cache_map[canonical] = (t.file_mtime, t.file_size, t.status, t.id)
        return cache_map

    def delete_track(self, track_id: str) -> bool:
        """Remove uma faixa pelo seu ID.
        
        O trigger 'trg_tracks_ad' remove os termos do FTS5 automaticamente.
        """
        sql = "DELETE FROM tracks WHERE id = ?;"
        with self.conn:
            cursor = self.conn.execute(sql, (track_id,))
            return cursor.rowcount > 0

    def get_track_by_id(self, track_id: str) -> Optional[Track]:
        """Recupera uma faixa pelo seu identificador primário."""
        cursor = self.conn.execute("SELECT * FROM tracks WHERE id = ?;", (track_id,))
        row = cursor.fetchone()
        return self._row_to_track(row) if row else None

    def get_track(self, track_id: str) -> Optional[Track]:
        """Alias ergonômico para get_track_by_id."""
        return self.get_track_by_id(track_id)

    def find_tracks_by_id_prefix(self, prefix: str, limit: int = 2) -> List[Track]:
        """Tracks whose ID starts with `prefix` (short IDs typed in commands, e.g. 'trk_3fa2b9c1').

        Uses the primary-key index (a range scan, not LIKE) and returns at most `limit` rows, so
        callers can detect ambiguity by asking for two.
        """
        if not prefix:
            return []
        upper = prefix[:-1] + chr(ord(prefix[-1]) + 1)
        cursor = self.conn.execute(
            "SELECT * FROM tracks WHERE id >= ? AND id < ? ORDER BY id LIMIT ?;",
            (prefix, upper, int(limit)),
        )
        return [self._row_to_track(row) for row in cursor.fetchall()]

    def get_track_by_path(self, file_path: str) -> Optional[Track]:
        """Recupera uma faixa pelo caminho do arquivo no disco."""
        cursor = self.conn.execute("SELECT * FROM tracks WHERE file_path = ?;", (file_path,))
        row = cursor.fetchone()
        return self._row_to_track(row) if row else None

    def find_tracks_by_artist_title(self, artist: str, title: str) -> List[Track]:
        """Tracks with this artist and title, ignoring ASCII case (playlist import fallback, ADR 0018)."""
        cursor = self.conn.execute(
            "SELECT * FROM tracks WHERE artist = ? COLLATE NOCASE AND title = ? COLLATE NOCASE;",
            (artist.strip(), title.strip()),
        )
        return [self._row_to_track(row) for row in cursor.fetchall()]

    def get_all_tracks(self, limit: Optional[int] = None, offset: int = 0) -> List[Track]:
        """Retorna todas as faixas ordenadas por Artista, Álbum e Título com suporte a paginação."""
        if limit is not None:
            cursor = self.conn.execute(
                "SELECT * FROM tracks ORDER BY artist, album, title LIMIT ? OFFSET ?;",
                (limit, offset),
            )
        else:
            cursor = self.conn.execute("SELECT * FROM tracks ORDER BY artist, album, title;")
        return [self._row_to_track(row) for row in cursor.fetchall()]

    def search_fulltext(self, query: str, limit: int = 50) -> List[Track]:
        """Executa busca textual rápida no índice FTS5 ranqueada por relevância Okapi BM25.
        
        Args:
            query: Termo ou expressão de busca (ex: 'Queen', 'Bohemian*', 'Rock NOT Metal').
            limit: Quantidade máxima de resultados.
        """
        cleaned = query.strip()
        if not cleaned:
            return []

        # Se for uma busca simples sem operadores booleanos, adiciona busca por prefixo
        # para permitir que 'Bohem' encontre 'Bohemian'
        fts_query = cleaned
        if not any(token in cleaned for token in ["*", '"', "AND", "OR", "NOT", "NEAR"]):
            words = cleaned.split()
            fts_query = " ".join(f"{w}*" for w in words)

        sql = """
        SELECT t.*
        FROM tracks t
        JOIN tracks_fts fts ON t.rowid = fts.rowid
        WHERE tracks_fts MATCH ?
        ORDER BY fts.rank
        LIMIT ?;
        """
        try:
            cursor = self.conn.execute(sql, (fts_query, limit))
            return [self._row_to_track(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            # Fallback seguro: escapa aspas para tratar a consulta como frase literal
            escaped = cleaned.replace('"', '""')
            try:
                cursor = self.conn.execute(sql, (f'"{escaped}"', limit))
                return [self._row_to_track(row) for row in cursor.fetchall()]
            except sqlite3.OperationalError:
                return []

    def search_combined(
        self,
        query: Optional[str] = None,
        genre: Optional[str] = None,
        min_bpm: Optional[float] = None,
        max_bpm: Optional[float] = None,
        limit: int = 50,
    ) -> List[Track]:
        """Busca híbrida combinando pesquisa textual (FTS5) e filtros numéricos/relacionais.
        
        Demonstra o poder de unir tabelas relacionais com índices invertidos.
        """
        conditions: List[str] = []
        params: List[Any] = []
        join_clause = ""
        order_clause = "ORDER BY t.artist, t.title"

        if query and query.strip():
            cleaned = query.strip()
            fts_query = cleaned
            if not any(token in cleaned for token in ["*", '"', "AND", "OR", "NOT", "NEAR"]):
                words = cleaned.split()
                fts_query = " ".join(f"{w}*" for w in words)
            
            join_clause = "JOIN tracks_fts fts ON t.rowid = fts.rowid"
            conditions.append("tracks_fts MATCH ?")
            params.append(fts_query)
            order_clause = "ORDER BY fts.rank"

        if genre:
            conditions.append("LOWER(t.genre) = LOWER(?)")
            params.append(genre)

        if min_bpm is not None:
            conditions.append("t.bpm >= ?")
            params.append(min_bpm)

        if max_bpm is not None:
            conditions.append("t.bpm <= ?")
            params.append(max_bpm)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
        SELECT t.*
        FROM tracks t
        {join_clause}
        {where_clause}
        {order_clause}
        LIMIT ?;
        """
        params.append(limit)

        try:
            cursor = self.conn.execute(sql, params)
            return [self._row_to_track(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            return []

    # ------------------------------------------------------------------
    # Acoustic analysis persistence (ADR 0014)
    # ------------------------------------------------------------------

    @staticmethod
    def _path_filter(path_prefix: Optional[str], params: Dict[str, Any]) -> str:
        if not path_prefix:
            return ""
        norm_prefix = path_prefix.replace("\\", "/").rstrip("/")
        # '%' and '_' are LIKE wildcards: escape them so '/music/my_band' cannot match '/music/myXband'.
        escaped = norm_prefix.replace("!", "!!").replace("%", "!%").replace("_", "!_")
        params["path_exact"] = norm_prefix
        params["path_like"] = f"{escaped}/%"
        return (
            " AND (replace(t.file_path, '\\', '/') = :path_exact"
            " OR replace(t.file_path, '\\', '/') LIKE :path_like ESCAPE '!')"
        )

    def get_tracks_pending_analysis(
        self,
        path_prefix: Optional[str] = None,
        force: bool = False,
        limit: Optional[int] = None,
        track_ids: Optional[List[str]] = None,
    ) -> List[Track]:
        """AVAILABLE tracks without a current analysis (or all of them when force=True).

        Pure SQL over catalog stamps: no filesystem access, so it is instant even for very
        large libraries. ERROR records count as current (a corrupt file is not retried on
        every run) until the file changes, the analysis version is bumped, or force=True.
        """
        params: Dict[str, Any] = {"version": ANALYSIS_VERSION}
        where = "t.status = 'AVAILABLE'"
        if not force:
            where += f" AND NOT ({_ANALYSIS_IS_CURRENT})"
        where += self._path_filter(path_prefix, params)
        if track_ids is not None:
            if not track_ids:
                return []
            keys = []
            for idx, tid in enumerate(track_ids):
                params[f"id{idx}"] = tid
                keys.append(f":id{idx}")
            where += f" AND t.id IN ({', '.join(keys)})"
        sql = f"""
        SELECT t.* FROM tracks t
        LEFT JOIN track_analysis a ON a.track_id = t.id
        WHERE {where}
        ORDER BY t.artist, t.album, t.title
        """
        if limit is not None:
            sql += " LIMIT :limit"
            params["limit"] = int(limit)
        cursor = self.conn.execute(sql, params)
        return [self._row_to_track(row) for row in cursor.fetchall()]

    def count_pending_analysis(self, path_prefix: Optional[str] = None) -> int:
        params: Dict[str, Any] = {"version": ANALYSIS_VERSION}
        sql = f"""
        SELECT COUNT(*) FROM tracks t
        LEFT JOIN track_analysis a ON a.track_id = t.id
        WHERE t.status = 'AVAILABLE' AND NOT ({_ANALYSIS_IS_CURRENT}){self._path_filter(path_prefix, params)}
        """
        return int(self.conn.execute(sql, params).fetchone()[0])

    def get_analysis_counts(self) -> Dict[str, int]:
        """Counts AVAILABLE tracks by analysis state: available / analyzed / failed / pending."""
        sql = f"""
        SELECT
            COUNT(*) AS available,
            COALESCE(SUM(CASE WHEN ({_ANALYSIS_IS_CURRENT}) AND a.status = 'OK' THEN 1 ELSE 0 END), 0) AS analyzed,
            COALESCE(SUM(CASE WHEN ({_ANALYSIS_IS_CURRENT}) AND a.status = 'ERROR' THEN 1 ELSE 0 END), 0) AS failed
        FROM tracks t
        LEFT JOIN track_analysis a ON a.track_id = t.id
        WHERE t.status = 'AVAILABLE'
        """
        row = self.conn.execute(sql, {"version": ANALYSIS_VERSION}).fetchone()
        available, analyzed, failed = int(row["available"]), int(row["analyzed"]), int(row["failed"])
        return {
            "available": available,
            "analyzed": analyzed,
            "failed": failed,
            "pending": available - analyzed - failed,
        }

    def save_analyses(self, analyses: List[TrackAnalysis], project_bpm_min_confidence: float = 0.2) -> int:
        """Upserts analysis records in one transaction and projects headline metrics onto 'tracks'.

        The projection keeps /list, /search, FTS filters and the AI agent working on real
        measurements without joins: lufs and musical_key are replaced; bpm is replaced only
        when a tempo was detected with enough confidence (otherwise the tag value stays).
        Records whose track disappeared meanwhile are skipped. Returns rows written.
        """
        from musicmatch.dsp.waveform import quantize

        sql = """
        INSERT OR REPLACE INTO track_analysis (
            track_id, analysis_version, status, error_message, analyzed_at,
            source_mtime, source_size, decoder, duration_seconds, sample_rate, channels,
            integrated_lufs, loudness_range_lu, sample_peak_dbfs, bpm, bpm_confidence,
            musical_key, camelot_key, key_confidence, tuning_cents,
            fingerprint_algorithm, fingerprint_hash, fingerprint_frames, fingerprint,
            waveform_peaks, waveform_rms, processing_ms
        ) VALUES (?, ?, ?, ?, COALESCE(?, datetime('now')), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        written = 0
        with self.conn:
            for a in analyses:
                exists = self.conn.execute("SELECT 1 FROM tracks WHERE id = ?;", (a.track_id,)).fetchone()
                if not exists:
                    continue
                f = a.features
                self.conn.execute(
                    sql,
                    (
                        a.track_id, a.analysis_version, a.status, a.error_message, a.analyzed_at,
                        a.source_mtime, a.source_size,
                        f.decoder if f else None,
                        f.duration_seconds if f else None,
                        f.sample_rate if f else None,
                        f.channels if f else None,
                        f.integrated_lufs if f else None,
                        f.loudness_range_lu if f else None,
                        f.sample_peak_dbfs if f else None,
                        f.bpm if f else None,
                        f.bpm_confidence if f else None,
                        f.musical_key if f else None,
                        f.camelot_key if f else None,
                        f.key_confidence if f else None,
                        f.tuning_cents if f else None,
                        f.fingerprint_algorithm if f else None,
                        f.fingerprint_hash if f else None,
                        f.fingerprint_frames if f else None,
                        f.fingerprint if f else None,
                        quantize(f.waveform_peaks) if f else None,
                        quantize(f.waveform_rms) if f else None,
                        f.processing_ms if f else None,
                    ),
                )
                if a.status == "OK" and f is not None:
                    projected_bpm = f.bpm if (f.bpm and f.bpm_confidence >= project_bpm_min_confidence) else None
                    self.conn.execute(
                        """
                        UPDATE tracks SET
                            lufs = ?,
                            musical_key = ?,
                            bpm = COALESCE(?, bpm),
                            updated_at = datetime('now')
                        WHERE id = ?;
                        """,
                        (f.integrated_lufs, f.musical_key, projected_bpm, a.track_id),
                    )
                written += 1
        return written

    def _row_to_analysis(self, row: sqlite3.Row) -> TrackAnalysis:
        from musicmatch.dsp.waveform import dequantize

        features = None
        if row["status"] == "OK" and row["decoder"]:
            features = AudioFeatures(
                duration_seconds=row["duration_seconds"] or 0.0,
                sample_rate=row["sample_rate"],
                channels=row["channels"],
                decoder=row["decoder"],
                integrated_lufs=row["integrated_lufs"],
                loudness_range_lu=row["loudness_range_lu"],
                sample_peak_dbfs=row["sample_peak_dbfs"],
                bpm=row["bpm"],
                bpm_confidence=row["bpm_confidence"] or 0.0,
                musical_key=row["musical_key"],
                camelot_key=row["camelot_key"],
                key_confidence=row["key_confidence"],
                tuning_cents=row["tuning_cents"],
                fingerprint_algorithm=row["fingerprint_algorithm"] or "",
                fingerprint_hash=row["fingerprint_hash"],
                fingerprint_frames=row["fingerprint_frames"] or 0,
                fingerprint=row["fingerprint"],
                waveform_peaks=dequantize(row["waveform_peaks"]),
                waveform_rms=dequantize(row["waveform_rms"]),
                processing_ms=row["processing_ms"] or 0.0,
            )
        return TrackAnalysis(
            track_id=row["track_id"],
            status=row["status"],
            error_message=row["error_message"],
            analysis_version=row["analysis_version"],
            analyzed_at=row["analyzed_at"],
            source_mtime=row["source_mtime"],
            source_size=row["source_size"],
            features=features,
        )

    def get_analysis(self, track_id: str) -> Optional[TrackAnalysis]:
        row = self.conn.execute("SELECT * FROM track_analysis WHERE track_id = ?;", (track_id,)).fetchone()
        return self._row_to_analysis(row) if row else None

    def get_fingerprint_records(self, algorithm: str) -> List[Dict[str, Any]]:
        """Successful fingerprints of the given algorithm: track_id, duration, hash and blob."""
        sql = """
        SELECT a.track_id, a.duration_seconds, a.fingerprint_hash, a.fingerprint
        FROM track_analysis a
        JOIN tracks t ON t.id = a.track_id
        WHERE a.status = 'OK' AND a.fingerprint_algorithm = ? AND a.fingerprint_hash IS NOT NULL
        ORDER BY a.track_id;
        """
        return [dict(row) for row in self.conn.execute(sql, (algorithm,)).fetchall()]

    def get_fingerprinted_track_ids(self, algorithm: str) -> set[str]:
        """IDs of the tracks with a successful fingerprint of the given algorithm."""
        sql = """
        SELECT track_id FROM track_analysis
        WHERE status = 'OK' AND fingerprint_algorithm = ? AND fingerprint_hash IS NOT NULL;
        """
        return {row["track_id"] for row in self.conn.execute(sql, (algorithm,)).fetchall()}

    def get_exact_fingerprint_groups(self, algorithm: str) -> List[List[Dict[str, Any]]]:
        """Groups (size >= 2) of tracks sharing an identical fingerprint hash (indexed GROUP BY)."""
        sql = """
        SELECT a.track_id, a.duration_seconds, a.fingerprint_hash
        FROM track_analysis a
        JOIN tracks t ON t.id = a.track_id
        WHERE a.status = 'OK' AND a.fingerprint_algorithm = ? AND a.fingerprint_hash IN (
            SELECT fingerprint_hash FROM track_analysis
            WHERE status = 'OK' AND fingerprint_algorithm = ? AND fingerprint_hash IS NOT NULL
            GROUP BY fingerprint_hash HAVING COUNT(*) > 1
        )
        ORDER BY a.fingerprint_hash, a.duration_seconds, a.track_id;
        """
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for row in self.conn.execute(sql, (algorithm, algorithm)).fetchall():
            groups.setdefault(row["fingerprint_hash"], []).append(dict(row))
        return list(groups.values())

    def count(self) -> int:
        """Retorna o número total de faixas registradas."""
        cursor = self.conn.execute("SELECT COUNT(*) FROM tracks;")
        return cursor.fetchone()[0]

    def clear(self) -> None:
        """Remove todos os registros da biblioteca.
        
        Os triggers excluem automaticamente as entradas correspondentes no FTS5.
        """
        with self.conn:
            self.conn.execute("DELETE FROM tracks;")

    def get_stats(self) -> Dict[str, Any]:
        """Calcula estatísticas agregadas da biblioteca."""
        sql = """
        SELECT
            COUNT(*) as total_tracks,
            COALESCE(SUM(duration_seconds), 0) as total_duration,
            COALESCE(AVG(bpm), 0) as avg_bpm,
            COALESCE(AVG(bitrate_kbps), 0) as avg_bitrate
        FROM tracks;
        """
        cursor = self.conn.execute(sql)
        row = cursor.fetchone()

        db_size_bytes = 0
        if self.db_path != ":memory:" and os.path.exists(self.db_path):
            db_size_bytes = os.path.getsize(self.db_path)
        total_plays_row = self.conn.execute(
            "SELECT value FROM playback_stats WHERE key = 'total_plays';"
        ).fetchone()

        return {
            "total_tracks": row["total_tracks"],
            "total_duration_hours": round(row["total_duration"] / 3600, 2),
            "avg_bpm": round(row["avg_bpm"], 1),
            "avg_bitrate_kbps": int(row["avg_bitrate"]),
            "db_path": self.db_path,
            "db_size_kb": round(db_size_bytes / 1024, 2),
            "total_plays": int(total_plays_row["value"]) if total_plays_row else 0,
        }

    def close(self) -> None:
        """Fecha a conexão com o banco de dados."""
        if hasattr(self, "conn") and self.conn:
            try:
                self.conn.close()
            except Exception:
                pass

    def __enter__(self) -> "SQLiteTrackRepository":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()
