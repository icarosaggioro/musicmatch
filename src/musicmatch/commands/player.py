"""Playback Commands (ADR 0015, ADR 0017).

Transport:
    /play [id | text]       Plays a track now, by ID or by searching the catalog. '/play' alone
                            continues a paused track (also after restarting the app) or plays
                            the queue.
    /pause                  Pauses keeping the position (even across restarts); run again, or
                            '/play', to continue.
    /resume                 Continues a paused track.
    /stop                   Stops and resets to the start of the queue (the queue is kept).
    /next                   Skips to the next queued track.
    /volume [0-100]         Shows or sets the volume.

Play queue (every queue command is named '/queue-<action>'):
    /queue                  Shows the current track and the queue.
    /queue-play             Plays the queue (continues a paused queue entry).
    /queue-add <id>         Queues a track to play next (after the current one).
    /queue-add-last <id>    Appends a track to the end of the queue.
    /queue-remove <id|#n>   Removes every copy of a track, or only the entry at position n.
    /queue-clear            Empties the queue.
    /queue-repeat [on|off]  Repeats the whole queue (no argument: toggles).
    /queue-consume [on|off] Removes each track from the queue once played (no argument: toggles).
    /queue-shuffle          Shuffles the whole queue (the current track goes to the top).
    /queue-sort <key>       Sorts the whole queue by title, genre (then title), artist (then
                            title) or album (then track number); playback continues from the
                            current track at its new position.

'/play queue' is still accepted as the former spelling of '/queue-play'.

Track IDs may be abbreviated to any unique prefix of at least 4 hex digits ('trk_3fa2' or
'3fa2'); /list and /search show the short form. Feedback (now playing, missing files,
errors, end of queue) is rendered from player events, including the ones raised in the
background when a track ends and the queue advances.

The queue is a persistent list: played tracks stay in it until the user removes them; a
cursor marks the entry that plays next. The queue, the paused position, the volume and the
play counters are persisted in the catalog database (ADR 0016).
"""

import sys
from typing import List, Optional

from musicmatch.commands.base import Command, CommandContext
from musicmatch.domain.models import Track
from musicmatch.domain.player import QueueOrder, parse_queue_order
from musicmatch.services.track_lookup import find_track, id_prefix


def _player(ctx: CommandContext):
    """Process-wide player with the console attached as event listener (lazy: no audio import at startup)."""
    from musicmatch.services.player import get_player_service

    db_path = getattr(ctx.db, "db_path", None)
    player = get_player_service(db_path if isinstance(db_path, str) else None)
    if hasattr(ctx.ui, "render_player_event"):
        player.add_listener(ctx.ui.render_player_event)
    return player


def playback_summary(ctx: CommandContext) -> Optional[str]:
    """One line about the player for '/status', or None when there is nothing to tell. Uses the
    running player, else the saved session: looking at the status never starts the audio engine."""
    player_module = sys.modules.get("musicmatch.services.player")
    player = getattr(player_module, "_player", None)
    if player is not None:
        status = player.status()
        state, current, position = status.state.value, status.current, status.position_seconds
        volume, size = status.volume, len(status.queue)
    else:
        db_path = getattr(ctx.db, "db_path", None)
        if not isinstance(db_path, str) or db_path == ":memory:":
            return None
        from musicmatch.storage.playback_store import SQLitePlaybackStore

        store = SQLitePlaybackStore(db_path)
        try:
            saved, size = store.load_session(), len(store.load_queue())
        finally:
            store.close()
        state, volume = saved.state, saved.volume
        current = saved.track if state == "PAUSED" else None
        position = saved.position_seconds
    label = {"PLAYING": "▶ Tocando", "PAUSED": "⏸ Pausado"}.get(state, "⏹ Parado")
    if current is not None:
        label += f": {current.artist} - {current.title} [{_clock(position)} / {_clock(current.duration_seconds or 0)}]"
    if volume is not None:
        label += f" · volume {volume}%"
    return f"{label} · fila: {size} faixa(s)"


def _clock(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes:02d}:{secs:02d}"


