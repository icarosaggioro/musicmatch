"""Harness de Execução e Loop de Eventos (Event Loop) do MusicMatch.

CONCEITO ARQUITETURAL DIDÁTICO:
--------------------------------
O 'Harness' (arnês ou chassi) é o orquestrador do ciclo de vida da aplicação interativa.
Ele implementa o padrão de 'Event Loop' (Loop de Eventos), separando três preocupações distintas:

1. ENTRADA (Input): Lê a intenção do usuário via terminal.
2. ROTEAMENTO (Routing):
   - Se for um comando de sistema (inicia com '/' ou palavra de saída) -> despacha para o 'CommandRegistry'.
   - Se for uma mensagem em linguagem natural -> despacha para o 'SingleTurnAgent' de IA.
3. FRONTEIRA DE ERROS (Error Boundary, ADR 0019):
   - Um erro inesperado num comando ou no agente é registrado com traceback no log de
     desenvolvimento (data/logs/musicmatch.log), a tela mostra uma linha com a referência e a
     sessão continua: o comando falhou, mas o estado da aplicação segue consistente.
   - Só um erro fatal (banco de dados danificado, memória esgotada) encerra o MusicMatch, de
     forma ordenada: o estado da reprodução é salvo e o código de saída é 1.
   - Problemas previstos com recursos (Issues) registrados durante o comando viram uma única
     linha de resumo ao final dele.
"""

import logging
import sys
from typing import Optional
from musicmatch.agent.core import SingleTurnAgent
from musicmatch.commands.base import CommandContext
from musicmatch.commands.registry import CommandRegistry
from musicmatch.config import settings
from musicmatch.diagnostics.logging_setup import is_fatal, log_path, log_unexpected
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository
from musicmatch.ui.renderer import ConsoleUI

logger = logging.getLogger(__name__)


