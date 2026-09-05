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
from musicmatch.domain.models import Track
from musicmatch.storage.schema import ALL_SCHEMA_STATEMENTS

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
        """Executa as instruções DDL para criar tabelas e triggers caso não existam."""
        with self.conn:
            for statement in ALL_SCHEMA_STATEMENTS:
                self.conn.execute(statement)

    def _row_to_track(self, row: sqlite3.Row) -> Track:
        """Converte uma linha do SQLite (sqlite3.Row) para uma entidade Pydantic Track."""
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
            mood=row["mood"],
            lufs=row["lufs"],
        )

    def insert_track(self, track: Track) -> None:
        """Insere uma única faixa no banco de dados.
        
        Os triggers do SQLite sincronizam automaticamente a tabela 'tracks_fts'.
        """
        sql = """
        INSERT INTO tracks (
            id, title, artist, album, genre, duration_seconds,
            bitrate_kbps, bpm, file_path, mood, lufs
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self.conn:
            self.conn.execute(
                sql,
                (
                    track.id, track.title, track.artist, track.album,
                    track.genre, track.duration_seconds, track.bitrate_kbps,
                    track.bpm, track.file_path, track.mood, track.lufs
                )
            )

    def insert_batch(self, tracks: List[Track]) -> int:
        """Insere uma lista de faixas em lote dentro de uma única transação."""
        if not tracks:
            return 0

        sql = """
        INSERT OR REPLACE INTO tracks (
            id, title, artist, album, genre, duration_seconds,
            bitrate_kbps, bpm, file_path, mood, lufs
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        data = [
            (
                t.id, t.title, t.artist, t.album, t.genre,
                t.duration_seconds, t.bitrate_kbps, t.bpm,
                t.file_path, t.mood, t.lufs
            )
            for t in tracks
        ]
        with self.conn:
            self.conn.executemany(sql, data)
        return len(tracks)

    def update_track(self, track: Track) -> bool:
        """Atualiza os metadados de uma faixa existente.
        
        O trigger 'trg_tracks_au' atualiza o índice FTS5 automaticamente.
        """
        sql = """
        UPDATE tracks SET
            title = ?, artist = ?, album = ?, genre = ?,
            duration_seconds = ?, bitrate_kbps = ?, bpm = ?,
            file_path = ?, mood = ?, lufs = ?, updated_at = datetime('now')
        WHERE id = ?;
        """
        with self.conn:
            cursor = self.conn.execute(
                sql,
                (
                    track.title, track.artist, track.album, track.genre,
                    track.duration_seconds, track.bitrate_kbps, track.bpm,
                    track.file_path, track.mood, track.lufs, track.id
                )
            )
            return cursor.rowcount > 0

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

    def get_track_by_path(self, file_path: str) -> Optional[Track]:
        """Recupera uma faixa pelo caminho do arquivo no disco."""
        cursor = self.conn.execute("SELECT * FROM tracks WHERE file_path = ?;", (file_path,))
        row = cursor.fetchone()
        return self._row_to_track(row) if row else None

    def get_all_tracks(self) -> List[Track]:
        """Retorna todas as faixas ordenadas por Artista, Álbum e Título."""
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

        return {
            "total_tracks": row["total_tracks"],
            "total_duration_hours": round(row["total_duration"] / 3600, 2),
            "avg_bpm": round(row["avg_bpm"], 1),
            "avg_bitrate_kbps": int(row["avg_bitrate"]),
            "db_path": self.db_path,
            "db_size_kb": round(db_size_bytes / 1024, 2),
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
