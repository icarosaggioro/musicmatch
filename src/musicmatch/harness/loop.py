"""Harness de Execução e Loop de Eventos (Event Loop) do MusicMatch.

CONCEITO ARQUITETURAL DIDÁTICO:
--------------------------------
O 'Harness' (arnês ou chassi) é o orquestrador do ciclo de vida da aplicação interativa.
Ele implementa o padrão de 'Event Loop' (Loop de Eventos), separando três preocupações distintas:

1. ENTRADA (Input): Lê a intenção do usuário via terminal.
2. ROTEAMENTO (Routing):
   - Se for um comando de sistema (inicia com '/' ou palavra de saída) -> despacha para o 'CommandRegistry'.
   - Se for uma mensagem em linguagem natural -> despacha para o 'SingleTurnAgent' de IA.
3. FRONTEIRA DE ERROS (Error Boundary):
   - Se ocorrer um erro durante uma chamada de API ou execução de comando, o Harness
     intercepta a falha, exibe uma mensagem elegante via 'ConsoleUI' e mantém a sessão viva,
     impedindo que uma exceção derrube o terminal do usuário.
"""

from typing import Optional
from musicmatch.agent.core import SingleTurnAgent
from musicmatch.commands.base import CommandContext
from musicmatch.commands.registry import CommandRegistry
from musicmatch.config import settings
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository
from musicmatch.ui.renderer import ConsoleUI

class Harness:
    """Orquestrador do ciclo interativo REPL com separação de UI, Comandos e Agente."""

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

    def start(self) -> None:
        """Inicia e mantém o Loop de Eventos (Event Loop) até solicitação de encerramento."""
        self.ui.render_banner(self.agent.model_name)

        running = True
        while running:
            try:
                raw_input = input("MusicMatch > ").strip()
                if not raw_input:
                    continue

                # Roteamento: se for comando estruturado do harness
                if self.registry.is_command(raw_input):
                    running = self.registry.dispatch(raw_input, self.ctx)
                else:
                    # Roteamento: mensagem livre direcionada ao Agente Inteligente
                    self.agent.run(user_prompt=raw_input, log_callback=self.ui.render_event)

            except (KeyboardInterrupt, EOFError):
                self.ui.render_goodbye()
                break
            except Exception as e:
                self.ui.render_error(f"Ocorreu um erro durante a execução: {e}")
