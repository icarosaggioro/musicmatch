"""Camada de Apresentação (View / Renderer) do MusicMatch.

CONCEITO ARQUITETURAL DIDÁTICO:
--------------------------------
Este módulo segue o Princípio da Responsabilidade Única (SRP - Single Responsibility Principle).
Ele é o único responsável por formatar e exibir dados para o usuário na tela do console.

Vantagens desta separação:
1. O agente de IA e as ferramentas não precisam saber se a saída é um terminal,
   uma página Web (WebSocket) ou uma janela gráfica (Tauri/Electron).
2. Se no futuro decidirmos migrar para bibliotecas visuais como 'rich' ou 'Textual',
   apenas esta classe precisará ser modificada, deixando o restante do sistema intacto.
"""

import functools
import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from musicmatch.domain.music_keys import camelot_for_key_name

# Output from several threads (ADR 0019): playback events are rendered by background threads
# (auto-advance) while the REPL thread may be printing a multi-line view such as /queue. Every
# render_* method holds this lock, so blocks never interleave. Re-entrant: renderers call each
# other. Prompts (input) never hold it, so a background thread never waits for the user.
_OUTPUT_LOCK = threading.RLock()


def _serialized_output(cls):
    for name, member in list(vars(cls).items()):
        if (name.startswith("render_") or name == "clear_screen") and callable(member):
            setattr(cls, name, _with_output_lock(member))
    return cls


def _with_output_lock(method):
    @functools.wraps(method)
    def locked(*args, **kwargs):
        with _OUTPUT_LOCK:
            return method(*args, **kwargs)

    return locked


