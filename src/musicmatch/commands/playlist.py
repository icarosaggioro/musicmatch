"""Playlist Commands (ADR 0018). Every playlist command is named '/playlist-<action>', like the queue family.

    /playlist [name]                       Lists the playlists, or shows the tracks of one.
    /playlist-save <name>                  Saves the play queue as a playlist (asks before replacing one).
    /playlist-load <name> [--append]       Fills the queue with a playlist: replaces the queue (asks
                                           first when it has tracks) or, with --append, adds to its end.
    /playlist-rename <name> <new name>     Renames a playlist.
    /playlist-remove <name> <id | #n>      Removes every occurrence of a track, or only the entry at
                                           position n (as numbered by '/playlist <name>').
    /playlist-delete <name>                Deletes a playlist; its tracks stay in the library.
    /playlist-delete-with-tracks <name>    Deletes a playlist and moves its tracks' files to the Recycle
                                           Bin, unindexing them (ADR 0013 count-verification gate).
    /playlist-import <file> [name]         Creates a playlist from an .m3u/.m3u8 file.
    /playlist-export <name> [destination] [--relative]
                                           Writes a playlist as .m3u8 (default: <library>/Playlists).

Names are case- and accent-insensitive and may be abbreviated to a unique prefix. Names with
spaces need no quotes when they come last; before another argument, an existing playlist name is
recognised word by word (/playlist-rename Road Trip Summer Trip), or it can be quoted. In
/playlist-remove the track reference is always the last word, so the name needs no quotes.

'remove' is reserved, as in /queue-remove, for taking tracks out of a list; 'delete' removes a
whole thing, as /delete does for tracks.
"""

from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple

from musicmatch.commands.base import Command, CommandContext
from musicmatch.commands.player import _player
from musicmatch.domain.playlist import InvalidPlaylistName, PlaylistSummary, normalize_playlist_name

_YES = ("s", "sim", "y", "yes")


def _service(ctx: CommandContext):
    from musicmatch.services.playlists import PlaylistService

    return PlaylistService(ctx.db)


def _confirm(question: str) -> bool:
    try:
        return input(f"{question} [s/N]: ").strip().lower() in _YES
    except (KeyboardInterrupt, EOFError):
        return False


def _plural(count: int, word: str = "faixa") -> str:
    return f"{count} {word}" + ("" if count == 1 else "s")


def _agree(count: int, singular: str, plural: str) -> str:
    """Portuguese agreement with a count: _agree(1, 'será removida', 'serão removidas')."""
    return singular if count == 1 else plural


class _PlaylistCommand(Command):
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

    def _split_flags(self, args: List[str], ctx: CommandContext) -> Optional[Tuple[List[str], Set[str]]]:
        positional = [a for a in args if not a.startswith("--")]
        flags = {a.lower() for a in args if a.startswith("--")}
        unknown = flags - set(self.flags)
        if unknown:
            ctx.ui.render_error(f"Opção desconhecida: {', '.join(sorted(unknown))}.")
            self._usage_error(ctx)
            return None
        return positional, flags

    @staticmethod
    def _resolve(ref: str, service, ctx: CommandContext) -> Optional[PlaylistSummary]:
        match, candidates = service.resolve(ref)
        if match is not None:
            return match
        if candidates:
            names = ", ".join(f"'{c.name}'" for c in candidates[:5])
            ctx.ui.render_error(f"'{ref}' corresponde a mais de uma playlist ({names}): informe mais do nome.")
        else:
            ctx.ui.render_error(f"Playlist '{ref}' não encontrada.")
            ctx.ui.render_info("Use /playlist para ver as playlists salvas.")
        return None

    @staticmethod
    def _split_name(tokens: Sequence[str], service, keep: int = 0) -> Tuple[str, List[str]]:
        """Longest leading run of words that names an existing playlist (leaving at least `keep`
        words for the next argument); otherwise the first word (a prefix or a quoted name)."""
        for size in range(len(tokens) - keep, 0, -1):
            candidate = " ".join(tokens[:size])
            if service.find_exact(candidate) is not None:
                return candidate, list(tokens[size:])
        return tokens[0], list(tokens[1:])

    @staticmethod
    def _valid_name(raw: str, ctx: CommandContext) -> Optional[str]:
        try:
            return normalize_playlist_name(raw)
        except InvalidPlaylistName as exc:
            ctx.ui.render_error(str(exc))
            return None


