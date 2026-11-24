"""Acoustic Analysis Command (/analyze) — ADR 0014.

Usage:
    /analyze                      Analyse every track pending analysis (incremental).
    /analyze <path>               Only tracks already scanned under <path>.
    /analyze --force              Re-analyse even tracks with a current analysis.
    /analyze --limit <n>          Process at most n tracks in this run.
    /analyze --workers <n>        Parallel decoders (default: MUSICMATCH_ANALYSIS_WORKERS or up to 4).
    /analyze status               Coverage of the analysis and decoder availability.
    /analyze show <track_id>      Loudness, tempo, key, fingerprint and waveform of one track.

Ctrl+C stops the run gracefully: finished tracks are already saved and the next /analyze
resumes with the remaining ones.
"""

from typing import List, Optional, Tuple

from musicmatch.commands.base import Command, CommandContext


def _analysis_service():
    # Imported lazily so NumPy/SciPy are only loaded when analysis is actually used,
    # keeping REPL start-up fast.
    from musicmatch.services.analysis import acoustic_analysis_service

    return acoustic_analysis_service


class AnalyzeCommand(Command):
    """Mede LUFS, BPM, tonalidade e fingerprint acústico das faixas do catálogo."""

    def __init__(self) -> None:
        super().__init__()
        self._name = "/analyze"
        self._description = (
            "Análise acústica (LUFS, BPM, tonalidade, fingerprint): "
            "/analyze [caminho] [--force] [--limit N] [--workers N] | status | show <id>"
        )
        self._aliases = ["/analisar", "/analyse"]
        self._default_error_messages = {
            "usage": "Uso: /analyze [caminho] [--force] [--limit N] [--workers N] | /analyze status | /analyze show <id>",
            "invalid_number": "Os parâmetros --limit e --workers exigem um número inteiro positivo.",
            "missing_id": "Uso: /analyze show <track_id>",
        }

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if args and args[0].lower() in ("status", "info"):
            ctx.ui.render_analysis_coverage(_analysis_service().coverage())
            return True
        if args and args[0].lower() in ("show", "mostrar"):
            return self._handle_show(args[1:], ctx)
        return self._handle_run(args, ctx)

    def _parse_run_args(self, args: List[str]) -> Tuple[Optional[str], bool, Optional[int], Optional[int]]:
        force = False
        limit: Optional[int] = None
        workers: Optional[int] = None
        path_parts: List[str] = []
        i = 0
        while i < len(args):
            token = args[i]
            if token == "--force":
                force = True
            elif token in ("--limit", "--workers"):
                if i + 1 >= len(args):
                    raise ValueError(token)
                value = int(args[i + 1])
                if value <= 0:
                    raise ValueError(token)
                if token == "--limit":
                    limit = value
                else:
                    workers = value
                i += 1
            else:
                path_parts.append(token)
            i += 1
        path = " ".join(path_parts) if path_parts else None
        return path, force, limit, workers

    def _handle_run(self, args: List[str], ctx: CommandContext) -> bool:
        errors = self.get_default_error_messages()
        try:
            path, force, limit, workers = self._parse_run_args(args)
        except ValueError:
            ctx.ui.render_error(errors["invalid_number"])
            ctx.ui.render_info(errors["usage"])
            return True

        service = _analysis_service()
        path_prefix = None
        if path:
            from pathlib import Path

            path_prefix = str(Path(path).expanduser().resolve()).replace("\\", "/")

        coverage = service.coverage()
        if not coverage.decoder_available:
            formats = "/".join(coverage.supported_formats) or "WAV"
            ctx.ui.render_warning(f"FFmpeg não encontrado: apenas arquivos {formats} serão analisados nesta execução.")
            ctx.ui.render_info("Instale o FFmpeg ou defina MUSICMATCH_FFMPEG_PATH no .env para suportar M4A/AAC/Opus/WMA/AIFF.")

        scope = f" em '{path}'" if path else ""
        mode = " (reanálise forçada)" if force else ""
        ctx.ui.render_info(f"Iniciando análise acústica{scope}{mode}... (Ctrl+C interrompe e salva o progresso)")

        result = service.analyze_library(
            path_prefix=path_prefix,
            force=force,
            limit=limit,
            workers=workers,
            on_progress=ctx.ui.render_analysis_progress,
        )

        if result.total_candidates == 0:
            if path and not service.repo.get_tracks_under_path(path_prefix):
                ctx.ui.render_warning(f"Nenhuma faixa catalogada em '{path}'. Rode /scan {path} primeiro.")
            elif coverage.available_tracks == 0:
                ctx.ui.render_warning("O catálogo não possui faixas disponíveis. Rode /scan <pasta> primeiro.")
            else:
                ctx.ui.render_success("Todas as faixas já possuem análise acústica atualizada.")
                ctx.ui.render_info("Use --force para reanalisar ou /analyze status para ver a cobertura.")
            return True

        ctx.ui.render_analysis_summary(result)
        if result.cancelled:
            if result.remaining_pending:
                ctx.ui.render_warning(
                    f"Análise interrompida. {result.remaining_pending} faixa(s) pendente(s) serão retomadas no próximo /analyze."
                )
            else:
                ctx.ui.render_info("Análise interrompida; as análises anteriores continuam válidas.")
        return True

    def _handle_show(self, args: List[str], ctx: CommandContext) -> bool:
        errors = self.get_default_error_messages()
        if not args:
            ctx.ui.render_error(errors["missing_id"])
            return True
        track_id = args[0]
        track = ctx.db.get_track(track_id) if hasattr(ctx.db, "get_track") else None
        if not track:
            ctx.ui.render_error(f"Faixa '{track_id}' não encontrada no catálogo.")
            return True
        analysis = _analysis_service().get_analysis(track_id)
        if analysis is None:
            ctx.ui.render_warning("Esta faixa ainda não foi analisada.")
            ctx.ui.render_info("Rode /analyze para medir LUFS, BPM, tonalidade e fingerprint.")
            return True
        ctx.ui.render_track_analysis(track, analysis)
        return True


__all__ = ["AnalyzeCommand"]
