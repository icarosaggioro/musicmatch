"""Motor de Varredura e Ingestão de Áudio (AudioScanner) com mediafile e ADR 0009.

CONCEITO ARQUITETURAL DIDÁTICO:
--------------------------------
1. Idempotência e Stat-Cache (ADR 0009):
   - Evita reprocessar arquivos idênticos inspecionando 'os.stat' (mtime e size) em O(1).
   - Re-varreduras de grandes bibliotecas acontecem em milissegundos sem abrir streams de áudio.
2. Camada Unificada de Tags (mediafile):
   - Suporte unificado a MP3, FLAC, M4A, OGG, WAV, WMA, AIFF sem código de baixo nível duplicado.
3. Resiliência:
   - Arquivos corrompidos ou com metadados inválidos não interrompem o lote e são contabilizados em 'errors_count'.
4. Ciclo de Vida Não-Destrutivo (Soft-Delete):
   - Arquivos excluídos ou movidos têm seu status alterado para 'MISSING', preservando o histórico do banco.
"""

import os
import time
from pathlib import Path
from typing import List, Optional, Set

import mediafile
from musicmatch.domain.models import ScanResult, Track
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository

SUPPORTED_AUDIO_EXTENSIONS = {
    ".mp3",
    ".flac",
    ".m4a",
    ".aac",
    ".ogg",
    ".wav",
    ".wma",
    ".aiff",
    ".aif",
    ".opus",
}

class AudioScanner:
    """Motor de descoberta, leitura de metadados e persistência idempotente de arquivos de áudio."""

    def __init__(self, repository: SQLiteTrackRepository) -> None:
        self.repo = repository

    def scan_directory(self, path_str: str, recursive: bool = True) -> ScanResult:
        """Executa a varredura completa de um diretório conforme o ADR 0009."""
        start_time = time.perf_counter()
        target_path = Path(path_str)

        if not target_path.exists() or not target_path.is_dir():
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return ScanResult(
                status="error",
                message=f"Diretório '{path_str}' não encontrado ou inacessível no sistema de arquivos.",
                path=path_str,
                recursive=recursive,
                total_files_scanned=0,
                tracks_indexed=0,
                tracks_added=0,
                tracks_updated=0,
                tracks_unchanged=0,
                tracks_missing=0,
                errors_count=0,
                sample_tracks=[],
                duration_ms=elapsed_ms,
                database_total_tracks=self.repo.count(),
            )

        # 1. Descoberta de arquivos suportados
        found_audio_paths: List[Path] = []
        if recursive:
            for root, _, files in os.walk(target_path):
                for file_name in files:
                    ext = os.path.splitext(file_name)[1].lower()
                    if ext in SUPPORTED_AUDIO_EXTENSIONS:
                        found_audio_paths.append(Path(root) / file_name)
        else:
            for item in target_path.iterdir():
                if item.is_file() and item.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
                    found_audio_paths.append(item)

        # 2. Carrega Stat-Cache do banco para o diretório
        stat_cache = self.repo.get_stat_cache_map(str(target_path))

        tracks_to_persist: List[Track] = []
        tracks_added = 0
        tracks_updated = 0
        tracks_unchanged = 0
        errors_count = 0
        found_canonicals: Set[str] = set()
        sample_tracks: List[str] = []

        # 3. Processa cada arquivo
        for p in found_audio_paths:
            try:
                stat = p.stat()
            except OSError:
                errors_count += 1
                continue

            canonical = Track.canonicalize_path(str(p))
            found_canonicals.add(canonical)

            # Avaliação Instantânea do Stat-Cache (O(1))
            if canonical in stat_cache:
                cached_mtime, cached_size, cached_status, _ = stat_cache[canonical]
                if (
                    cached_status == "AVAILABLE"
                    and cached_size == stat.st_size
                    and cached_mtime is not None
                    and abs(cached_mtime - stat.st_mtime) < 1e-4
                ):
                    tracks_unchanged += 1
                    continue

            # Extração de tags via mediafile
            try:
                mf = mediafile.MediaFile(str(p.resolve()))
                title = (mf.title or "").strip() or p.stem
                artist = (mf.artist or "").strip() or "Unknown Artist"
                album = (mf.album or "").strip() or "Unknown Album"
                genre = (mf.genre or "").strip() or "Unknown Genre"
                duration = float(mf.length or 0.0)
                bitrate = int(mf.bitrate / 1000) if (mf.bitrate and mf.bitrate > 0) else 320
                bpm = float(mf.bpm) if (mf.bpm and float(mf.bpm) > 0) else 120.0
                year = int(mf.year) if (mf.year and str(mf.year).isdigit()) else None
                track_num = int(mf.track) if (mf.track and str(mf.track).isdigit()) else None

                track = Track(
                    id=Track.generate_id(str(p)),
                    title=title,
                    artist=artist,
                    album=album,
                    genre=genre,
                    duration_seconds=duration,
                    bitrate_kbps=bitrate,
                    bpm=bpm,
                    file_path=str(p.resolve()).replace("\\", "/"),
                    file_mtime=stat.st_mtime,
                    file_size=stat.st_size,
                    status="AVAILABLE",
                    year=year,
                    track_number=track_num,
                )
                tracks_to_persist.append(track)

                if canonical in stat_cache:
                    tracks_updated += 1
                else:
                    tracks_added += 1

                if len(sample_tracks) < 5:
                    sample_tracks.append(f"{artist} - {title} ({genre})")

            except Exception:
                errors_count += 1
                continue

        # 4. Soft-Delete: arquivos anteriormente indexados que sumiram do disco
        missing_ids: List[str] = []
        for cached_canonical, (_, _, cached_status, cached_id) in stat_cache.items():
            if cached_canonical not in found_canonicals and cached_status == "AVAILABLE":
                missing_ids.append(cached_id)

        tracks_missing = 0
        if missing_ids:
            tracks_missing = self.repo.mark_missing_by_ids(missing_ids)

        # 5. Persistência em lote
        if tracks_to_persist:
            self.repo.insert_batch(tracks_to_persist)

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        total_indexed = tracks_added + tracks_updated

        return ScanResult(
            status="success",
            message=f"Varredura concluída com sucesso no diretório '{path_str}'.",
            path=path_str,
            recursive=recursive,
            total_files_scanned=len(found_audio_paths),
            tracks_indexed=total_indexed,
            tracks_added=tracks_added,
            tracks_updated=tracks_updated,
            tracks_unchanged=tracks_unchanged,
            tracks_missing=tracks_missing,
            errors_count=errors_count,
            sample_tracks=sample_tracks,
            duration_ms=elapsed_ms,
            database_total_tracks=self.repo.count(),
        )