class PlaylistCommand(_PlaylistCommand):
    usage = "/playlist [nome]"

    def __init__(self) -> None:
        super().__init__("/playlist", "Lista as playlists salvas, ou mostra as faixas de uma: /playlist [nome]")

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        service = _service(ctx)
        if not args:
            ctx.ui.render_playlists(service.list())
            return True
        summary = self._resolve(" ".join(args), service, ctx)
        if summary is not None:
            ctx.ui.render_playlist(service.get(summary.id))
        return True


class PlaylistSaveCommand(_PlaylistCommand):
    usage = "/playlist-save <nome>"

    def __init__(self) -> None:
        super().__init__("/playlist-save", "Salva a fila de reprodução como playlist: /playlist-save <nome>")

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args:
            return self._usage_error(ctx)
        name = self._valid_name(" ".join(args), ctx)
        if name is None:
            return True
        queue = _player(ctx).status().queue
        if not queue:
            ctx.ui.render_warning("A fila está vazia: nada a salvar. Adicione faixas com /queue-add <id> ou /playlist-load <nome>.")
            return True
        service = _service(ctx)
        existing = service.find_exact(name)
        if existing is not None and not _confirm(
            f"A playlist '{existing.name}' ({_plural(existing.track_count)}) já existe e será substituída "
            f"pela fila atual ({_plural(len(queue))}). Continuar?"
        ):
            ctx.ui.render_info("Operação cancelada: nada foi alterado.")
            return True
        saved = service.save(name, queue, existing)
        verb = "atualizada" if existing is not None else "criada"
        ctx.ui.render_success(f"Playlist '{saved.name}' {verb} com a fila atual ({_plural(saved.track_count)}).")
        skipped = len(queue) - saved.track_count
        if skipped:
            ctx.ui.render_warning(
                f"{_plural(skipped, 'entrada')} da fila {_agree(skipped, 'não está', 'não estão')} mais no catálogo "
                f"e {_agree(skipped, 'ficou', 'ficaram')} de fora."
            )
        return True