@_serialized_output
class ConsoleUI:
    """Responsável exclusivo pela renderização e formatação visual no terminal."""

    def __init__(self) -> None:
        # Garante suporte a UTF-8 no Windows (necessário para emojis e caracteres acentuados)
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")

    def render_banner(self, model_name: str) -> None:
        """Exibe o cabeçalho de boas-vindas da aplicação."""
        print("=" * 72)
        print("   🎵 MusicMatch - Laboratório de Agentes de IA & Engenharia de Áudio")
        print(f"   Modelo Conectado: {model_name}")
        print("=" * 72)
        print("Digite sua pergunta musical ou use comandos de controle (digite '/help').\n")

    def render_event(self, stage: str, message: str) -> None:
        """Renderiza os passos de observabilidade do ciclo ReAct do agente.
        
        Args:
            stage: Fase do raciocínio ('INPUT', 'TOOL_CALL', 'OBSERVATION', 'RESPONSE', 'ERROR').
            message: Conteúdo textual detalhando a fase.
        """
        if stage == "INPUT":
            print(f"\n>>> [USER PROMPT         ]: {message}")
        elif stage == "TOOL_CALL":
            print(f"⚙️   [AGENTE - TOOL CALL  ]: {message}")
        elif stage == "OBSERVATION":
            print(f"📦   [TOOL OBSERVATION    ]: {message}")
        elif stage == "ERROR":
            print(f"❌   [ERROR ERROR ERROR ER]: {message}")
        elif stage == "RESPONSE":
            print("\n" + "=" * 72)
            print(f"💬   [AGENT RESPONSE      ]: {message}")
            print("=" * 72 + "\n")

    def render_help(self, commands: List[Any]) -> None:
        """Exibe uma tabela formatada com todos os comandos disponíveis no sistema."""
        print("\n" + "-" * 72)
        print("📋 COMANDOS DISPONÍVEIS (Harness Commands):")
        print("-" * 72)
        width = max([10] + [len(cmd.name) for cmd in commands])
        for cmd in commands:
            aliases_str = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
            print(f"  {cmd.name:<{width}} : {cmd.description}{aliases_str}")
        print("-" * 72)
        print("💡 Dica: Mensagens normais sem barra '/' são enviadas diretamente ao Agente de IA.\n")

    def render_status(self, status_info: Dict[str, Any]) -> None:
        """Exibe o estado operacional atual do sistema."""
        print("\n" + "-" * 72)
        print("📊 STATUS ATUAL DO SISTEMA:")
        print("-" * 72)
        for key, value in status_info.items():
            print(f"  • {key:<24}: {value}")
        print("-" * 72 + "\n")

    def render_info(self, message: str) -> None:
        """Exibe uma mensagem informativa."""
        print(f"ℹ️    {message}")

    def render_success(self, message: str) -> None:
        """Exibe uma mensagem de sucesso."""
        print(f"✅   {message}")

    def render_error(self, message: str) -> None:
        """Exibe uma mensagem de erro visualmente destacada."""
        print(f"❌   {message}")

    def render_warning(self, message: str) -> None:
        """Exibe uma mensagem de aviso visualmente destacada."""
        print(f"⚠️   {message}")

    def render_track_page(
        self,
        tracks: List[Any],
        page: int,
        total_pages: int,
        total_count: int,
        start_idx: int = 1,
    ) -> None:
        """Exibe uma página de faixas formatadas com título e caminho."""
        print("\n" + "-" * 72)
        print(f"📑 BIBLIOTECA DE MÚSICAS [Página {page}/{total_pages} - Total: {total_count} faixa(s)]:")
        print("-" * 72)
        for i, t in enumerate(tracks, start=start_idx):
            artist_str = f" - {t.artist}" if getattr(t, "artist", None) else ""
            status_str = " ⚠️ [ARQUIVO INDISPONÍVEL]" if getattr(t, "status", None) == "MISSING" else ""
            print(f"  {i:>3}. {t.title}{artist_str}{status_str}")
            print(f"       {self._id_prefix(t)}Caminho: {t.file_path}")
        print("-" * 72)

    def render_search_results(self, tracks: List[Any]) -> None:
        """Exibe os resultados de busca formatados com caminhos e status de disponibilidade."""
        print("-" * 72)
        for i, t in enumerate(tracks, 1):
            status_str = " ⚠️ [ARQUIVO INDISPONÍVEL]" if getattr(t, "status", None) == "MISSING" else ""
            metrics = []
            if getattr(t, "bpm", None):
                metrics.append(f"{t.bpm:.0f} BPM")
            key = getattr(t, "musical_key", None)
            if isinstance(key, str) and key:
                camelot = camelot_for_key_name(key)
                metrics.append(f"{key} ({camelot})" if camelot else key)
            lufs = getattr(t, "lufs", None)
            if isinstance(lufs, (int, float)):
                metrics.append(f"{lufs:.1f} LUFS")
            plays = getattr(t, "play_count", 0)
            if isinstance(plays, int) and plays > 0:
                metrics.append(f"▶ {plays}x")
            metrics_str = f"({' · '.join(metrics)})" if metrics else ""
            genre_str = f"[{t.genre}]" if getattr(t, "genre", None) else ""
            print(f"  {i:>2}. {t.artist} - {t.title} {genre_str} {metrics_str}{status_str}")
            print(f"      {self._id_prefix(t)}Caminho: {t.file_path}")
        print("-" * 72)

    @staticmethod
    def short_id(track_id: Any) -> str:
        """Short, typeable form of a track ID ('trk_' + 8 hex digits); commands accept any unique prefix."""
        return track_id[:12] if isinstance(track_id, str) else ""

    def _id_prefix(self, track: Any) -> str:
        short = self.short_id(getattr(track, "id", None))
        return f"ID: {short} · " if short else ""

    # ------------------------------------------------------------------
    # Playback (ADR 0015)
    # ------------------------------------------------------------------

    @staticmethod
    def _plays_label(track: Any) -> str:
        count = getattr(track, "play_count", 0)
        return f"  · {count} reprodução(ões)" if isinstance(count, int) and count > 0 else ""

    @staticmethod
    def _track_label(track: Any) -> str:
        if track is None:
            return ""
        duration = getattr(track, "duration_seconds", None)
        clock = f" [{ConsoleUI._format_clock(duration)}]" if isinstance(duration, (int, float)) and duration > 0 else ""
        return f"{track.artist} - {track.title}{clock}"

    def render_player_event(self, event: Any) -> None:
        """Renders player notifications; background ones (auto-advance) redraw the prompt."""
        label = self._track_label(event.track)
        short = self.short_id(getattr(event.track, "id", None))
        kind = event.kind
        if kind in ("TRACK_FINISHED", "PLAY_COUNTED", "QUEUE_ENTRY_CONSUMED"):
            # Finished: the next TRACK_STARTED / QUEUE_ENDED already tells the story.
            # Counted: shown in /queue and /search instead of interrupting the prompt every song.
            # Consumed (consume mode): the entry simply disappears from /queue, as the user asked.
            return
        if kind == "TRACK_STARTED":
            line = f"▶️   Tocando agora: {label}"
        elif kind == "TRACK_MISSING":
            # One line: the path and what to do are in the issue (ADR 0019).
            line = f"⚠️   Faixa indisponível: {label} ({short}) — arquivo não encontrado (veja /issue)."
        elif kind == "TRACK_ERROR":
            line = f"❌   Não foi possível reproduzir {label} (veja /issue)."
        elif kind == "DEVICE_ERROR":
            line = f"❌   Reprodução indisponível: {event.message}"
        elif kind == "PAUSED":
            where = f" {event.message}" if event.message else ""
            line = f"⏸️   Pausado{where}: {label}  (use /pause ou /play para continuar)"
        elif kind == "RESUMED":
            where = f" {event.message}" if event.message else ""
            line = f"▶️   Continuando{where}: {label}"
        elif kind == "STOPPED":
            line = f"⏹️   Reprodução parada: {label}. {event.message or ''}".rstrip()
        elif kind == "QUEUE_ENDED":
            line = f"⏹️   {event.message or 'Fim da fila de reprodução.'}"
        elif kind == "VOLUME_CHANGED":
            line = f"🔊  {event.message}"
        elif kind == "QUEUE_CHANGED":
            line = f"➕  {label} — {event.message}"
        elif kind == "QUEUE_REORDERED":
            line = f"🔀  {event.message} Veja a nova ordem com /queue."
        elif kind in ("QUEUE_REPEATED", "REPEAT_CHANGED"):
            line = f"🔁  {event.message}"
        elif kind == "CONSUME_CHANGED":
            line = f"🧹  {event.message}"
        elif kind == "QUEUE_LOADED":
            line = f"📥  {event.message}"
        elif kind == "PERSISTENCE_ERROR":
            line = f"⚠️   {event.message} A reprodução continua normalmente."
        else:
            line = f"ℹ️    {event.message or kind}"
        if getattr(event, "background", False):
            print("\n" + line)
            print("MusicMatch > ", end="", flush=True)
        else:
            print(line)

    def render_player_status(self, status: Any) -> None:
        """Transport view for /queue: current track, position, volume and upcoming tracks."""
        from musicmatch.services.player import is_track_available

        icons = {"PLAYING": "▶️ ", "PAUSED": "⏸️ ", "STOPPED": "⏹️ "}
        state = getattr(status.state, "value", status.state)
        print("\n" + "=" * 72)
        print(f"🎧 REPRODUÇÃO  {icons.get(state, '')} {state}  ·  Volume {status.volume}%"
              + (f"  ·  Saída: {status.output_backend}" if status.output_backend else "")
              + f"  ·  Reproduções totais: {getattr(status, 'total_plays', 0)}")
        print("=" * 72)
        paused = state == "PAUSED"
        if status.current is not None:
            total = status.current.duration_seconds or 0.0
            ratio = min(1.0, status.position_seconds / total) if total > 0 else 0.0
            bar = "█" * int(round(ratio * 20)) + "░" * (20 - int(round(ratio * 20)))
            caption = "Pausado" if paused else "Agora"
            plays = self._plays_label(status.current)
            print(f"  {caption}: {status.current.artist} - {status.current.title}{plays}")
            print(f"         [{self._format_clock(status.position_seconds)} / {self._format_clock(total)}] [{bar}]")
            if paused:
                print("         ⏯  Use /pause ou /play para continuar deste ponto.")
        else:
            print("  Nada tocando.")
        print("-" * 72)
        if not status.queue:
            print("  Fila vazia. Use /queue-add <id> (tocar em seguida) ou /queue-add-last <id>.")
            if getattr(status, "repeat", False):
                print("  🔁 Repetir fila: ligado (/queue-repeat off para desligar).")
            if getattr(status, "consume", False):
                print("  🧹 Remover faixas tocadas: ligado (/queue-consume off para desligar).")
        else:
            current = getattr(status, "current_index", None)
            upcoming = getattr(status, "next_index", 0)
            modes = "  ·  🔁 repetir: ligado" if getattr(status, "repeat", False) else ""
            modes += "  ·  🧹 remover tocadas: ligado" if getattr(status, "consume", False) else ""
            print(f"  Fila ({len(status.queue)} faixa(s)){modes} — ▶ atual · ✓ já tocada nesta passagem:")
            for i, track in enumerate(status.queue):
                if i == current:
                    marker = "⏸" if paused else "▶"
                elif i < upcoming:
                    marker = "✓"
                else:
                    marker = " "
                warning = "" if is_track_available(track) else "  ⚠️ [ARQUIVO INDISPONÍVEL]"
                print(f"  {marker} {i + 1:>3}. {self._track_label(track)}  ({self.short_id(track.id)}){self._plays_label(track)}{warning}")
            print("  Remover uma entrada: /queue-remove #<posição> · todas as cópias: /queue-remove <id> · tudo: /queue-clear")
            print("  Ordem: /queue-shuffle · /queue-sort <title|genre|artist|album>"
                  " · Modos: /queue-repeat [on|off] · /queue-consume [on|off]")
        print("=" * 72 + "\n")

    # ------------------------------------------------------------------
    # Diagnostics: unexpected errors and Issues (ADR 0019)
    # ------------------------------------------------------------------

    _SEVERITY_ICONS = {"ERROR": "⛔", "WARNING": "⚠️ "}

    def render_unexpected_error(self, command: str, ref: str, log_file: Any = None, reason: str = "") -> None:
        """A bug, contained to the command that hit it: one line, with the log reference."""
        where = f" em {log_file}" if log_file else " no log"
        cause = f" ({self._shorten_end(reason, 100)})" if reason else ""
        print(f"❌   Erro inesperado ao executar '{command}'{cause}. O MusicMatch continua; "
              f"detalhes registrados{where} (ref. {ref}).")

    def render_fatal_error(self, ref: str, log_file: Any = None) -> None:
        where = f" em {log_file}" if log_file else ""
        print(f"\n⛔  Erro grave: o banco de dados ou a memória não permitem continuar com segurança. "
              f"O estado da reprodução foi salvo e o MusicMatch será encerrado. Detalhes{where} (ref. {ref}).")

    def render_issue_notice(self, new_count: int, background: bool = False) -> None:
        """One summary line for problems registered by the last command (never one line per problem)."""
        if new_count <= 0:
            return
        noun = "novo problema registrado" if new_count == 1 else "novos problemas registrados"
        line = f"🩺  {new_count} {noun} — veja /issue"
        if background:
            print("\n" + line)
            print("MusicMatch > ", end="", flush=True)
        else:
            print(line)

    def render_open_issues(self, open_count: int) -> None:
        """Startup line (ADR 0019), next to the queue status line."""
        if open_count > 0:
            print(f"🩺 Problemas em aberto: {open_count} · /issue para revisar\n")

    def render_issues(self, issues: List[Any], counts_by_kind: Dict[Any, int], total: int,
                      status: Optional[str] = "OPEN", other_count: int = 0) -> None:
        titles = {"OPEN": "PROBLEMAS EM ABERTO", "DISMISSED": "PROBLEMAS DISPENSADOS", None: "TODOS OS PROBLEMAS"}
        print("\n" + "=" * 72)
        extra = ""
        if status == "OPEN" and other_count:
            extra = f"  ·  dispensados: {other_count} (/issue --dismissed)"
        print(f"🩺 {titles.get(status, 'PROBLEMAS')} ({total}){extra}")
        print("=" * 72)
        if not issues:
            print("  Nenhum problema." if status != "OPEN" else "  Nenhum problema em aberto. 🎉")
            print("=" * 72 + "\n")
            return
        summary = " · ".join(f"{count}× {kind.label}" for kind, count in list(counts_by_kind.items())[:4])
        if summary:
            print(f"  {summary}")
            print("-" * 72)
        for issue in issues:
            icon = self._SEVERITY_ICONS.get(issue.severity, "•")
            muted = "  [dispensado]" if issue.status == "DISMISSED" else ""
            print(f"  #{issue.id:<5} {icon} {issue.kind.label}{muted}")
            repeats = f" · {issue.occurrences}x" if issue.occurrences > 1 else ""
            print(f"         {self._shorten(issue.subject, 58)}{repeats} · {issue.last_seen}")
        if total > len(issues):
            print(f"  … e mais {total - len(issues)} (mostrando os {len(issues)} mais recentes).")
        print("-" * 72)
        print("  Detalhes: /issue <id> · Dispensar: /issue-dismiss <id | --all> · Apagar: /issue-delete <id | --all>")
        print("=" * 72 + "\n")

    def render_issue(self, issue: Any) -> None:
        print("\n" + "=" * 72)
        icon = self._SEVERITY_ICONS.get(issue.severity, "•")
        status = "dispensado" if issue.status == "DISMISSED" else "em aberto"
        print(f"🩺 Problema #{issue.id} · {icon} {issue.kind.label} · {status}")
        print("=" * 72)
        print(f"  Assunto:      {issue.subject}")
        if issue.subject_label and issue.subject_label != issue.subject_key:
            print(f"  Referência:   {issue.subject_key}")
        print(f"  Ocorrência:   {issue.message}")
        print(f"  Vezes:        {issue.occurrences} · primeira: {issue.first_seen} · última: {issue.last_seen}")
        origin = {"ENVIRONMENT": "ambiente (não é culpa do arquivo)", "RESOURCE": "recurso da biblioteca"}
        print(f"  Tipo:         {origin.get(issue.category, issue.category)} · origem: {issue.source or '-'}")
        for key, value in issue.details.items():
            if isinstance(value, list):
                print(f"  {key}: ({len(value)})")
                for item in value[:10]:
                    print(f"     {item}")
                if len(value) > 10:
                    print(f"     … e mais {len(value) - 10}.")
            else:
                print(f"  {key}: {value}")
        print("-" * 72)
        action = "Apagar" if issue.status == "DISMISSED" else f"Dispensar: /issue-dismiss {issue.id} · Apagar"
        print(f"  {action}: /issue-delete {issue.id}")
        print("=" * 72 + "\n")

    @staticmethod
    def _shorten(text: str, width: int) -> str:
        """Keeps the end (paths: the file name matters most)."""
        return text if len(text) <= width else "…" + text[-(width - 1):]

    @staticmethod
    def _shorten_end(text: str, width: int) -> str:
        return text if len(text) <= width else text[:width - 1] + "…"

    # ------------------------------------------------------------------
    # Playlists (ADR 0018)
    # ------------------------------------------------------------------

    def render_playlists(self, playlists: List[Any]) -> None:
        """/playlist: every saved playlist with its size and total duration."""
        print("\n" + "=" * 72)
        print(f"📜 PLAYLISTS ({len(playlists)})")
        print("=" * 72)
        if not playlists:
            print("  Nenhuma playlist salva. Crie uma com /playlist-save <nome> (a partir da fila)")
            print("  ou /playlist-import <arquivo.m3u8>.")
        else:
            width = min(40, max(len(p.name) for p in playlists))
            for p in playlists:
                print(f"  {p.name:<{width}}  {p.track_count:>5} faixa(s)  {self._format_clock(p.duration_seconds):>8}"
                      f"  · atualizada em {p.updated_at or '-'}")
            print("-" * 72)
            print("  Ver: /playlist <nome> · Tocar: /playlist-load <nome> · Salvar a fila: /playlist-save <nome>")
        print("=" * 72 + "\n")

    def render_playlist(self, playlist: Any) -> None:
        """/playlist <name>: the entries in order, flagging unavailable files like /queue."""
        from musicmatch.services.player import is_track_available

        print("\n" + "=" * 72)
        print(f"📜 {playlist.name}  ·  {playlist.track_count} faixa(s)  ·  {self._format_clock(playlist.duration_seconds)}")
        print("=" * 72)
        if not playlist.tracks:
            print("  Playlist vazia.")
        for i, track in enumerate(playlist.tracks):
            warning = "" if is_track_available(track) else "  ⚠️ [ARQUIVO INDISPONÍVEL]"
            print(f"  {i + 1:>4}. {self._track_label(track)}  ({self.short_id(track.id)}){self._plays_label(track)}{warning}")
        print("-" * 72)
        print("  Remover uma entrada: /playlist-remove <nome> #<posição> · todas as cópias: /playlist-remove <nome> <id>")
        print("  Tocar: /playlist-load <nome> [--append] · Exportar: /playlist-export <nome> · Renomear: /playlist-rename")
        print("=" * 72 + "\n")

    def render_playlist_import(self, result: Any) -> None:
        """/playlist-import: what was matched, and what to do about the rest."""
        if result.playlist is None:
            self.render_error(f"Nenhuma das {result.total_entries} entrada(s) de '{result.source_path}' "
                              "corresponde a faixas do catálogo: a playlist não foi criada.")
        else:
            via_tags = f" ({result.matched_by_tags} reconhecida(s) por artista/título)" if result.matched_by_tags else ""
            self.render_success(f"Playlist '{result.playlist.name}' importada: {result.matched} de "
                                f"{result.total_entries} entrada(s){via_tags}.")
        if result.not_in_catalog:
            folders = sorted({str(Path(p).parent) for p in result.not_in_catalog})
            self.render_warning(f"{len(result.not_in_catalog)} arquivo(s) existem no disco mas não estão no catálogo. "
                                "Indexe as pastas e importe de novo:")
            for folder in folders[:5]:
                print(f"     /scan \"{folder}\"")
            if len(folders) > 5:
                print(f"     … e mais {len(folders) - 5} pasta(s).")
        if result.missing_files:
            self.render_warning(f"{len(result.missing_files)} arquivo(s) não encontrados no disco nem no catálogo:")
            for path in result.missing_files[:5]:
                print(f"     {path}")
            if len(result.missing_files) > 5:
                print(f"     … e mais {len(result.missing_files) - 5}.")
        if result.remote_entries:
            self.render_warning(f"{len(result.remote_entries)} entrada(s) da web (streams/URLs) ignorada(s): "
                                "só arquivos locais são suportados.")

    # ------------------------------------------------------------------
    # Acoustic analysis (ADR 0014)
    # ------------------------------------------------------------------

    @staticmethod
    def _format_clock(seconds: Optional[float]) -> str:
        if seconds is None:
            return "--:--"
        minutes, secs = divmod(int(seconds), 60)  # elapsed time is truncated, never rounded up
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"

    def render_analysis_progress(self, event: Any) -> None:
        """Linha de progresso reescrita no lugar (\r); falhas ficam registradas em linha própria.

        Fora de um terminal interativo (logs, saída redirecionada) imprime apenas falhas e
        marcos de ~5% em linhas próprias, em vez de acumular sequências de '\r'.
        """
        if not sys.stdout.isatty():
            milestone = max(1, event.total // 20)
            if event.outcome == "ERROR":
                print(f"   ✗ Falha: {event.label} — {event.message}")
            if event.completed == event.total or event.completed % milestone == 0:
                print(
                    f"   [{event.completed}/{event.total}] {event.percent:.0f}% "
                    f"(ETA {self._format_clock(event.eta_seconds)})",
                    flush=True,
                )
            return
        width = max(60, min(shutil.get_terminal_size((100, 20)).columns, 140) - 1)
        icon = {"OK": "✓", "ERROR": "✗", "SKIPPED": "·"}.get(event.outcome, "?")
        if event.outcome == "ERROR":
            print("\r" + " " * width + "\r", end="")
            print(f"   ✗ Falha: {event.label} — {event.message}")
        prefix = f"   [{event.completed:>{len(str(event.total))}}/{event.total}] {event.percent:5.1f}% {icon} "
        suffix = f"  ETA {self._format_clock(event.eta_seconds)}"
        room = max(10, width - len(prefix) - len(suffix))
        label = event.label if len(event.label) <= room else event.label[: room - 1] + "…"
        print("\r" + f"{prefix}{label:<{room}}{suffix}", end="", flush=True)
        if event.completed >= event.total:
            print()

    def render_analysis_summary(self, result: Any) -> None:
        """Resumo consolidado de uma execução do /analyze."""
        print("\n" + "=" * 72)
        title = "⏹️  ANÁLISE ACÚSTICA INTERROMPIDA" if result.cancelled else "🎛️  ANÁLISE ACÚSTICA CONCLUÍDA"
        print(title)
        print("=" * 72)
        print(f"  • Faixas selecionadas   : {result.total_candidates}")
        print(f"  • Analisadas com sucesso: {result.analyzed_ok}")
        print(f"  • Falhas registradas    : {result.failed}")
        print(f"  • Ignoradas             : {result.skipped}")
        print(f"  • Ainda pendentes       : {result.remaining_pending}")
        print(f"  • Decodificador / Workers: {result.decoder} / {result.workers}")
        print(f"  • Tempo total           : {self._format_clock(result.duration_ms / 1000.0)}")
        if result.failures:
            print("-" * 72)
            print("  Amostra de falhas:")
            for failure in result.failures:
                print(f"    - {failure}")
        print("=" * 72 + "\n")

    def render_analysis_coverage(self, coverage: Any) -> None:
        """Cobertura da análise acústica no catálogo."""
        print("\n" + "=" * 72)
        print("🎛️  COBERTURA DA ANÁLISE ACÚSTICA:")
        print("=" * 72)
        print(f"  • Faixas disponíveis     : {coverage.available_tracks}")
        print(f"  • Analisadas (atuais)    : {coverage.analyzed_tracks}")
        print(f"  • Com falha de leitura   : {coverage.failed_tracks}")
        print(f"  • Pendentes              : {coverage.pending_tracks}")
        print(f"  • Decodificador          : {coverage.decoder}")
        if not coverage.decoder_available:
            formats = "/".join(getattr(coverage, "supported_formats", None) or ["WAV"])
            print(f"  ⚠️  Sem FFmpeg apenas arquivos {formats} podem ser analisados.")
            print("     Instale o FFmpeg ou defina MUSICMATCH_FFMPEG_PATH no .env.")
        print("=" * 72 + "\n")

    def render_track_analysis(self, track: Any, analysis: Any) -> None:
        """Detalhe das métricas acústicas de uma faixa."""
        print("\n" + "=" * 72)
        print(f"🎛️  ANÁLISE ACÚSTICA: {track.artist} - {track.title}")
        print("=" * 72)
        print(f"  Arquivo : {track.file_path}")
        print(f"  Analisado em: {analysis.analyzed_at} (versão {analysis.analysis_version})")
        if analysis.status != "OK" or analysis.features is None:
            print(f"  ❌ Falha na análise: {analysis.error_message}")
            print("=" * 72 + "\n")
            return
        f = analysis.features

        def fmt(value: Any, unit: str = "", digits: int = 1) -> str:
            return f"{value:.{digits}f}{unit}" if isinstance(value, (int, float)) else "—"

        print("-" * 72)
        print(f"  Loudness integrado : {fmt(f.integrated_lufs, ' LUFS')}  (EBU R128)")
        print(f"  Loudness Range     : {fmt(f.loudness_range_lu, ' LU')}")
        print(f"  Pico de amostra    : {fmt(f.sample_peak_dbfs, ' dBFS')}")
        print(f"  Andamento          : {fmt(f.bpm, ' BPM')}  (confiança {f.bpm_confidence:.0%})")
        if getattr(track, "bpm_source", None) == "tag":
            print(f"  Andamento na tag   : {fmt(track.bpm, ' BPM')}  (mantido no catálogo)")
        if f.musical_key:
            confidence = f" (confiança {f.key_confidence:.0%})" if f.key_confidence is not None else ""
            print(f"  Tonalidade         : {f.musical_key} · Camelot {f.camelot_key}{confidence}")
            print(f"  Afinação           : {fmt(f.tuning_cents, ' cents')} em relação a A=440 Hz")
        else:
            print("  Tonalidade         : —")
        print(f"  Duração decodificada: {self._format_clock(f.duration_seconds)} · {f.channels} canal(is) · {f.decoder}")
        fingerprint = f"{f.fingerprint_algorithm} · {f.fingerprint_frames} quadros" if f.fingerprint_hash else "— (silêncio ou curta demais)"
        print(f"  Fingerprint        : {fingerprint}")
        if f.waveform_peaks:
            print(f"  Waveform           : {self._sparkline(f.waveform_peaks)}")
        print("=" * 72 + "\n")

    @staticmethod
    def _sparkline(values: List[float], width: int = 60) -> str:
        blocks = " ▁▂▃▄▅▆▇█"
        if not values:
            return ""
        step = len(values) / width if len(values) > width else 1.0
        picked = [max(values[int(i * step): max(int(i * step) + 1, int((i + 1) * step))]) for i in range(min(width, len(values)))]
        return "".join(blocks[min(8, int(round(v * 8)))] for v in picked)

    # ------------------------------------------------------------------
    # Library audit (ADR 0013 / ADR 0014)
    # ------------------------------------------------------------------

    def render_audit_report(self, report: Any) -> None:
        print("\n" + "=" * 72)
        print("🩺 DIAGNÓSTICO DE INTEGRIDADE DA BIBLIOTECA:")
        print("=" * 72)
        print(f"  • Total de Faixas no Catálogo: {report.total_tracks}")
        print(f"  • Faixas Acessíveis no Disco : {report.available_tracks} (OK)")
        print(f"  • Faixas Indisponíveis/MISSING: {report.missing_tracks}")
        print(f"  • Faixas com Metadados Falhos: {report.untagged_tracks}")
        print(f"  • Faixas com Bitrate Baixo   : {report.low_bitrate_tracks} (< 128 kbps)")
        print(f"  • Grupos de Músicas Duplicadas (tags): {report.duplicate_groups_count}")
        print(f"  • Análise Acústica           : {report.analyzed_tracks} analisada(s), {report.pending_analysis_tracks} pendente(s)")
        print(f"  • Duplicatas Acústicas Exatas: {report.acoustic_duplicate_groups_count} grupo(s)")
        if report.pending_analysis_tracks:
            print("    💡 Rode /analyze para medir LUFS, BPM, tonalidade e fingerprint das faixas pendentes.")
        if report.missing_sample:
            print("-" * 72)
            print("  Amostra de faixas indisponíveis no disco:")
            for m in report.missing_sample:
                print(f"    - {m.artist} - {m.title} [{m.file_path}]")
        print("=" * 72 + "\n")

    def render_duplicate_groups(self, groups: List[Any]) -> None:
        labels = {
            "METADATA": "tags (artista + título)",
            "EXACT_FINGERPRINT": "fingerprint acústico idêntico",
            "FUZZY_FINGERPRINT": "fingerprint acústico similar",
        }
        print("\n" + "=" * 72)
        print(f"👥 {len(groups)} GRUPO(S) DE DUPLICATAS ENCONTRADO(S):")
        print("=" * 72)
        for i, g in enumerate(groups, start=1):
            match_type = getattr(g, "match_type", "METADATA")
            evidence = labels.get(match_type, match_type)
            similarity = getattr(g, "similarity", None)
            if isinstance(similarity, (int, float)) and match_type != "METADATA":
                evidence += f", similaridade {similarity:.0%}"
            print(f"  Grupo {i}: {g.signature.upper()}  [{evidence}]")
            print(f"  💡 Recomendação: {g.recommendation_reason}")
            for t in g.tracks:
                star = " ⭐ [PRESERVAR]" if t.id == g.recommended_track_id else " 🗑️ [SUGERIDO EXCLUIR]"
                print(f"    - [{t.id}] {t.artist} - {t.title} ({t.bitrate_kbps} kbps, {t.duration_seconds:.0f}s){star}")
                print(f"      Caminho: {t.file_path}")
        print("=" * 72 + "\n")

    def prompt_pagination(self) -> str:
        """Solicita ação do usuário para controle da paginação."""
        try:
            return input("⏩ Pressione [Enter] para a próxima página ou ['q'/'c'] para cancelar: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return "q"

    def render_saved_playback(self, queue_size: int, last_track: Any, position_seconds: float,
                              repeat: bool = False, consume: bool = False) -> None:
        """One-line startup notice with the saved queue (ADR 0016) and its modes (ADR 0017)."""
        if not queue_size and last_track is None:
            return
        line = f"🎧 Fila: {queue_size} faixa(s)"
        if last_track is not None:
            line += f" · Última tocada: {last_track.artist} - {last_track.title} · Tempo: {self._format_clock(position_seconds)}"
        if repeat:
            line += " · 🔁 Repetir fila"
        if consume:
            line += " · 🧹 Remover tocadas"
        print(line + "\n")

    def render_goodbye(self) -> None:
        """Exibe a mensagem de encerramento da sessão."""
        print("\nEncerrando sessão do MusicMatch. Até logo!\n")

    def render_search_candidates(self, candidates: List[Dict[str, Any]]) -> None:
        """Exibe candidatos a download encontrados no YouTube."""
        print("\n" + "=" * 72)
        print("🔍 RESULTADOS DA BUSCA (Escolha uma opção de 1 a 5, ou 0 para cancelar):")
        print("=" * 72)
        for idx, item in enumerate(candidates, start=1):
            dur = int(item.get("duration") or 0)
            mins, secs = divmod(dur, 60)
            duration_str = f"{mins:02d}:{secs:02d}" if dur > 0 else "--:--"
            views = item.get("view_count") or 0
            views_str = f" | {views:,} views" if views else ""
            print(f"  [{idx}] {item.get('title', 'Sem Título')}")
            print(f"       Canal: {item.get('channel', 'Desconhecido')} | Duração: {duration_str}{views_str}")
        print("-" * 72 + "\n")

    def render_staging_sessions(self, sessions: List[Any]) -> None:
        """Exibe lista de sessões ativas na Staging Area."""
        print("\n" + "=" * 72)
        print("📥 SESSÕES ATIVAS NA STAGING AREA:")
        print("=" * 72)
        if not sessions:
            print("  Nenhuma sessão ativa no momento. Áudios baixados já promovidos ou descartados.")
        else:
            for s in sessions:
                created = s.created_at[:19].replace("T", " ") if hasattr(s, "created_at") else ""
                track_count = len(s.tracks) if hasattr(s, "tracks") else 0
                print(f"  • Sessão: {s.session_id}")
                print(f"    Criada em: {created} | Faixas: {track_count} | Origem: {s.query_or_url}")
                print(f"    Comandos: /staging show {s.session_id} | /staging discard {s.session_id}")
        print("-" * 72 + "\n")

    def render_staging_detail(self, session: Any) -> None:
        """Exibe os detalhes e faixas de uma sessão da Staging Area."""
        print("\n" + "=" * 72)
        print(f"📦 DETALHES DA SESSÃO [{session.session_id}]:")
        print("=" * 72)
        print(f"  Origem: {session.query_or_url}")
        print(f"  Status: {session.status}")
        print(f"  Total de Faixas: {len(session.tracks)}")
        print("-" * 72)
        for idx, track in enumerate(session.tracks, start=1):
            dur = int(track.duration_seconds)
            mins, secs = divmod(dur, 60)
            size_mb = track.file_size / (1024 * 1024)
            ext_tags = []
            if track.extended_metadata:
                for k, v in track.extended_metadata.items():
                    ext_tags.append(f"{k}: {v}")
            tags_str = f" [{', '.join(ext_tags)}]" if ext_tags else ""
            print(f"  {idx}. {track.artist} - {track.title}{tags_str}")
            print(f"     Formato: {track.format.upper()} | Duração: {mins:02d}:{secs:02d} | Tamanho: {size_mb:.2f} MB")
            print(f"     Arquivo: {track.file_path}")
        print("-" * 72 + "\n")

    def render_staging_alert(self, active_count: int) -> None:
        """Exibe alerta proeminente no início ou encerramento sobre arquivos pendentes na Staging Area."""
        if active_count <= 0:
            return
        plural = "sessões ativas" if active_count > 1 else "sessão ativa"
        print("\n" + "!" * 72)
        print(f"⚠️   ALERTA STAGING: Você possui {active_count} {plural} aguardando revisão!")
        print("    Faixas baixadas permanecem isoladas na Staging Area até serem promovidas.")
        print("    Use '/staging list' para ver as sessões ou '/staging show <id>' para inspecionar.")
        print("!" * 72 + "\n")

    def render_library_status(self, info: Dict[str, Any]) -> None:
        """Exibe informações sobre a localização e integridade da Biblioteca Gerenciada."""
        print("\n" + "=" * 72)
        print("🏛️  BIBLIOTECA GERENCIADA (Managed Library):")
        print("=" * 72)
        for k, v in info.items():
            print(f"  • {k:<20}: {v}")
        print("-" * 72 + "\n")

    def render_promotion_results(self, results: List[Any]) -> None:
        """Exibe o relatório consolidado da promoção de faixas para a Biblioteca Gerenciada."""
        print("\n" + "=" * 72)
        print("🚀 RESULTADO DA PROMOÇÃO PARA A BIBLIOTECA GERENCIADA:")
        print("=" * 72)
        promoted_count = sum(1 for r in results if getattr(r, "status", "") == "PROMOTED")
        collision_count = sum(1 for r in results if getattr(r, "status", "") == "COLLISION")
        error_count = sum(1 for r in results if getattr(r, "status", "") in ("ERROR", "NOT_FOUND"))

        for idx, res in enumerate(results, start=1):
            status = getattr(res, "status", "UNKNOWN")
            dest = getattr(res, "destination_path", "") or "(Nenhum destino)"
            msg = getattr(res, "error_message", None)

            if status == "PROMOTED":
                print(f"  [{idx}] ✅ PROMOVIDA COM SUCESSO:")
                print(f"       Destino: {dest}")
            elif status == "COLLISION":
                print(f"  [{idx}] ⚠️  COLISÃO DETECTADA (Arquivo retido na Staging Area):")
                print(f"       Destino existente: {dest}")
                if msg:
                    print(f"       Motivo: {msg}")
            else:
                print(f"  [{idx}] ❌ FALHA NA PROMOÇÃO:")
                if msg:
                    print(f"       Erro: {msg}")

        print("-" * 72)
        print(f"  Total: {promoted_count} promovida(s) | {collision_count} colisão(ões) | {error_count} erro(s)")
        print("=" * 72 + "\n")

    def clear_screen(self) -> None:
        """Limpa o console de maneira compatível com Windows e Unix."""
        os.system("cls" if os.name == "nt" else "clear")


