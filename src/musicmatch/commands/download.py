"""Web Ingestion and Safe Download Command (/download).

Follows ADR 0010, ADR 0011, and ADR 0012:
- Supports direct URLs and interactive keyword search candidate selection.
- Bitstream preservation (native audio container) by default; optional --format mp3.
- Downloads directly into isolated staging sessions.
"""

from typing import List, Tuple

from musicmatch.commands.base import Command, CommandContext
from musicmatch.services.downloader import audio_downloader_service


class DownloadCommand(Command):
    """Realiza busca e download seguro de áudio da Web para a Staging Area."""

    def __init__(self) -> None:
        super().__init__(
            name="/download",
            description="Baixa áudio da web para a Staging Area: /download <url|busca> [--format mp3]",
            aliases=["/baixar"],
        )

    def _parse_args(self, args: List[str]) -> Tuple[str, str, bool]:
        """Parses options (--format, --playlist) from positional query/URL arguments."""
        format_preference = "native"
        is_playlist = False
        remaining: List[str] = []

        i = 0
        while i < len(args):
            arg = args[i]
            if arg in ("--format", "-f") and i + 1 < len(args):
                format_preference = args[i + 1].lower()
                i += 2
            elif arg == "--playlist":
                is_playlist = True
                i += 1
            else:
                remaining.append(arg)
                i += 1

        query_or_url = " ".join(remaining).strip()
        return query_or_url, format_preference, is_playlist

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args:
            ctx.ui.render_error("Uso incorreto. Especifique uma URL ou termo de busca: /download <url|busca>")
            ctx.ui.render_info("Exemplos:")
            ctx.ui.render_info("  /download https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            ctx.ui.render_info("  /download Queen Bohemian Rhapsody")
            ctx.ui.render_info("  /download Pink Floyd Time --format mp3")
            return True

        query_or_url, fmt, is_playlist = self._parse_args(args)
        if not query_or_url:
            ctx.ui.render_error("Nenhum termo de busca ou URL fornecido.")
            return True

        is_direct_url = query_or_url.startswith(("http://", "https://", "www."))
        if is_direct_url:
            # Direct URL download
            manifest = audio_downloader_service.create_session(query_or_url)
            ctx.ui.render_info(f"Iniciando download seguro para a Staging Area (Sessão: {manifest.session_id})...")
            try:
                track = audio_downloader_service.download_track(
                    url=query_or_url,
                    session_id=manifest.session_id,
                    format_preference=fmt,
                )
                ctx.ui.render_success(f"Download concluído: {track.artist} - {track.title} ({track.format.upper()})")
                ctx.ui.render_info(f"Arquivo isolado em: {track.file_path}")
                ctx.ui.render_info(f"Para inspecionar a sessão: /staging show {manifest.session_id}")
            except Exception as e:
                ctx.ui.render_error(f"Erro durante o download da faixa: {e}")
            return True

        # Search query workflow
        ctx.ui.render_info(f"Pesquisando candidatos para '{query_or_url}' no YouTube...")
        try:
            candidates = audio_downloader_service.search_candidates(query_or_url, max_results=5)
        except Exception as e:
            ctx.ui.render_error(f"Erro ao pesquisar candidatos: {e}")
            return True

        if not candidates:
            ctx.ui.render_warning(f"Nenhum resultado encontrado no YouTube para '{query_or_url}'.")
            return True

        ctx.ui.render_search_candidates(candidates)

        try:
            choice_str = input("Escolha o número da faixa (1 a 5, ou 0 para cancelar): ").strip()
        except (KeyboardInterrupt, EOFError):
            ctx.ui.render_info("Operação cancelada pelo usuário.")
            return True

        if choice_str in ("0", "c", "cancel", "q", "quit", "sair", "cancelar", ""):
            ctx.ui.render_info("Download cancelado.")
            return True

        try:
            idx = int(choice_str) - 1
            if idx < 0 or idx >= len(candidates):
                ctx.ui.render_error(f"Opção '{choice_str}' inválida. Operação cancelada.")
                return True
        except ValueError:
            ctx.ui.render_error("Entrada inválida. Digite apenas o número correspondente à música.")
            return True

        selected = candidates[idx]
        manifest = audio_downloader_service.create_session(selected["url"])
        ctx.ui.render_info(f"Baixando '{selected['title']}' para a Staging Area...")

        try:
            track = audio_downloader_service.download_track(
                url=selected["url"],
                session_id=manifest.session_id,
                format_preference=fmt,
            )
            ctx.ui.render_success(f"Download concluído: {track.artist} - {track.title} ({track.format.upper()})")
            ctx.ui.render_info(f"Arquivo isolado em: {track.file_path}")
            ctx.ui.render_info(f"Para inspecionar a sessão: /staging show {manifest.session_id}")
        except Exception as e:
            ctx.ui.render_error(f"Erro durante o download da faixa: {e}")

        return True
