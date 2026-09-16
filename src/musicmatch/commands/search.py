"""Search Command (/search).

Performs instant full-text search against the SQLite FTS5 index without invoking the LLM.
"""

from typing import Dict, List

from musicmatch.commands.base import Command, CommandContext


class SearchCommand(Command):
    """Executa busca textual instantânea na biblioteca via FTS5 sem acionar a LLM."""

    def __init__(self) -> None:
        super().__init__(
            name="/search",
            description="Busca faixas por texto ou metadados via FTS5: /search <termo>",
            aliases=["/buscar"],
        )

    def get_name(self) -> str:
        return "/search"

    def get_aliases(self) -> List[str]:
        return ["/buscar"]

    def get_description(self) -> str:
        return "Busca faixas por texto ou metadados via FTS5: /search <termo>"

    def get_default_error_messages(self) -> Dict[str, str]:
        return {
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
