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
5. Varredura Rápida, Análise Separada (ADR 0014):
   - O scanner lê apenas tags e 'os.stat'; a decodificação do áudio (LUFS, BPM, tonalidade,
     fingerprint) acontece no passo incremental e retomável '/analyze'.
"""

import logging
import os
import re
import time
from pathlib import Path
from typing import List, Optional, Set

import mediafile
from musicmatch.diagnostics.logging_setup import log_unexpected
from musicmatch.domain.issues import IssueKind
from musicmatch.domain.models import ScanResult, Track
from musicmatch.services.issues import report_issue
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository

logger = logging.getLogger(__name__)

# Name checks (ADR 0019): a library must survive being copied to another system or drive.
WINDOWS_MAX_PATH = 260  # classic Win32 limit (including the terminating NUL): 259 usable characters
_NOT_PORTABLE_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def printable_path(path: str) -> str:
    """A path safe to store and show: bytes that are not valid UTF-8 become '\\xNN' escapes."""
    return path.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")


def name_problem(name: str) -> Optional[str]:
    """Why a file or folder name is not portable across Windows, macOS and Linux (None if it is)."""
    if any("\udc80" <= c <= "\udcff" for c in name):
        return "o nome contém bytes que não são UTF-8 válido"
    if _NOT_PORTABLE_CHARS.search(name):
        return 'o nome contém caracteres proibidos no Windows (< > : " | ? * ou de controle)'
    if name != name.rstrip(" ."):
        return "o nome termina com espaço ou ponto (o Windows os remove)"
    if name.split(".")[0].upper() in _RESERVED_NAMES:
        return f"'{name.split('.')[0]}' é um nome reservado de dispositivo no Windows"
    return None

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

_SUGGESTIONS = {
    IssueKind.FILE_UNREADABLE: "Verifique permissões e o disco; depois rode /scan novamente.",
    IssueKind.FILE_EMPTY: "Baixe ou copie o arquivo de novo, ou apague-o.",
    IssueKind.AUDIO_EMPTY: "Ouça a faixa; se estiver vazia ou cortada, substitua o arquivo.",
    IssueKind.TAGS_UNREADABLE: "O arquivo pode estar corrompido ou ter a extensão errada; substitua-o.",
    IssueKind.NAME_NOT_PORTABLE: "Renomeie o arquivo e rode /scan novamente.",
    IssueKind.PATH_TOO_LONG: "Encurte nomes de pastas/arquivos ou mova a pasta para perto da raiz do disco.",
}


class AudioScanner:
    """Motor de descoberta, leitura de metadados e persistência idempotente de arquivos de áudio."""

    def __init__(self, repository: SQLiteTrackRepository) -> None:
        self.repo = repository

    @staticmethod
    def _report_file(kind: IssueKind, path: Path, message: str, label: Optional[str] = None) -> None:
        report_issue(kind, printable_path(str(path)), message, subject_type="file", subject_label=label,
                     source="scan", details={"sugestão": _SUGGESTIONS.get(kind, "")} if kind in _SUGGESTIONS else None)

    def _names_ok(self, path: Path, root: Path, checked_dirs: Set[str]) -> bool:
        """Reports names that are not portable (per folder once per scan, and per file) and paths
        over the Windows limit. Returns False only when the name cannot even be stored: bytes that
        are not valid UTF-8 (the file stays out of the catalog until renamed)."""
        try:
            parts = path.relative_to(root).parts
        except ValueError:
            parts = (path.name,)
        folder = root
        for part in parts[:-1]:
            folder = folder / part
            key = str(folder)
            if key in checked_dirs:
                continue
            checked_dirs.add(key)
            problem = name_problem(part)
            if problem:
                report_issue(IssueKind.NAME_NOT_PORTABLE, printable_path(key), f"Pasta: {problem}.",
                             subject_type="directory", source="scan",
                             details={"sugestão": "Renomeie a pasta e rode /scan novamente."})
        problem = name_problem(path.name)
        if problem:
            self._report_file(IssueKind.NAME_NOT_PORTABLE, path, f"Arquivo: {problem}.")
        length = len(str(path))
        if length >= WINDOWS_MAX_PATH:
            self._report_file(IssueKind.PATH_TOO_LONG, path,
                              f"O caminho tem {length} caracteres; programas Windows comuns aceitam até {WINDOWS_MAX_PATH - 1}.")
        stored = printable_path(str(path))
        return stored == str(path)  # surrogates (invalid UTF-8 bytes) cannot go into SQLite

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
        checked_dirs: Set[str] = set()
        for p in found_audio_paths:
            if not self._names_ok(p, target_path, checked_dirs):
                errors_count += 1  # cannot be stored in the catalog (issue registered)
                continue
            try:
                stat = p.stat()
            except OSError as exc:
                errors_count += 1
                self._report_file(IssueKind.FILE_UNREADABLE, p, f"Não foi possível ler o arquivo: {exc.strerror or exc}")
                continue
            if stat.st_size == 0:
                errors_count += 1
                self._report_file(IssueKind.FILE_EMPTY, p, "O arquivo tem 0 bytes: não contém áudio.")
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
                bpm, bpm_source = Track.bpm_from_tag(mf.bpm)
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
                    bpm_source=bpm_source,
                    file_path=str(p.resolve()).replace("\\", "/"),
                    file_mtime=stat.st_mtime,
                    file_size=stat.st_size,
                    status="AVAILABLE",
                    year=year,
                    track_number=track_num,
                )
                if canonical in stat_cache:
                    tracks_to_persist.append(track)
                    tracks_updated += 1
                else:
                    # Heurística de Fast Relocation Match (ADR 0009): verifica se o arquivo foi movido/renomeado
                    candidate = self.repo.find_relocation_candidate(
                        file_size=track.file_size,
                        duration_seconds=track.duration_seconds,
                        title=track.title,
                        artist=track.artist,
                    )
                    if candidate:
                        self.repo.relocate_track(candidate.id, track)
                        tracks_updated += 1
                    else:
                        tracks_to_persist.append(track)
                        tracks_added += 1

                if len(sample_tracks) < 5:
                    sample_tracks.append(f"{artist} - {title} ({genre})")
                if duration <= 0:
                    self._report_file(IssueKind.AUDIO_EMPTY, p,
                                      "A faixa foi indexada, mas sem duração: o áudio pode estar vazio ou truncado.",
                                      label=f"{artist} - {title}")

            except mediafile.UnreadableFileError as exc:
                errors_count += 1
                self._report_file(IssueKind.TAGS_UNREADABLE, p, f"Não foi possível ler o arquivo de áudio: {exc}")
            except OSError as exc:
                errors_count += 1
                self._report_file(IssueKind.FILE_UNREADABLE, p, f"Não foi possível ler o arquivo: {exc.strerror or exc}")
            except Exception as exc:  # unforeseen: a bug, not a bad file (developer log)
                errors_count += 1
                log_unexpected(f"Unexpected error scanning {printable_path(str(p))!r}", exc)

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

        # The scan never decodes audio (ADR 0014): acoustic analysis is a separate, resumable
        # /analyze pass. Report how many tracks in this directory still need it.
        resolved_root = str(target_path.resolve()).replace("\\", "/")
        tracks_pending_analysis = self.repo.count_pending_analysis(resolved_root)

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
            tracks_pending_analysis=tracks_pending_analysis,
            sample_tracks=sample_tracks,
            duration_ms=elapsed_ms,
            database_total_tracks=self.repo.count(),
        )