class Harness:
    """Orquestrador do ciclo interativo REPL com separação de UI, Comandos e Agente."""

    exit_code: int = 0  # 1 after a fatal error (ADR 0019)

    def __init__(
        self,
        agent: Optional[SingleTurnAgent] = None,
        ui: Optional[ConsoleUI] = None,
        registry: Optional[CommandRegistry] = None,
        database: Optional[object] = None,
    ) -> None:
        self.ui = ui or ConsoleUI()
        self.registry = registry or CommandRegistry()
        self.db = database or SQLiteTrackRepository()
        
        # O agente pode ser injetado externamente (ex: em testes) ou instanciado
        if agent is not None:
            self.agent = agent
        else:
            try:
                self.agent = SingleTurnAgent()
            except ValueError as e:
                self.ui.render_error(f"Erro de Inicialização: {e}")
                self.ui.render_info("💡 Dica: Configure GEMINI_API_KEY no arquivo .env da raiz.")
                raise

        # Constrói o contexto compartilhado que será entregue a cada comando executado
        self.ctx = CommandContext(
            ui=self.ui,
            agent=self.agent,
            db=self.db,
            registry=self.registry,
        )

    def _announce_saved_playback(self) -> None:
        """Tells the user a queue / interrupted track can be continued (ADR 0016), without
        starting the audio engine: only the persisted rows are read."""
        db_path = getattr(self.db, "db_path", None)
        if not isinstance(db_path, str) or db_path == ":memory:" or not hasattr(self.ui, "render_saved_playback"):
            return
        try:
            from musicmatch.storage.playback_store import SQLitePlaybackStore

            store = SQLitePlaybackStore(db_path)
            try:
                queue, saved = store.load_queue(), store.load_session()
            finally:
                store.close()
            self.ui.render_saved_playback(len(queue), saved.track, saved.position_seconds,
                                        repeat=saved.repeat, consume=saved.consume)
        except Exception:
            pass  # a startup hint must never prevent the REPL from starting

    def _prepare_issues(self) -> None:
        """Startup (ADR 0019): retention, checks that need no user action, and one status line."""
        from musicmatch.services.issues import current_issue_reporter

        reporter = current_issue_reporter()
        if reporter is None:
            return
        try:
            purged = reporter.store.purge(settings.ISSUE_RETENTION_DAYS)
            if purged:
                logger.info("Issue retention: %d dismissed issue(s) purged", purged)
            if isinstance(self.db, SQLiteTrackRepository):
                from musicmatch.services.playlists import PlaylistService

                PlaylistService(self.db).report_empty_playlists()
            reporter.flush(timeout=2.0)
            reporter.take_new_count()  # counted in the startup line below, not as "new" later
            if hasattr(self.ui, "render_open_issues"):
                self.ui.render_open_issues(reporter.store.count("OPEN"))
        except Exception as exc:  # a startup hint must never prevent the REPL from starting
            log_unexpected("Could not prepare the issue register at startup", exc)

    def _announce_new_issues(self) -> None:
        """One summary line for the issues the last command registered (never one per problem)."""
        from musicmatch.services.issues import current_issue_reporter

        reporter = current_issue_reporter()
        if reporter is None or not hasattr(self.ui, "render_issue_notice"):
            return
        reporter.flush(timeout=2.0)
        self.ui.render_issue_notice(reporter.take_new_count())

    def _contain(self, raw_input: str, exc: Exception) -> bool:
        """Error boundary: logs the failure; returns False when MusicMatch must stop (fatal)."""
        command = raw_input.split()[0] if raw_input.split() else raw_input
        if is_fatal(exc):
            ref = log_unexpected(f"Fatal error while running {command!r}; shutting down", exc)
            logger.critical("Graceful shutdown after fatal error [ref %s]", ref)
            self.ui.render_fatal_error(ref, log_path())
            self.exit_code = 1
            return False
        ref = log_unexpected(f"Unexpected error while running {raw_input!r}", exc)
        self.ui.render_unexpected_error(command, ref, log_path(), reason=f"{type(exc).__name__}: {exc}")
        return True

    def start(self) -> None:
        """Inicia e mantém o Loop de Eventos (Event Loop) até solicitação de encerramento."""
        self.ui.render_banner(self.agent.model_name)
        self._announce_saved_playback()
        self._prepare_issues()

        # Alerta de inicialização: verifica se há faixas pendentes na Staging Area
        try:
            from musicmatch.services.downloader import audio_downloader_service
            active_sessions = audio_downloader_service.list_active_sessions()
            if active_sessions:
                self.ui.render_staging_alert(len(active_sessions))
        except Exception:
            pass

        running = True
        try:
            while running:
                raw_input = ""
                try:
                    raw_input = input("MusicMatch > ").strip()
                    if not raw_input:
                        continue

                    try:
                        # Roteamento: se for comando estruturado do harness
                        if self.registry.is_command(raw_input):
                            running = self.registry.dispatch(raw_input, self.ctx)
                        else:
                            # Roteamento: mensagem livre direcionada ao Agente Inteligente
                            self.agent.run(user_prompt=raw_input, log_callback=self.ui.render_event)
                    finally:
                        # Also after a failed command: what it registered before failing is real.
                        self._announce_new_issues()

                except (KeyboardInterrupt, EOFError):
                    self.ui.render_goodbye()
                    break
                except Exception as e:
                    running = self._contain(raw_input, e)
        finally:
            # Encerra a reprodução (ADR 0015): libera o dispositivo de áudio e o decodificador.
            # Só é importado se o player chegou a ser usado nesta sessão.
            player_module = sys.modules.get("musicmatch.services.player")
            if player_module is not None:
                player_module.shutdown_player_service()
            # Alerta de encerramento: lembra o usuário sobre faixas na Staging Area
            try:
                from musicmatch.services.downloader import audio_downloader_service
                active_sessions = audio_downloader_service.list_active_sessions()
                if active_sessions:
                    self.ui.render_staging_alert(len(active_sessions))
            except Exception:
                pass

