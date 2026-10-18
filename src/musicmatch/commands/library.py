"""Library Management Command (/library).

Follows ADR 0012 and ADR 0013:
- Displays system/model/database status followed by Managed Library location and write capability.
- Unifies former /status functionality directly into /library and /library status.
- Supports aliases: /lib, /biblioteca.
- Supports external library consolidation (/library import <path> [--copy | --move]).
- Supports physical in-library reorganization (/library reorganize).
- Supports catalog reset (/library clear / reset).
"""

from pathlib import Path
from typing import Dict, List, Optional

from musicmatch.commands.base import Command, CommandContext
from musicmatch.config import settings
from musicmatch.services.location import library_location_manager
from musicmatch.services.maintenance import library_maintenance_service


class LibraryCommand(Command):
    """Gerencia a localização, integridade e status da Biblioteca Gerenciada."""

    def __init__(self) -> None:
        super().__init__()
        self._name = "/library"
        self._description = "Exibe status do sistema e da biblioteca: /library [status] | set-path | import | reorganize | clear"
        self._aliases = ["/biblioteca", "/lib"]
        self._default_error_messages = {
            "usage": "Uso: /library [status] | set-path <caminho> | import <caminho> | reorganize | clear",
            "missing_path": "Uso incorreto. Especifique o novo caminho: /library set-path <caminho>",
        }

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args or args[0].lower() in ("status", "info", "path"):
            return self._handle_combined_status(ctx)

        subcommand = args[0].lower()
        if subcommand in ("set-path", "set"):
            return self._handle_set_path(args[1:], ctx)
        if subcommand in ("clear", "reset", "limpar"):
            return self._handle_clear(ctx)
        if subcommand == "import":
            return self._handle_import(args[1:], ctx)
        if subcommand in ("reorganize", "reorganizar"):
            return self._handle_reorganize(ctx)

        errors = self.get_default_error_messages()
        ctx.ui.render_error(f"Subcomando '{args[0]}' não reconhecido para /library.")
        ctx.ui.render_info(errors["usage"])
        return True

    def _handle_combined_status(self, ctx: CommandContext) -> bool:
        """Exibe as informações do /status primeiro, seguidas pelas informações do /library."""
        # 1. First, render the system/database status information (what was in /status)
        db_type = type(ctx.db).__name__
        status_info = {
            "Ambiente": "Python 3.14 (Clean Architecture + DDD)",
            "Camada de Armazenamento": f"{db_type} ({'FTS5 Ativo' if 'SQLite' in db_type else 'Memória'})",
            "Arquivo de Banco de Dados": getattr(ctx.db, "db_path", "Em Memória"),
            "Nível de Log": settings.LOG_LEVEL,
            "Modelo Gemini Ativo": ctx.agent.model_name,
            "Total de Faixas no Banco": f"{ctx.db.count()} faixa(s)",
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

        # 2. Second, render the Managed Library status information (what was in /library)
        current_path = library_location_manager.resolve_library_path()
        try:
            library_location_manager.validate_and_probe_path(current_path)
            write_status = "Permitido (OK)"
        except Exception as e:
            write_status = f"Falha ({e})"

        library_info = {
            "Caminho Base": str(current_path).replace("\\", "/"),
            "Acesso de Escrita": write_status,
            "Estrutura Padrão": "Artists/ | Various Artists/ | Collections/",
        }
        ctx.ui.render_library_status(library_info)
        return True

    def _handle_set_path(self, args: List[str], ctx: CommandContext) -> bool:
        if not args:
            ctx.ui.render_error("Uso incorreto. Especifique o novo caminho: /library set-path <caminho>")
            ctx.ui.render_info("Exemplo: /library set-path D:/MinhasMusicas")
            return True

        new_path_str = " ".join(args)
        target_path = Path(new_path_str).expanduser()

        try:
            saved_path = library_location_manager.set_library_path(target_path)
            ctx.ui.render_success("Diretório da Biblioteca Gerenciada atualizado com sucesso!")
            ctx.ui.render_info(f"Novo caminho ativo: {saved_path}")
            ctx.ui.render_info("Estrutura canônica de diretórios inicializada (Artists, Various Artists, Collections).")
        except (ValueError, PermissionError) as e:
            ctx.ui.render_error(f"Não foi possível definir o caminho informado: {e}")
        return True

    def _handle_clear(self, ctx: CommandContext) -> bool:
        ctx.ui.render_warning("⚠️ ATENÇÃO: Esta ação apagará todas as faixas e índices FTS5 do catálogo local!")
        ctx.ui.render_info("Nota: Os arquivos físicos de música no seu disco NÃO serão excluídos.")
        try:
            confirm = input("Tem certeza que deseja zerar todo o catálogo da biblioteca? [s/N]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            ctx.ui.render_info("Operação cancelada pelo usuário.")
            return True

        if confirm in ("s", "sim", "y", "yes"):
            ctx.db.clear()
            ctx.ui.render_success("Biblioteca limpa com sucesso! O catálogo agora está vazio.")
        else:
            ctx.ui.render_info("Operação cancelada pelo usuário.")
        return True

    def _handle_import(self, args: List[str], ctx: CommandContext) -> bool:
        if not args:
            ctx.ui.render_error("Uso incorreto: /library import <caminho_origem> [--copy | --move]")
            return True

        mode = "move" if "--move" in args else "copy"
        filtered_args = [a for a in args if a not in ("--copy", "--move")]
        source_path_str = " ".join(filtered_args)

        ctx.ui.render_info(f"Iniciando importação de '{source_path_str}' no modo '{mode.upper()}'...")
        result = library_maintenance_service.import_external_library(
            source_path=Path(source_path_str),
            mode=mode,
        )

        if result.status == "error":
            for err in result.errors:
                ctx.ui.render_error(err)
            return True

        ctx.ui.render_success(f"Importação concluída: {result.imported_count}/{result.total_files} faixa(s) importada(s).")
        if result.skipped_count > 0:
            ctx.ui.render_info(f"{result.skipped_count} faixa(s) ignorada(s) por colisão com arquivos já existentes.")
        if result.locked_files:
            ctx.ui.render_warning(f"{len(result.locked_files)} arquivo(s) não puderam ser movidos por trava de permissão.")
        return True

    def _handle_reorganize(self, ctx: CommandContext) -> bool:
        ctx.ui.render_info("Reorganizando arquivos na Biblioteca Gerenciada para refletir metadados atualizados...")
        res = library_maintenance_service.reorganize_library()
        ctx.ui.render_success(f"Reorganização concluída: {res.realigned_count} arquivo(s) realinhado(s), {res.skipped_count} inalterado(s).")
        if res.errors:
            for err in res.errors:
                ctx.ui.render_error(err)
        return True


__all__ = ["LibraryCommand"]
