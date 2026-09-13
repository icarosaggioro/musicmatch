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
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "data" / "musicmatch.db"))
    STAGING_DIR: str = os.getenv("MUSICMATCH_STAGING_DIR", str(PROJECT_ROOT / "data" / "staging"))
    MANAGED_LIBRARY_DIR: str = os.getenv("MUSICMATCH_LIBRARY_DIR", "")
    DOWNLOAD_DEFAULT_FORMAT: str = os.getenv("DOWNLOAD_DEFAULT_FORMAT", "native")
    DOWNLOAD_MAX_DURATION_SECONDS: int = int(os.getenv("DOWNLOAD_MAX_DURATION_SECONDS", "1800"))
    DOWNLOAD_PLAYLIST_MAX_TRACKS: int = int(os.getenv("DOWNLOAD_PLAYLIST_MAX_TRACKS", "50"))

settings = Settings()
