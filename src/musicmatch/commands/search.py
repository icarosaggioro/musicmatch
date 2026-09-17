"""Search Command (/search).

Performs instant full-text search against the SQLite FTS5 index without invoking the LLM.
"""

from typing import List

from musicmatch.commands.base import Command, CommandContext


class SearchCommand(Command):
    """Executa busca textual instantânea na biblioteca via FTS5 sem acionar a LLM."""

    def __init__(self) -> None:
        super().__init__()
        self._name = "/search"
        self._description = "Busca faixas por texto ou metadados via FTS5: /search <termo>"
        self._aliases = ["/buscar"]
        self._default_error_messages = {
            "usage": "Uso incorreto. Especifique o termo de busca: /search <termo>",
            "example": "Exemplo: /search Queen  ou  /search Bohemian",
        }

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args:
            errors = self.get_default_error_messages()
            ctx.ui.render_error(errors["usage"])
            ctx.ui.render_info(errors["example"])
            return True

        query = " ".join(args)
        ctx.ui.render_info(f"Buscando por '{query}' no índice FTS5...")

        if hasattr(ctx.db, "search_fulltext"):
            tracks = ctx.db.search_fulltext(query=query, limit=10)
        else:
            tracks = [
                t
                for t in ctx.db.get_all_tracks()
                if query.lower() in t.title.lower() or query.lower() in t.artist.lower()
            ]

        if not tracks:
            ctx.ui.render_info(f"Nenhuma faixa encontrada para '{query}'.")
            return True

        ctx.ui.render_success(f"{len(tracks)} faixa(s) encontrada(s):")
        for i, t in enumerate(tracks, 1):
            print(f"  {i}. {t.artist} - {t.title} [{t.genre}] ({t.bpm:.0f} BPM)")
        return True
