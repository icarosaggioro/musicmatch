"""Módulo de Configuração e Variáveis de Ambiente."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega o arquivo .env a partir da raiz do projeto
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

class Settings:
    """Configurações globais da aplicação."""
    
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    # Developer log (ADR 0019): unforeseen errors with tracebacks, rotating text file.
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR: str = os.getenv("MUSICMATCH_LOG_DIR", "").strip() or str(PROJECT_ROOT / "data" / "logs")
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "data" / "musicmatch.db"))
    STAGING_DIR: str = os.getenv("MUSICMATCH_STAGING_DIR", str(PROJECT_ROOT / "data" / "staging"))
    MANAGED_LIBRARY_DIR: str = os.getenv("MUSICMATCH_LIBRARY_DIR", "")
    # Where /library set-path persists the chosen Managed Library Directory (ADR 0012).
    LIBRARY_CONFIG_PATH: str = os.getenv("MUSICMATCH_LIBRARY_CONFIG", "").strip() or str(
        PROJECT_ROOT / "data" / "library_config.json"
    )
    DOWNLOAD_DEFAULT_FORMAT: str = os.getenv("DOWNLOAD_DEFAULT_FORMAT", "native")
    DOWNLOAD_MAX_DURATION_SECONDS: int = int(os.getenv("DOWNLOAD_MAX_DURATION_SECONDS", "1800"))
    DOWNLOAD_PLAYLIST_MAX_TRACKS: int = int(os.getenv("DOWNLOAD_PLAYLIST_MAX_TRACKS", "50"))
    # Acoustic analysis (ADR 0014): explicit FFmpeg binary (empty = discover on PATH) and
    # parallel worker count (0 = automatic, based on CPU count).
    FFMPEG_PATH: str = os.getenv("MUSICMATCH_FFMPEG_PATH", "")
    ANALYSIS_WORKERS: int = int(os.getenv("MUSICMATCH_ANALYSIS_WORKERS", "0"))
    # Playback (ADR 0015): force a miniaudio output backend (wasapi, dsound, winmm, coreaudio,
    # pulseaudio, alsa, jack, null); empty = automatic selection for the platform.
    AUDIO_BACKEND: str = os.getenv("MUSICMATCH_AUDIO_BACKEND", "")
    # Play counting (ADR 0016): a play counts after this many seconds of actual listening
    # (shorter tracks count when heard to the end).
    PLAY_COUNT_SECONDS: float = float(os.getenv("MUSICMATCH_PLAY_COUNT_SECONDS", "60"))
    # Issues (ADR 0019): dismissed issues not seen again for this many days are purged at startup.
    ISSUE_RETENTION_DAYS: int = int(os.getenv("MUSICMATCH_ISSUE_RETENTION_DAYS", "180"))

settings = Settings()
