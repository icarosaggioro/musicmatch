"""Serviço de Negócios da Biblioteca de Música (LibraryService).

CONCEITO ARQUITETURAL DIDÁTICO:
--------------------------------
A 'Camada de Serviços' (Service Layer / Application Service) define os limites da aplicação
e estabelece o conjunto de operações/casos de uso que o sistema oferece para o mundo externo.

Por que não deixar os comandos do Harness ou as ferramentas de IA chamarem o SQL diretamente?
1. Desacoplamento e Regras de Negócio: Se amanhã decidirmos que antes de inserir uma faixa
   devemos calcular um hash acústico, normalizar o nome do artista ou disparar um evento,
   essa lógica fica centralizada no 'LibraryService'. O Harness e os Agentes de IA continuam
   intactos.
2. Independência de Framework: O 'LibraryService' é agnóstico se quem o chamou foi um script CLI,
   uma ferramenta do Gemini, um endpoint FastAPI ou um WebSocket de uma interface gráfica.
3. Testabilidade com Injeção de Dependências: O serviço recebe o repositório ('SQLiteTrackRepository')
   no construtor. Em testes, injetamos um banco em memória ':memory:', garantindo testes rápidos
   e 100% isolados.
"""

import time
from typing import Any, Dict, List, Optional
from musicmatch.domain.models import ScanResult, Track
from musicmatch.services.scanner import AudioScanner
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository

class LibraryService:
    """Orquestrador dos casos de uso da biblioteca musical do MusicMatch."""

    def __init__(self, repository: Optional[SQLiteTrackRepository] = None) -> None:
        self.repo = repository or SQLiteTrackRepository()
        self.scanner = AudioScanner(repository=self.repo)

    def add_track(self, track: Track) -> Track:
        """Adiciona uma nova faixa à biblioteca após validar e persistir."""
        self.repo.insert_track(track)
        return track

    def add_tracks_batch(self, tracks: List[Track]) -> int:
        """Adiciona múltiplas faixas em uma operação atômica de lote."""
        return self.repo.insert_batch(tracks)

    def update_track(self, track: Track) -> bool:
        """Atualiza os metadados de uma faixa existente na biblioteca."""
        return self.repo.update_track(track)

    def delete_track(self, track_id: str) -> bool:
        """Remove uma faixa da biblioteca pelo seu ID."""
        return self.repo.delete_track(track_id)

    def get_track(self, track_id: str) -> Optional[Track]:
        """Recupera uma faixa pelo seu ID."""
        return self.repo.get_track_by_id(track_id)

    def get_track_by_path(self, file_path: str) -> Optional[Track]:
        """Recupera uma faixa pelo seu caminho de arquivo."""
        return self.repo.get_track_by_path(file_path)

    def get_all_tracks(self, limit: Optional[int] = None, offset: int = 0) -> List[Track]:
        """Retorna todas as faixas cadastradas no acervo com suporte a paginação."""
        return self.repo.get_all_tracks(limit=limit, offset=offset)

    def search_tracks(
        self,
        query: Optional[str] = None,
        genre: Optional[str] = None,
        min_bpm: Optional[float] = None,
        max_bpm: Optional[float] = None,
        limit: int = 50,
    ) -> List[Track]:
        """Executa busca híbrida avançada (FTS5 + filtros numéricos)."""
        return self.repo.search_combined(
            query=query,
            genre=genre,
            min_bpm=min_bpm,
            max_bpm=max_bpm,
            limit=limit,
        )

    def scan_and_ingest(self, path: str, recursive: bool = True) -> ScanResult:
        """Executa a varredura e ingestão real de arquivos de áudio locais via AudioScanner."""
        return self.scanner.scan_directory(path_str=path, recursive=recursive)

    def count_tracks(self) -> int:
        """Retorna o número total de faixas na biblioteca."""
        return self.repo.count()

    def clear_library(self) -> None:
        """Remove todos os registros da biblioteca."""
        self.repo.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Obtém dados estatísticos e de integridade do acervo."""
        return self.repo.get_stats()

# Instância padrão de serviço de biblioteca
library_service = LibraryService()