class PlaylistLoadCommand(_PlaylistCommand):
    usage = "/playlist-load <nome> [--append]"
    flags = ("--append",)

    def __init__(self) -> None:
        super().__init__(
            "/playlist-load",
            "Preenche a fila com uma playlist (substitui a fila; --append adiciona ao final): /playlist-load <nome> [--append]",
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        parsed = self._split_flags(args, ctx)
        if parsed is None:
            return True
        positional, flags = parsed
        if not positional:
            return self._usage_error(ctx)
        service = _service(ctx)
        summary = self._resolve(" ".join(positional), service, ctx)
        if summary is None:
            return True
        playlist = service.get(summary.id)
        if not playlist.tracks:
            ctx.ui.render_warning(f"A playlist '{playlist.name}' está vazia: a fila não foi alterada.")
            service.report_empty(summary)
            return True
        player = _player(ctx)
        append = "--append" in flags
        queue = player.status().queue
        same = [t.id for t in queue] == [t.id for t in playlist.tracks]
        if not append and queue and not same and not _confirm(
            f"A fila atual ({_plural(len(queue))}) será substituída pela playlist '{playlist.name}' "
            f"({_plural(len(playlist.tracks))}). Para guardá-la antes, use /playlist-save <nome>. Continuar?"
        ):
            ctx.ui.render_info("Operação cancelada: a fila não foi alterada.")
            return True
        player.queue_load(playlist.tracks, replace=not append, source=f"playlist '{playlist.name}'")
        from musicmatch.services.player import is_track_available

        unavailable = sum(1 for t in playlist.tracks if not is_track_available(t))
        if unavailable:
            ctx.ui.render_warning(
                f"{_plural(unavailable)} com arquivo indisponível: "
                f"{_agree(unavailable, 'será pulada', 'serão puladas')} na reprodução."
            )
        if not append:
            from musicmatch.domain.player import PlayerState

            if player.state == PlayerState.STOPPED:
                ctx.ui.render_info("Use /queue-play para tocar.")
            else:
                ctx.ui.render_info("A faixa atual continua; a playlist começa em seguida.")
        return True


class PlaylistRenameCommand(_PlaylistCommand):
    usage = '/playlist-rename <nome> <novo nome>   (nome com espaços e seguido de outro argumento: use aspas se não for reconhecido)'

    def __init__(self) -> None:
        super().__init__("/playlist-rename", "Renomeia uma playlist: /playlist-rename <nome> <novo nome>")

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if len(args) < 2:
            return self._usage_error(ctx)
        service = _service(ctx)
        ref, rest = self._split_name(args, service, keep=1)
        summary = self._resolve(ref, service, ctx)
        if summary is None:
            return True
        new_name = self._valid_name(" ".join(rest), ctx)
        if new_name is None:
            return True
        if new_name == summary.name:
            ctx.ui.render_info(f"A playlist já se chama '{new_name}'.")
            return True
        taken = service.find_exact(new_name)
        if taken is not None and taken.id != summary.id:
            ctx.ui.render_error(f"Já existe uma playlist chamada '{taken.name}'.")
            return True
        renamed = service.rename(summary, new_name)
        ctx.ui.render_success(f"Playlist '{summary.name}' renomeada para '{renamed.name}'.")
        return True


class PlaylistRemoveCommand(_PlaylistCommand):
    usage = "/playlist-remove <nome> <id>  (todas as ocorrências)  ou  /playlist-remove <nome> #<posição>  (apenas uma entrada)"
    _MIN_PREFIX_HEX = 4  # Short Track ID rule (CONTEXT.md)

    def __init__(self) -> None:
        super().__init__(
            "/playlist-remove",
            "Remove faixas de uma playlist: /playlist-remove <nome> <id> (todas as ocorrências) | #<posição>",
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if len(args) < 2:
            return self._usage_error(ctx)
        service = _service(ctx)
        summary = self._resolve(" ".join(args[:-1]), service, ctx)  # the track reference is always the last word
        if summary is None:
            return True
        ref = args[-1]
        if ref.startswith("#"):
            return self._remove_position(ref, summary, service, ctx)
        return self._remove_track(ref, summary, service, ctx)

    def _remove_track(self, ref: str, summary: PlaylistSummary, service, ctx: CommandContext) -> bool:
        token = ref.strip().lower()
        prefix = token if token.startswith("trk_") else f"trk_{token}"
        hex_part = prefix[4:]
        if len(hex_part) < self._MIN_PREFIX_HEX or any(c not in "0123456789abcdef" for c in hex_part):
            ctx.ui.render_error(f"'{ref}' não é um ID de faixa: use ao menos {self._MIN_PREFIX_HEX} dígitos "
                                "hexadecimais (ex.: 3fa2b9c1) ou #<posição>.")
            return self._usage_error(ctx)
        playlist = service.get(summary.id)
        # Match against the playlist's own entries: a prefix only has to be unique within it.
        matches = {t.id: t for t in playlist.tracks if t.id.startswith(prefix)}
        if len(matches) > 1:
            ctx.ui.render_error(f"O ID '{ref}' é ambíguo na playlist '{playlist.name}': informe mais caracteres.")
            return True
        if not matches:
            ctx.ui.render_warning(f"A faixa '{ref}' não está na playlist '{playlist.name}' (veja /playlist {playlist.name}).")
            return True
        track = next(iter(matches.values()))
        removed = service.remove_track(summary, track.id)
        ctx.ui.render_success(
            f"{_plural(removed, 'ocorrência')} de {track.artist} - {track.title} "
            f"{_agree(removed, 'removida', 'removidas')} da playlist '{playlist.name}'."
        )
        self._report_if_empty(playlist.track_count - removed, playlist.name, ctx)
        return True

    def _remove_position(self, token: str, summary: PlaylistSummary, service, ctx: CommandContext) -> bool:
        try:
            position = int(token[1:])
        except ValueError:
            return self._usage_error(ctx)
        removed = service.remove_at(summary, position)
        if removed is None:
            ctx.ui.render_error(f"Não há entrada na posição {position} da playlist '{summary.name}' "
                                f"(veja /playlist {summary.name}).")
            return True
        ctx.ui.render_success(f"Removida da posição {position} da playlist '{summary.name}': {removed.artist} - {removed.title}.")
        remaining = service.get(summary.id)
        copies = sum(1 for t in remaining.tracks if t.id == removed.id)
        if copies:
            ctx.ui.render_info(f"Esta faixa ainda aparece {copies}x na playlist; para remover todas: "
                               f"/playlist-remove {summary.name} {removed.id[4:12]}")
        self._report_if_empty(remaining.track_count, summary.name, ctx)
        return True

    @staticmethod
    def _report_if_empty(remaining: int, name: str, ctx: CommandContext) -> None:
        if remaining == 0:
            ctx.ui.render_info(f"A playlist '{name}' agora está vazia (exclua com /playlist-delete {name}).")


class PlaylistDeleteCommand(_PlaylistCommand):
    usage = "/playlist-delete <nome>"

    def __init__(self) -> None:
        super().__init__("/playlist-delete", "Exclui uma playlist; as faixas continuam na biblioteca: /playlist-delete <nome>")

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args:
            return self._usage_error(ctx)
        service = _service(ctx)
        summary = self._resolve(" ".join(args), service, ctx)
        if summary is None:
            return True
        if not _confirm(
            f"Excluir a playlist '{summary.name}' ({_plural(summary.track_count)})? "
            "As faixas continuam na biblioteca e na fila."
        ):
            ctx.ui.render_info("Operação cancelada: nada foi alterado.")
            return True
        service.delete(summary)
        ctx.ui.render_success(f"Playlist '{summary.name}' excluída. Nenhuma faixa foi removida da biblioteca.")
        return True


class PlaylistDeleteWithTracksCommand(_PlaylistCommand):
    usage = "/playlist-delete-with-tracks <nome>"

    def __init__(self) -> None:
        super().__init__(
            "/playlist-delete-with-tracks",
            "Exclui a playlist e envia os arquivos das faixas para a Lixeira, removendo-as do catálogo: "
            "/playlist-delete-with-tracks <nome>",
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args:
            return self._usage_error(ctx)
        service = _service(ctx)
        summary = self._resolve(" ".join(args), service, ctx)
        if summary is None:
            return True
        playlist = service.get(summary.id)
        tracks = list({t.id: t for t in playlist.tracks}.values())  # each track once, in playlist order
        if not tracks:
            ctx.ui.render_info(f"A playlist '{playlist.name}' não tem faixas: use /playlist-delete para excluí-la.")
            return True

        count = len(tracks)
        ctx.ui.render_warning(
            f"ATENÇÃO: a playlist '{playlist.name}' será excluída e os arquivos de {_plural(count)} serão "
            "movidos para a Lixeira do sistema, saindo do catálogo."
        )
        for track in tracks[:10]:
            ctx.ui.render_info(f"  • {track.artist} - {track.title}  ({track.file_path})")
        if count > 10:
            ctx.ui.render_info(f"  … e mais {_plural(count - 10)}.")
        if any(self._is_external(t.file_path) for t in tracks):
            ctx.ui.render_warning("AVISO: parte dos arquivos reside fora da pasta da Biblioteca Gerenciada!")
        others = service.other_playlists_with([t.id for t in tracks], playlist)
        if others:
            listed = ", ".join(f"'{n}'" for n in others[:5]) + (" …" if len(others) > 5 else "")
            ctx.ui.render_warning(f"Estas faixas também saem de outras playlists: {listed}.")
        player = _player(ctx)
        status = player.status()
        doomed = {t.id for t in tracks}
        queued = sum(1 for t in status.queue if t.id in doomed)
        if queued:
            ctx.ui.render_warning(
                f"{_plural(queued, 'entrada')} da fila de reprodução também {_agree(queued, 'será removida', 'serão removidas')}."
            )

        ctx.ui.render_info(f"Para confirmar, digite exatamente o número de faixas afetadas ({count}):")
        try:
            typed = input("Confirmação de contagem: ").strip()
        except (KeyboardInterrupt, EOFError):
            typed = ""
        if typed != str(count):
            ctx.ui.render_error("Contagem incorreta ou cancelada. Nada foi excluído.")
            return True

        if status.current is not None and status.current.id in doomed:
            player.stop()  # release the file: an open file cannot be moved to the Recycle Bin on Windows
        from musicmatch.services.maintenance import LibraryMaintenanceService

        deleted, errors, playlist_deleted = service.delete_with_tracks(
            playlist, LibraryMaintenanceService(repository=ctx.db)
        )
        for track_id in doomed:
            if ctx.db.get_track(track_id) is None:
                player.queue_remove(track_id)
        for error in errors:
            ctx.ui.render_error(error)
        if playlist_deleted:
            moved = _agree(deleted, "movida para a Lixeira e removida", "movidas para a Lixeira e removidas")
            ctx.ui.render_success(f"Playlist '{playlist.name}' excluída; {_plural(deleted)} {moved} do catálogo.")
        else:
            failed = count - deleted
            ctx.ui.render_warning(
                f"{_plural(deleted)} {_agree(deleted, 'excluída', 'excluídas')}; {_plural(failed)} "
                f"{_agree(failed, 'não pôde ser movida', 'não puderam ser movidas')} para a Lixeira. "
                f"A playlist '{playlist.name}' foi mantida só com {_agree(failed, 'ela', 'elas')}: "
                "corrija o problema e repita o comando."
            )
        return True

    @staticmethod
    def _is_external(file_path: str) -> bool:
        from musicmatch.services.location import library_location_manager

        try:
            root = library_location_manager.resolve_library_path().resolve()
            return root not in Path(file_path).resolve().parents
        except Exception:
            return True


class PlaylistImportCommand(_PlaylistCommand):
    usage = "/playlist-import <arquivo.m3u|.m3u8> [nome]"

    def __init__(self) -> None:
        super().__init__("/playlist-import", "Cria uma playlist a partir de um arquivo .m3u/.m3u8: /playlist-import <arquivo> [nome]")

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args:
            return self._usage_error(ctx)
        from musicmatch.services.playlists import PlaylistFileError

        source, rest = self._split_path(args)
        name = self._valid_name(" ".join(rest) or source.stem, ctx)
        if name is None:
            return True
        service = _service(ctx)
        existing = service.find_exact(name)
        if existing is not None and not _confirm(
            f"A playlist '{existing.name}' ({_plural(existing.track_count)}) já existe e será substituída "
            f"pelo conteúdo de '{source.name}'. Continuar?"
        ):
            ctx.ui.render_info("Operação cancelada: nada foi alterado. Informe outro nome: /playlist-import <arquivo> <nome>")
            return True
        try:
            result = service.import_m3u(source, name, existing)
        except PlaylistFileError as exc:
            ctx.ui.render_error(str(exc))
            return True
        ctx.ui.render_playlist_import(result)
        return True


    @staticmethod
    def _split_path(tokens: Sequence[str]) -> Tuple[Path, List[str]]:
        """Longest leading run of words that is an existing file, so unquoted paths with spaces
        work (/playlist-import D:\\My Music\\mix.m3u Road Trip); otherwise the first word."""
        for size in range(len(tokens), 0, -1):
            candidate = Path(" ".join(tokens[:size])).expanduser()
            if candidate.is_file():
                return candidate, list(tokens[size:])
        return Path(tokens[0]).expanduser(), list(tokens[1:])


class PlaylistExportCommand(_PlaylistCommand):
    usage = "/playlist-export <nome> [arquivo.m3u8 | pasta] [--relative]"
    flags = ("--relative",)

    def __init__(self) -> None:
        super().__init__(
            "/playlist-export",
            "Grava a playlist em .m3u8 (padrão: <biblioteca>/Playlists): /playlist-export <nome> [arquivo | pasta] [--relative]",
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        parsed = self._split_flags(args, ctx)
        if parsed is None:
            return True
        positional, flags = parsed
        if not positional:
            return self._usage_error(ctx)
        from musicmatch.services.playlists import PlaylistFileError

        service = _service(ctx)
        ref, rest = self._split_name(positional, service)
        summary = self._resolve(ref, service, ctx)
        if summary is None:
            return True
        try:
            target = service.export_target(summary, " ".join(rest) or None)
        except PlaylistFileError as exc:
            ctx.ui.render_error(str(exc))
            return True
        if target.exists() and not _confirm(f"O arquivo '{target}' já existe e será sobrescrito. Continuar?"):
            ctx.ui.render_info("Operação cancelada: nada foi gravado.")
            return True
        try:
            result = service.export_m3u(service.get(summary.id), target, relative="--relative" in flags)
        except PlaylistFileError as exc:
            ctx.ui.render_error(str(exc))
            return True
        kind = "relativos" if result.relative_paths else "absolutos"
        ctx.ui.render_success(f"Playlist '{summary.name}' exportada ({_plural(result.entries)}, caminhos {kind}): {result.path}")
        if result.absolute_fallbacks:
            ctx.ui.render_warning(
                f"{_plural(result.absolute_fallbacks)} em outra unidade de disco: gravada(s) com caminho absoluto."
            )
        return True


PLAYLIST_COMMANDS = [
    PlaylistCommand,
    PlaylistSaveCommand,
    PlaylistLoadCommand,
    PlaylistRenameCommand,
    PlaylistRemoveCommand,
    PlaylistDeleteCommand,
    PlaylistDeleteWithTracksCommand,
    PlaylistImportCommand,
    PlaylistExportCommand,
]

__all__ = [cls.__name__ for cls in PLAYLIST_COMMANDS] + ["PLAYLIST_COMMANDS"]
