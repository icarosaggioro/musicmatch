"""Audit Command (/audit).

Follows ADR 0013:
- Diagnostic dashboard for library health, missing files, untagged tracks, degraded bitrates, and duplicates.
- Side-by-side duplicate recording comparisons with quality-first retention recommendations.
"""

from typing import List
from musicmatch.commands.base import Command, CommandContext
from musicmatch.commands.prune import PruneCommand
from musicmatch.services.maintenance import library_maintenance_service


class AuditCommand(Command):
    """Diagnóstico de integridade, duplicatas e qualidade do acervo musical."""

    def __init__(self) -> None:
        super().__init__()
        self._name = "/audit"
        self._description = "Diagnóstico e auditoria de saúde da biblioteca: /audit [duplicates | prune]"
        self._aliases = ["/auditar"]
        self._default_error_messages = {
            "usage": "Uso: /audit  ou  /audit duplicates  ou  /audit prune",
        }

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args or args[0].lower() in ("status", "info", "report"):
            report = library_maintenance_service.audit_library()
            if hasattr(ctx.ui, "render_audit_report"):
                ctx.ui.render_audit_report(report)
            else:
                print("\n" + "=" * 72)
                print("🩺 DIAGNÓSTICO DE INTEGRIDADE DA BIBLIOTECA:")
                print("=" * 72)
                print(f"  • Total de Faixas no Catálogo: {report.total_tracks}")
                print(f"  • Faixas Acessíveis no Disco : {report.available_tracks} (OK)")
                print(f"  • Faixas Indisponíveis/MISSING: {report.missing_tracks}")
                print(f"  • Faixas com Metadados Falhos: {report.untagged_tracks}")
                print(f"  • Faixas com Bitrate Baixo   : {report.low_bitrate_tracks} (< 128 kbps)")
                print(f"  • Grupos de Músicas Duplicadas: {report.duplicate_groups_count}")
                if report.missing_sample:
                    print("-" * 72)
                    print("  Amostra de faixas indisponíveis no disco:")
                    for m in report.missing_sample:
                        print(f"    - {m.artist} - {m.title} [{m.file_path}]")
                print("=" * 72 + "\n")
            return True

        subcommand = args[0].lower()
        if subcommand in ("duplicates", "dup", "dups"):
            groups = library_maintenance_service.find_duplicates()
            if not groups:
                ctx.ui.render_success("Nenhuma duplicata detectada na biblioteca.")
                return True

            if hasattr(ctx.ui, "render_duplicate_groups"):
                ctx.ui.render_duplicate_groups(groups)
            else:
                print("\n" + "=" * 72)
                print(f"👥 {len(groups)} GRUPO(S) DE DUPLICATAS ENCONTRADO(S):")
                print("=" * 72)
                for i, g in enumerate(groups, start=1):
                    print(f"  Grupo {i}: {g.signature.upper()}")
                    print(f"  💡 Recomendação: {g.recommendation_reason}")
                    for t in g.tracks:
                        star = " ⭐ [PRESERVAR]" if t.id == g.recommended_track_id else " 🗑️ [SUGERIDO EXCLUIR]"
                        print(f"    - [{t.id}] {t.artist} - {t.title} ({t.bitrate_kbps} kbps, {t.duration_seconds:.0f}s){star}")
                        print(f"      Caminho: {t.file_path}")
                print("=" * 72 + "\n")
            return True

        if subcommand == "prune":
            prune_cmd = PruneCommand()
            return prune_cmd.execute(args[1:], ctx)

        ctx.ui.render_error(f"Subcomando '{subcommand}' não reconhecido para /audit.")
        ctx.ui.render_info("Uso: /audit  ou  /audit duplicates  ou  /audit prune")
        return True

