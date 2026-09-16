"""Status Command (/status).

Displays system operational status, active Gemini model, storage backend, and library statistics.
"""

from typing import List

from musicmatch.commands.base import Command, CommandContext
from musicmatch.config import settings


class StatusCommand(Command):
    """Exibe o status operacional do sistema, modelo conectado e banco de dados."""

    def __init__(self) -> None:
        super().__init__()
        self._name = "/status"
        self._description = "Exibe informações do modelo de IA conectado e tamanho da biblioteca."
        self._aliases = ["/info"]
        self._default_error_messages = {
            "usage": "Uso: /status (não requer argumentos adicionais).",
        }

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        db_type = type(ctx.db).__name__
        status_info = {
            "Modelo Gemini Ativo": ctx.agent.model_name,
            "Total de Faixas no Banco": f"{ctx.db.count()} faixa(s)",
            "Nível de Log": settings.LOG_LEVEL,
            "Camada de Armazenamento": f"{db_type} ({'FTS5 Ativo' if 'SQLite' in db_type else 'Memória'})",
            "Arquivo de Banco de Dados": getattr(ctx.db, "db_path", "Em Memória"),
            "Ambiente": "Python 3.14 (Clean Architecture + DDD)",
        }
        if hasattr(ctx.db, "get_stats"):
            stats = ctx.db.get_stats()
            if isinstance(stats, dict):
                status_info["Duração Total"] = f"{stats.get('total_duration_hours', 0)} horas"
                status_info["BPM Médio"] = f"{stats.get('avg_bpm', 0)}"
                db_size = stats.get("db_size_kb", 0)
                if isinstance(db_size, (int, float)) and db_size > 0:
                    status_info["Tamanho do Arquivo .db"] = f"{db_size} KB"

        ctx.ui.render_status(status_info)
        return True
