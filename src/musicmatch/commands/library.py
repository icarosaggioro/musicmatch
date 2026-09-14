"""Library Management Command (/library).

Follows ADR 0012:
- Displays current Managed Library path, origin, and write capability.
- Allows user to change the Managed Library path with critical path safeguards and write probe validation.
"""

from pathlib import Path
from typing import List

from musicmatch.commands.base import Command, CommandContext
from musicmatch.services.location import library_location_manager


class LibraryCommand(Command):
    """Gerencia a localização e integridade do diretório da Biblioteca Gerenciada."""

    def __init__(self) -> None:
        super().__init__(
            name="/library",
            description="Exibe ou altera o diretório da Biblioteca Gerenciada: /library [set-path <caminho>]",
            aliases=["/biblioteca"],
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args or args[0].lower() in ("path", "status", "info"):
            # Display current library path and health
            current_path = library_location_manager.resolve_library_path()
            try:
                library_location_manager.validate_and_probe_path(current_path)
                write_status = "Permitido (OK)"
            except Exception as e:
                write_status = f"Falha ({e})"

            info = {
                "Caminho Base": str(current_path).replace("\\", "/"),
                "Acesso de Escrita": write_status,
                "Estrutura Padrão": "Artists/ | Various Artists/ | Collections/",
            }
            ctx.ui.render_library_status(info)
            return True

        subcommand = args[0].lower()
        if subcommand in ("set-path", "set"):
            if len(args) < 2:
                ctx.ui.render_error("Uso incorreto. Especifique o novo caminho: /library set-path <caminho>")
                ctx.ui.render_info("Exemplo: /library set-path D:/MinhasMusicas")
                return True

            new_path_str = " ".join(args[1:])
            target_path = Path(new_path_str).expanduser()

            try:
                saved_path = library_location_manager.set_library_path(target_path)
                ctx.ui.render_success(f"Diretório da Biblioteca Gerenciada atualizado com sucesso!")
                ctx.ui.render_info(f"Novo caminho ativo: {saved_path}")
                ctx.ui.render_info("Estrutura canônica de diretórios inicializada (Artists, Various Artists, Collections).")
            except (ValueError, PermissionError) as e:
                ctx.ui.render_error(f"Não foi possível definir o caminho informado: {e}")
            return True

        ctx.ui.render_error(f"Subcomando '{subcommand}' não reconhecido para /library.")
        ctx.ui.render_info("Uso: /library  ou  /library set-path <novo_caminho>")
        return True