def resolve_track(ref: str, ctx: CommandContext) -> Optional[Track]:
    """Resolves a full track ID or a unique short prefix; renders an error and returns None otherwise."""
    ref = ref.strip()
    track = ctx.db.get_track(ref) if hasattr(ctx.db, "get_track") else None
    if isinstance(track, Track):
        return track
    prefix = id_prefix(ref)
    if prefix:
        matches = ctx.db.find_tracks_by_id_prefix(prefix, limit=2) if hasattr(ctx.db, "find_tracks_by_id_prefix") else []
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            ctx.ui.render_error(f"O ID '{ref}' é ambíguo: informe mais caracteres.")
            return None
    ctx.ui.render_error(f"Faixa '{ref}' não encontrada no catálogo.")
    ctx.ui.render_info("Use /search <termo> ou /list para ver os IDs das faixas.")
    return None


class _PlayerCommand(Command):
    usage = ""

    def __init__(self, name: str, description: str, aliases: Optional[List[str]] = None) -> None:
        super().__init__()
        self._name = name
        self._description = description
        self._aliases = aliases or []
        self._default_error_messages = {"usage": f"Uso: {self.usage or name}"}

    def _usage_error(self, ctx: CommandContext) -> bool:
        ctx.ui.render_error(self.get_default_error_messages()["usage"])
        return True


def _play_queue(ctx: CommandContext) -> bool:
    player = _player(ctx)
    status = player.status()
    if not status.queue and not status.resume_available:
        ctx.ui.render_warning("A fila está vazia. Adicione faixas com /queue-add <id> ou /queue-add-last <id>.")
    else:
        player.play_queue()
    return True


