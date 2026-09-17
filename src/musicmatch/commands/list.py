"""List Command (/list).

Lists indexed tracks in the library with interactive pagination and cancellation.
"""

from typing import List

from musicmatch.commands.base import Command, CommandContext


class ListCommand(Command):
    """Lista as músicas presentes na biblioteca com paginação e opção de cancelamento."""

    DEFAULT_PAGE_SIZE = 20

    def __init__(self) -> None:
        super().__init__()
        self._name = "/list"
        self._description = "Lista as músicas da biblioteca com paginação (padrão: 20): /list [tamanho_pagina]"
        self._aliases = ["/listar"]
        self._default_error_messages = {
            "usage": "Uso: /list [tamanho_pagina]",
            "invalid_page_size": "O tamanho da página deve ser um número inteiro positivo.",
            "empty_library": "A biblioteca está vazia. Use '/scan <caminho>' para adicionar músicas.",
        }

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        errors = self.get_default_error_messages()
        page_size = self.DEFAULT_PAGE_SIZE

        if args:
            try:
                parsed_size = int(args[0])
                if parsed_size > 0:
                    page_size = parsed_size
                else:
                    ctx.ui.render_error(errors["invalid_page_size"])
                    return True
            except ValueError:
                ctx.ui.render_error(errors["invalid_page_size"])
                return True

        total_tracks = ctx.db.count()
        if total_tracks == 0:
            ctx.ui.render_info(errors["empty_library"])
            return True

        total_pages = (total_tracks + page_size - 1) // page_size

        for page in range(1, total_pages + 1):
            offset = (page - 1) * page_size
            try:
                tracks = ctx.db.get_all_tracks(limit=page_size, offset=offset)
            except TypeError:
                all_tracks = ctx.db.get_all_tracks()
                tracks = all_tracks[offset : offset + page_size]

            start_idx = offset + 1
            ctx.ui.render_track_page(tracks, page, total_pages, total_tracks, start_idx=start_idx)

            if page < total_pages:
                action = ctx.ui.prompt_pagination()
                if action in ("q", "quit", "c", "cancel", "sair", "cancelar"):
                    ctx.ui.render_info("Listagem cancelada pelo usuário.")
                    return True

        ctx.ui.render_info("Fim da listagem.")
        return True
