"""Scan Command (/scan).

Directly runs library scanning and audio indexing on a local filesystem directory.
"""

from typing import List

from musicmatch.commands.base import Command, CommandContext
from musicmatch.tools.scanner import scan_library


class ScanCommand(Command):
    """Executa a ferramenta de escaneamento diretamente pelo terminal sem acionar a LLM."""

    def __init__(self) -> None:
        super().__init__()
        self._name = "/scan"
        self._description = "Varre um diretório de áudio diretamente: /scan <caminho_da_pasta>"
        self._aliases = ["/escanear", "/varrer"]
        self._default_error_messages = {
            "usage": "Uso incorreto. Especifique o caminho da pasta: /scan <caminho>",
            "example": "Exemplo: /scan C:/Musicas",
        }

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args:
            errors = self.get_default_error_messages()
            ctx.ui.render_error(errors["usage"])
            ctx.ui.render_info(errors["example"])
            return True

        path = " ".join(args)
        ctx.ui.render_info(f"Iniciando varredura determinística direta em '{path}'...")
        result = scan_library(path=path)

        if result.get("status") == "error":
            ctx.ui.render_error(result.get("message", "Erro ao executar varredura."))
            return True

        total_scanned = result.get("total_files_scanned", 0)
        tracks_indexed = result.get("tracks_indexed", 0)
        tracks_added = result.get("tracks_added", tracks_indexed)
        tracks_updated = result.get("tracks_updated", 0)
        tracks_unchanged = result.get("tracks_unchanged", 0)
        tracks_missing = result.get("tracks_missing", 0)
        errors_count = result.get("errors_count", 0)
        duration_ms = result.get("duration_ms", 0.0)

        ctx.ui.render_success(
            f"Varredura concluída: {total_scanned} arquivo(s) processado(s) em {duration_ms:.1f}ms."
        )
        ctx.ui.render_info(
            f"  [+] {tracks_added} nova(s) | [~] {tracks_updated} atualizada(s) | [=] {tracks_unchanged} inalterada(s) (Stat-Cache)"
        )
        if tracks_missing > 0:
            ctx.ui.render_warning(f"  [!] {tracks_missing} faixa(s) marcada(s) como ausente(s) no disco (Soft-Delete).")
        if errors_count > 0:
            ctx.ui.render_warning(f"  [!] {errors_count} arquivo(s) com erro ignorado(s).")

        total_tracks = ctx.db.count() if hasattr(ctx.db, "count") else result.get("database_total_tracks", 0)
        ctx.ui.render_info(f"Total na biblioteca agora: {total_tracks} faixa(s).")
        return True