class PlayCommand(_PlayerCommand):
    usage = "/play <id ou busca>  (sem argumentos: retoma a faixa pausada ou inicia a fila)"

    def __init__(self) -> None:
        super().__init__(
            "/play", "Reproduz uma faixa: /play <id ou busca>. Sem argumentos, retoma a faixa pausada ou inicia a fila.",
            ["/tocar"],
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        player = _player(ctx)
        if not args:
            from musicmatch.domain.player import PlayerState

            status = player.status()
            if player.state == PlayerState.PLAYING:
                ctx.ui.render_info("Já existe uma faixa tocando. Use /pause, /stop, /next ou /play <id ou busca>.")
            elif player.state == PlayerState.PAUSED or status.queue:
                player.play()  # outcome (playing / missing / errors) arrives as player events
            else:
                ctx.ui.render_warning("A fila está vazia.")
                ctx.ui.render_info(self.get_default_error_messages()["usage"])
            return True
        if len(args) == 1 and args[0].lower() in ("queue", "fila"):
            return _play_queue(ctx)  # former spelling of /queue-play, kept for muscle memory
        ref = " ".join(args)
        found = find_track(ctx.db, ref)
        if found.track is not None:
            player.play_track(found.track)
        elif found.candidates:
            ctx.ui.render_warning(f"Mais de uma faixa corresponde a '{ref}'. Escolha com /play <id>:")
            ctx.ui.render_search_results(found.candidates)
            if found.more:
                ctx.ui.render_info(f"Mostrando as {len(found.candidates)} primeiras: refine a busca.")
        else:
            ctx.ui.render_error(f"Nenhuma faixa encontrada para '{ref}'.")
            ctx.ui.render_info("Use /search <termo> ou /list para ver as faixas do catálogo.")
        return True


class ResumeCommand(_PlayerCommand):
    def __init__(self) -> None:
        super().__init__("/resume", "Continua a faixa pausada de onde parou.", ["/retomar"])

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        from musicmatch.domain.player import PlayerState

        player = _player(ctx)
        if player.state == PlayerState.PAUSED:
            player.resume()
        elif player.state == PlayerState.PLAYING:
            ctx.ui.render_info("A faixa já está tocando.")
        else:
            ctx.ui.render_info("Não há faixa pausada. Use /play para tocar a fila.")
        return True


class PauseCommand(_PlayerCommand):
    def __init__(self) -> None:
        super().__init__(
            "/pause", "Pausa mantendo a posição, mesmo ao sair do app (repita ou use /play para continuar).", ["/pausar"]
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not _player(ctx).toggle_pause():
            ctx.ui.render_info("Nada está tocando no momento.")
        return True


class StopCommand(_PlayerCommand):
    def __init__(self) -> None:
        super().__init__("/stop", "Para e volta ao início da fila (as faixas continuam na fila).", ["/parar"])

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not _player(ctx).stop():
            ctx.ui.render_info("Nada está tocando. A fila está posicionada na primeira faixa.")
        return True


class NextCommand(_PlayerCommand):
    def __init__(self) -> None:
        super().__init__("/next", "Avança para a próxima faixa da fila (a faixa atual permanece na fila).", ["/proxima", "/skip"])

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        player = _player(ctx)
        status = player.status()
        if not status.queue and status.current is None:
            ctx.ui.render_info("A fila está vazia e nada está tocando.")
            return True
        player.next()
        return True


class VolumeCommand(_PlayerCommand):
    usage = "/volume <0-100>"

    def __init__(self) -> None:
        super().__init__("/volume", "Exibe ou ajusta o volume: /volume [0-100]", ["/vol"])

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        player = _player(ctx)
        if not args:
            ctx.ui.render_info(f"🔊 Volume atual: {player.volume}%")
            return True
        try:
            volume = int(args[0].rstrip("%"))
            if not 0 <= volume <= 100:
                raise ValueError
        except ValueError:
            ctx.ui.render_error("O volume deve ser um número inteiro entre 0 e 100.")
            return True
        player.set_volume(volume)
        return True


class QueueCommand(_PlayerCommand):
    def __init__(self) -> None:
        super().__init__("/queue", "Exibe a faixa atual e a fila de reprodução.", ["/fila"])

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        ctx.ui.render_player_status(_player(ctx).status())
        return True


class QueuePlayCommand(_PlayerCommand):
    def __init__(self) -> None:
        super().__init__("/queue-play", "Reproduz a fila a partir da próxima faixa (ou continua a faixa pausada da fila).")

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        return _play_queue(ctx)


class QueueAddCommand(_PlayerCommand):
    usage = "/queue-add <id>  (toca em seguida, após a faixa atual)"

    def __init__(self) -> None:
        super().__init__("/queue-add", "Adiciona uma faixa para tocar em seguida: /queue-add <id>")

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args:
            return self._usage_error(ctx)
        track = resolve_track(" ".join(args), ctx)
        if track is not None:
            _player(ctx).queue_add_next(track)
        return True


class QueueAddLastCommand(_PlayerCommand):
    usage = "/queue-add-last <id>  (adiciona ao final da fila)"

    def __init__(self) -> None:
        super().__init__("/queue-add-last", "Adiciona uma faixa ao final da fila: /queue-add-last <id>")

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args:
            return self._usage_error(ctx)
        track = resolve_track(" ".join(args), ctx)
        if track is not None:
            _player(ctx).queue_add_last(track)
        return True


class QueueRemoveCommand(_PlayerCommand):
    usage = "/queue-remove <id>  (todas as ocorrências)  ou  /queue-remove #<posição>  (apenas uma entrada)"

    def __init__(self) -> None:
        super().__init__("/queue-remove", "Remove da fila: /queue-remove <id> (todas as cópias) | #<posição>")

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args:
            return self._usage_error(ctx)
        player = _player(ctx)
        if args[0].startswith("#"):
            return self._remove_position(args[0], player, ctx)
        ref = args[0].strip().lower()
        prefix = ref if ref.startswith("trk_") else f"trk_{ref}"
        # Match against the queue itself: the track may no longer exist in the catalog.
        queued = {t.id for t in player.status().queue if t.id == ref or t.id.startswith(prefix)}
        if len(queued) > 1:
            ctx.ui.render_error(f"O ID '{args[0]}' é ambíguo na fila: informe mais caracteres.")
            return True
        if not queued:
            ctx.ui.render_warning(f"A faixa '{args[0]}' não está na fila.")
            return True
        removed = player.queue_remove(queued.pop())
        ctx.ui.render_success(f"{removed} ocorrência(s) removida(s) da fila.")
        return True

    def _remove_position(self, token: str, player, ctx: CommandContext) -> bool:
        try:
            position = int(token[1:])
        except ValueError:
            return self._usage_error(ctx)
        removed = player.queue_remove_at(position)
        if removed is None:
            ctx.ui.render_error(f"Não há entrada na posição {position} da fila (veja /queue).")
            return True
        ctx.ui.render_success(f"Removida da posição {position}: {removed.artist} - {removed.title}.")
        return True


class QueueClearCommand(_PlayerCommand):
    def __init__(self) -> None:
        super().__init__("/queue-clear", "Esvazia a fila de reprodução (a faixa atual continua).")

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        removed = _player(ctx).queue_clear()
        ctx.ui.render_success(f"Fila esvaziada ({removed} faixa(s) removida(s)).")
        return True


_ON = ("on", "ligar", "ligado", "sim", "1")
_OFF = ("off", "desligar", "desligado", "nao", "não", "0")


class _QueueSwitchCommand(_PlayerCommand):
    """'/queue-<mode> [on|off]': no argument toggles; the player confirms with an event."""

    def _switch(self, args: List[str], current: bool, ctx: CommandContext) -> Optional[bool]:
        if not args:
            return not current
        if len(args) == 1 and args[0].lower() in _ON:
            return True
        if len(args) == 1 and args[0].lower() in _OFF:
            return False
        self._usage_error(ctx)
        return None


class QueueRepeatCommand(_QueueSwitchCommand):
    usage = "/queue-repeat [on|off]  (sem argumento: alterna)"

    def __init__(self) -> None:
        super().__init__("/queue-repeat", "Repete a fila inteira ao chegar ao fim: /queue-repeat [on|off] (sem argumento: alterna)")

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        player = _player(ctx)
        enabled = self._switch(args, player.repeat, ctx)
        if enabled is not None:
            player.set_repeat(enabled)  # confirmation arrives as a REPEAT_CHANGED event
        return True


class QueueConsumeCommand(_QueueSwitchCommand):
    usage = "/queue-consume [on|off]  (sem argumento: alterna)"

    def __init__(self) -> None:
        super().__init__(
            "/queue-consume",
            "Remove da fila cada faixa já tocada ao seguir para a próxima: /queue-consume [on|off] (sem argumento: alterna)",
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        player = _player(ctx)
        enabled = self._switch(args, player.consume, ctx)
        if enabled is not None:
            player.set_consume(enabled)  # confirmation arrives as a CONSUME_CHANGED event
        return True


def _check_reorderable(player, ctx: CommandContext) -> bool:
    """True when the queue has at least two entries; otherwise tells the user why nothing happens."""
    size = len(player.status().queue)
    if size == 0:
        ctx.ui.render_warning("A fila está vazia. Adicione faixas com /queue-add <id> ou /queue-add-last <id>.")
    elif size == 1:
        ctx.ui.render_info("A fila tem uma só faixa: nada a reordenar.")
    return size >= 2


class QueueShuffleCommand(_PlayerCommand):
    def __init__(self) -> None:
        super().__init__(
            "/queue-shuffle",
            "Embaralha a fila inteira; a faixa atual vai para o topo e as demais tocam em seguida.",
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        player = _player(ctx)
        if _check_reorderable(player, ctx):
            player.queue_shuffle()  # outcome arrives as a QUEUE_REORDERED event
        return True


class QueueSortCommand(_PlayerCommand):
    usage = "/queue-sort <title | genre | artist | album>"

    def __init__(self) -> None:
        super().__init__(
            "/queue-sort",
            "Ordena a fila inteira: /queue-sort <title | genre | artist | album> (a reprodução segue da faixa atual)",
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        order: Optional[QueueOrder] = parse_queue_order(" ".join(args)) if args else None
        if order is None:
            ctx.ui.render_error(self.get_default_error_messages()["usage"])
            ctx.ui.render_info(
                "title: nome da faixa · genre: gênero, depois nome da faixa · "
                "artist: artista, depois nome da faixa · album: álbum, depois número da faixa"
            )
            return True
        player = _player(ctx)
        if _check_reorderable(player, ctx):
            player.queue_sort(order)  # outcome arrives as a QUEUE_REORDERED event
        return True


PLAYER_COMMANDS = [
    PlayCommand,
    PauseCommand,
    ResumeCommand,
    StopCommand,
    NextCommand,
    VolumeCommand,
    QueueCommand,
    QueuePlayCommand,
    QueueAddCommand,
    QueueAddLastCommand,
    QueueRemoveCommand,
    QueueClearCommand,
    QueueRepeatCommand,
    QueueConsumeCommand,
    QueueShuffleCommand,
    QueueSortCommand,
]

__all__ = [cls.__name__ for cls in PLAYER_COMMANDS] + ["PLAYER_COMMANDS", "resolve_track"]
