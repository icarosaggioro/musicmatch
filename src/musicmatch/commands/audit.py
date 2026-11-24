"""Audit Command (/audit).

Follows ADR 0013 and ADR 0014:
- Diagnostic dashboard for library health, missing files, untagged tracks, degraded bitrates,
  duplicates and acoustic analysis coverage.
- Side-by-side duplicate recording comparisons with quality-first retention recommendations.
- Duplicate evidence: by default the audio of analysed tracks, and normalized tags for the
  others. --tags, --exact and --fuzzy (same recording across encodes and bitrates) force one.
"""

from typing import List
from musicmatch.commands.base import Command, CommandContext
from musicmatch.commands.prune import PruneCommand
from musicmatch.services.maintenance import library_maintenance_service

_STRATEGY_FLAGS = {
    "--tags": "metadata",
    "--metadata": "metadata",
    "--exact": "exact",
    "--fuzzy": "fuzzy",
    "--acoustic": "fuzzy",
}


class AuditCommand(Command):
    """Diagnóstico de integridade, duplicatas e qualidade do acervo musical."""

    def __init__(self) -> None:
        super().__init__()
        self._name = "/audit"
        self._description = (
            "Diagnóstico e auditoria de saúde da biblioteca: "
            "/audit [duplicates [--tags | --exact | --fuzzy] | prune]"
        )
        self._aliases = ["/auditar"]
        self._default_error_messages = {
            "usage": "Uso: /audit  ou  /audit duplicates [--tags | --exact | --fuzzy]  ou  /audit prune",
        }

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args or args[0].lower() in ("status", "info", "report"):
            report = library_maintenance_service.audit_library()
            ctx.ui.render_audit_report(report)
            return True

        subcommand = args[0].lower()
        if subcommand in ("duplicates", "dup", "dups"):
            return self._handle_duplicates(args[1:], ctx)

        if subcommand == "prune":
            prune_cmd = PruneCommand()
            return prune_cmd.execute(args[1:], ctx)

        ctx.ui.render_error(f"Subcomando '{subcommand}' não reconhecido para /audit.")
        ctx.ui.render_info(self.get_default_error_messages()["usage"])
        return True

    def _handle_duplicates(self, flags: List[str], ctx: CommandContext) -> bool:
        strategy = "auto"
        for flag in flags:
            key = flag.lower()
            if key not in _STRATEGY_FLAGS:
                ctx.ui.render_error(f"Opção '{flag}' não reconhecida para /audit duplicates.")
                ctx.ui.render_info(self.get_default_error_messages()["usage"])
                return True
            strategy = _STRATEGY_FLAGS[key]

        if strategy in ("exact", "fuzzy"):
            counts = library_maintenance_service.repo.get_analysis_counts()
            if counts["analyzed"] == 0:
                ctx.ui.render_warning("Nenhuma faixa possui análise acústica ainda.")
                ctx.ui.render_info("Rode /analyze para calcular os fingerprints e tente novamente.")
                return True
            if counts["pending"]:
                ctx.ui.render_info(
                    f"{counts['pending']} faixa(s) ainda sem análise acústica ficam fora desta comparação (/analyze)."
                )
            if strategy == "fuzzy":
                ctx.ui.render_info("Comparando fingerprints acústicos (tolerante a reencodes e bitrates)...")

        groups = library_maintenance_service.find_duplicates(strategy=strategy)
        if not groups:
            ctx.ui.render_success("Nenhuma duplicata detectada na biblioteca.")
            if strategy != "fuzzy":
                ctx.ui.render_info("Dica: após /analyze, /audit duplicates --fuzzy encontra a mesma gravação em outros formatos e bitrates.")
            return True

        ctx.ui.render_duplicate_groups(groups)
        return True
