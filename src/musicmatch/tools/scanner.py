"""Ferramentas de Ingestão e Varredura de Áudio."""

from typing import Any, Dict, Optional
from musicmatch.services.library import LibraryService, library_service

def scan_library(
    path: str,
    recursive: bool = True,
    service: Optional[LibraryService] = None,
) -> Dict[str, Any]:
    """Varre um diretório local em busca de arquivos de áudio (MP3/FLAC/WAV), extrai metadados e popula a biblioteca.

    Esta ferramenta deve ser chamada sempre que o usuário solicitar indexar, escanear,
    adicionar ou atualizar arquivos de música a partir de uma pasta ou disco local.

    Args:
        path: Caminho absoluto ou relativo do diretório a ser varrido (ex: 'C:/Musicas' ou 'D:/Audio/Albuns').
        recursive: Se True, percorre todas as subpastas recursivamente. Padrão é True.
        service: Instância opcional da camada de serviços (LibraryService) para injeção de dependência.

    Returns:
        Um dicionário serializado do modelo Pydantic ScanResult contendo o status da operação,
        total de faixas indexadas e uma amostra dos títulos adicionados.
    """
    svc = service or library_service
    scan_result = svc.scan_and_ingest(path=path, recursive=recursive)
    return scan_result.model_dump()
