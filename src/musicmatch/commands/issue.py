"""Issue Commands (ADR 0019). Every command on the Issue register is named '/issue-<action>'.

    /issue [id | --dismissed | --all]        Lists open issues (most recent first), shows one, or
                                             lists the dismissed ones / all of them.
    /issue-dismiss <id...> | --all           Dismisses: "I know, stop telling me". The issue is kept
                                             (dismissed), so the same problem is not raised again.
    /issue-delete <id...> | --dismissed | --all
                                             Deletes: forgets the issue; it comes back as a new one if
                                             the problem happens again. Bulk forms ask first.

IDs are the numbers shown by /issue ('12' or '#12'); several may be given at once.
"""

from typing import List, Optional, Set, Tuple

from musicmatch.commands.base import Command, CommandContext

_YES = ("s", "sim", "y", "yes")
_LIST_LIMIT = 50


def _store(ctx: CommandContext):
    """The register's store, with every report queued so far already persisted."""
    from musicmatch.services.issues import configure_issue_reporter, current_issue_reporter

    reporter = current_issue_reporter()
    if reporter is None:  # normally installed by cli.main; e.g. commands driven by a test or script
        reporter = configure_issue_reporter(getattr(ctx.db, "db_path", None) or ":memory:")
    reporter.flush(timeout=5.0)
    return reporter.store


def _confirm(question: str) -> bool:
    try:
        return input(f"{question} [s/N]: ").strip().lower() in _YES
    except (KeyboardInterrupt, EOFError):
        return False


class _IssueCommand(Command):
    usage = ""
    flags: Tuple[str, ...] = ()

    def __init__(self, name: str, description: str) -> None:
        super().__init__()
        self._name = name
        self._description = description
        self._default_error_messages = {"usage": f"Uso: {self.usage or name}"}

    def _usage_error(self, ctx: CommandContext) -> bool:
        ctx.ui.render_error(self.get_default_error_messages()["usage"])
        return True

    def _parse(self, args: List[str], ctx: CommandContext) -> Optional[Tuple[List[int], Set[str]]]:
        """IDs ('12' or '#12') and flags; renders the problem and returns None when invalid."""
        ids: List[int] = []
        flags: Set[str] = set()
        for arg in args:
            if arg.startswith("--"):
                if arg.lower() not in self.flags:
                    ctx.ui.render_error(f"Opção desconhecida: {arg}.")
                    self._usage_error(ctx)
                    return None
                flags.add(arg.lower())
                continue
            token = arg[1:] if arg.startswith("#") else arg
            if not token.isdigit():
                ctx.ui.render_error(f"'{arg}' não é o número de um problema (veja /issue).")
                return None
            ids.append(int(token))
        if ids and flags:
            ctx.ui.render_error("Informe números de problemas ou uma opção, não ambos.")
            return None
        return list(dict.fromkeys(ids)), flags


class IssueCommand(_IssueCommand):
    usage = "/issue [id | --dismissed | --all]"
    flags = ("--dismissed", "--all")

    def __init__(self) -> None:
        super().__init__("/issue", "Lista os problemas registrados ou mostra um deles: /issue [id | --dismissed | --all]")

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        parsed = self._parse(args, ctx)
        if parsed is None:
            return True
        ids, flags = parsed
        store = _store(ctx)
        if len(ids) > 1 or len(flags) > 1:
            return self._usage_error(ctx)
        if ids:
            issue = store.get(ids[0])
            if issue is None:
                ctx.ui.render_error(f"Problema #{ids[0]} não encontrado (veja /issue).")
            else:
                ctx.ui.render_issue(issue)
            return True
        status = None if "--all" in flags else ("DISMISSED" if "--dismissed" in flags else "OPEN")
        ctx.ui.render_issues(
            store.list(status=status, limit=_LIST_LIMIT), store.counts_by_kind(status), store.count(status),
            status=status, other_count=store.count("DISMISSED") if status == "OPEN" else 0,
        )
        return True


class IssueDismissCommand(_IssueCommand):
    usage = "/issue-dismiss <id...> | --all"
    flags = ("--all",)

    def __init__(self) -> None:
        super().__init__(
            "/issue-dismiss",
            "Dispensa problemas (não voltam a ser avisados): /issue-dismiss <id...> | --all",
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        parsed = self._parse(args, ctx)
        if parsed is None:
            return True
        ids, flags = parsed
        if not ids and not flags:
            return self._usage_error(ctx)
        store = _store(ctx)
        if flags:
            count = store.dismiss()
            ctx.ui.render_success(f"{count} problema(s) dispensado(s). Veja-os com /issue --dismissed.")
            return True
        known = {i: store.get(i) for i in ids}
        missing = [i for i, issue in known.items() if issue is None]
        already = [i for i, issue in known.items() if issue is not None and issue.status == "DISMISSED"]
        count = store.dismiss([i for i, issue in known.items() if issue is not None and issue.status == "OPEN"])
        if count:
            ctx.ui.render_success(f"{count} problema(s) dispensado(s): não serão avisados de novo.")
        if already:
            ctx.ui.render_info(f"Já estavam dispensados: {', '.join(f'#{i}' for i in already)}.")
        if missing:
            ctx.ui.render_error(f"Não encontrados: {', '.join(f'#{i}' for i in missing)} (veja /issue).")
        return True


class IssueDeleteCommand(_IssueCommand):
    usage = "/issue-delete <id...> | --dismissed | --all"
    flags = ("--dismissed", "--all")

    def __init__(self) -> None:
        super().__init__(
            "/issue-delete",
            "Apaga problemas (voltam se ocorrerem de novo): /issue-delete <id...> | --dismissed | --all",
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        parsed = self._parse(args, ctx)
        if parsed is None:
            return True
        ids, flags = parsed
        if not ids and not flags:
            return self._usage_error(ctx)
        if len(flags) > 1:
            return self._usage_error(ctx)
        store = _store(ctx)
        if flags:
            status = "DISMISSED" if "--dismissed" in flags else None
            total = store.count(status)
            if total == 0:
                ctx.ui.render_info("Nenhum problema a apagar.")
                return True
            scope = "dispensado(s)" if status else "registrado(s), abertos e dispensados"
            if not _confirm(f"Apagar {total} problema(s) {scope}? Os que voltarem a ocorrer serão registrados de novo."):
                ctx.ui.render_info("Operação cancelada: nada foi apagado.")
                return True
            count = store.delete(status=status) if status else store.delete()
            ctx.ui.render_success(f"{count} problema(s) apagado(s).")
            return True
        missing = [i for i in ids if store.get(i) is None]
        count = store.delete([i for i in ids if i not in missing])
        if count:
            ctx.ui.render_success(f"{count} problema(s) apagado(s). Se o problema ocorrer de novo, será registrado outra vez.")
        if missing:
            ctx.ui.render_error(f"Não encontrados: {', '.join(f'#{i}' for i in missing)} (veja /issue).")
        return True


ISSUE_COMMANDS = [IssueCommand, IssueDismissCommand, IssueDeleteCommand]

__all__ = [cls.__name__ for cls in ISSUE_COMMANDS] + ["ISSUE_COMMANDS"]
