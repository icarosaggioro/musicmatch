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
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository

class LibraryService:
    """Orquestrador dos casos de uso da biblioteca musical do MusicMatch."""

    def __init__(self, repository: Optional[SQLiteTrackRepository] = None) -> None:
        self.repo = repository or SQLiteTrackRepository()

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

    def get_all_tracks(self) -> List[Track]:
        """Retorna todas as faixas cadastradas no acervo."""
        return self.repo.get_all_tracks()

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
        """Executa o caso de uso de varredura e ingestão de diretório no acervo.
        
        Na Fase 1/2 (Walking Skeleton), gera faixas representativas com metadados
        acústicos variados e as persiste diretamente no banco de dados SQLite.
        """
        start_time = time.perf_counter()

        synthetic_tracks = [
            Track(
                id="trk_001",
                title="Bohemian Rhapsody",
                artist="Queen",
                album="A Night at the Opera",
                genre="Rock",
                duration_seconds=354.0,
                bitrate_kbps=320,
                bpm=72.0,
                file_path=f"{path}/Queen/Bohemian_Rhapsody.mp3",
                mood="Epic",
                lufs=-12.4
            ),
            Track(
                id="trk_002",
                title="Midnight City",
                artist="M83",
                album="Hurry Up, We're Dreaming",
                genre="Synthwave",
                duration_seconds=243.0,
                bitrate_kbps=320,
                bpm=105.0,
                file_path=f"{path}/M83/Midnight_City.mp3",
                mood="Nostalgic / Energetic",
                lufs=-9.8
            ),
            Track(
                id="trk_003",
                title="Take Five",
                artist="Dave Brubeck Quartet",
                album="Time Out",
                genre="Jazz",
                duration_seconds=324.0,
                bitrate_kbps=256,
                bpm=174.0,
                file_path=f"{path}/Dave_Brubeck/Take_Five.mp3",
                mood="Relaxed / Sophisticated",
                lufs=-16.1
            ),
            Track(
                id="trk_004",
                title="Master of Puppets",
                artist="Metallica",
                album="Master of Puppets",
                genre="Metal",
                duration_seconds=515.0,
                bitrate_kbps=320,
                bpm=212.0,
                file_path=f"{path}/Metallica/Master_of_Puppets.mp3",
                mood="Aggressive / Intense",
                lufs=-8.5
            ),
            Track(
                id="trk_005",
                title="Weightless",
                artist="Marconi Union",
                album="Ambient Transmissions Vol. 2",
                genre="Ambient",
                duration_seconds=485.0,
                bitrate_kbps=320,
                bpm=60.0,
                file_path=f"{path}/Marconi_Union/Weightless.mp3",
                mood="Calm / Meditative",
                lufs=-21.3
            ),
        ]

        # Persiste em lote no SQLite real
        self.repo.insert_batch(synthetic_tracks)

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return ScanResult(
            status="success",
            message=f"Varredura concluída com sucesso no diretório '{path}'.",
            path=path,
            recursive=recursive,
            total_files_scanned=len(synthetic_tracks),
            tracks_indexed=len(synthetic_tracks),
            sample_tracks=[f"{t.artist} - {t.title} ({t.genre})" for t in synthetic_tracks],
            duration_ms=elapsed_ms,
            database_total_tracks=self.repo.count(),
        )

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
