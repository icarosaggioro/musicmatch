"""Modelos de Domínio do MusicMatch usando Pydantic.

CONCEITO ARQUITETURAL DIDÁTICO:
--------------------------------
Por que migramos de '@dataclass' para 'pydantic.BaseModel'?
1. Validação em Tempo de Execução (Runtime): '@dataclass' aceita qualquer tipo silenciosamente.
   O Pydantic garante que se uma tag de MP3 contiver um texto no lugar do BPM,
   ou se uma taxa de bits for negativa, um erro explicativo ('ValidationError') seja disparado.
2. Coerção Automática de Tipos: O Pydantic converte strings válidas (ex: "128" -> 128 int)
   automaticamente, simplificando a ingestão de metadados de arquivos de áudio.
3. Integração com LLMs (JSON Schema): O método '.model_json_schema()' do Pydantic
   gera a especificação exata necessária para ferramentas do Gemini com descrições semânticas.
"""

import hashlib
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field

class Track(BaseModel):
    """Representa uma faixa musical indexada com seus metadados essenciais e validados."""
    
    id: str = Field(..., description="Identificador único da faixa no catálogo (ex: trk_<sha256>)")
    title: str = Field(..., description="Título da composição musical")
    artist: str = Field(..., description="Nome do artista, banda ou compositor principal")
    album: str = Field(..., description="Nome do álbum de lançamento")
    genre: str = Field(..., description="Gênero musical principal")
    duration_seconds: float = Field(ge=0, description="Duração total em segundos")
    bitrate_kbps: int = Field(gt=0, description="Taxa de bits em kbps (ex: 320)")
    bpm: float = Field(gt=0, description="Batidas por minuto detectadas (BPM)")
    file_path: str = Field(..., description="Caminho absoluto do arquivo no disco local")
    mood: Optional[str] = Field(default=None, description="Humor ou vibe acústica detectada")
    lufs: Optional[float] = Field(default=None, description="Loudness integrado em LUFS segundo a norma EBU R128")
    
    # Campos de Stat-Cache e Ciclo de Vida (ADR 0009)
    file_mtime: Optional[float] = Field(default=None, description="Timestamp de modificação do arquivo no disco")
    file_size: Optional[int] = Field(default=None, ge=0, description="Tamanho do arquivo em bytes")
    status: str = Field(default="AVAILABLE", description="Status de disponibilidade ('AVAILABLE' | 'MISSING')")
    year: Optional[int] = Field(default=None, description="Ano de lançamento extraído das tags")
    track_number: Optional[int] = Field(default=None, description="Número da faixa no álbum")

    @classmethod
    def canonicalize_path(cls, file_path: str) -> str:
        """Padroniza o caminho do arquivo para hash determinístico no Windows/NTFS (ADR 0009)."""
        return str(Path(file_path).resolve()).replace("\\", "/").lower()

    @classmethod
    def generate_id(cls, file_path: str) -> str:
        """Gera um ID imutável e determinístico baseado no hash SHA-256 do caminho canônico."""
        canonical = cls.canonicalize_path(file_path)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"trk_{digest}"

class ScanResult(BaseModel):
    """Resultado consolidado e fortemente tipado de uma operação de varredura/escaneamento."""
    
    status: str = Field(default="success", description="Status da operação (ex: 'success' ou 'error')")
    message: str = Field(..., description="Mensagem resumida para o usuário ou agente")
    path: str = Field(..., description="Diretório varrido no disco")
    recursive: bool = Field(default=True, description="Se a varredura incluiu subdiretórios")
    total_files_scanned: int = Field(ge=0, description="Total de arquivos de áudio processados")
    tracks_indexed: int = Field(ge=0, description="Total de faixas inseridas/atualizadas com sucesso no banco")
    tracks_added: int = Field(default=0, ge=0, description="Total de novas faixas inseridas")
    tracks_updated: int = Field(default=0, ge=0, description="Total de faixas modificadas e atualizadas")
    tracks_unchanged: int = Field(default=0, ge=0, description="Total de faixas inalteradas puladas via Stat-Cache")
    tracks_missing: int = Field(default=0, ge=0, description="Total de faixas catalogadas anteriormente ausentes no disco")
    errors_count: int = Field(default=0, ge=0, description="Total de arquivos corrompidos ou ilegíveis")
    sample_tracks: List[str] = Field(default_factory=list, description="Amostra descritiva das faixas adicionadas")
    duration_ms: float = Field(ge=0, description="Tempo decorrido na varredura em milissegundos")
    database_total_tracks: int = Field(ge=0, description="Contagem total acumulada no banco de dados")

