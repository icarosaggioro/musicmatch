"""Padrão de Projeto Command (Command Pattern) para o Harness do MusicMatch.

CONCEITO ARQUITETURAL DIDÁTICO:
--------------------------------
O 'Command Pattern' transforma uma ação em um objeto isolado contendo todas as
informações necessárias para disparar a execução.

Por que usamos isso em vez de um 'if/elif/else' gigante no loop?
1. Open/Closed Principle (Princípio Aberto/Fechado): Para criar um novo comando
   (ex: '/playlist', '/export', '/benchmark'), criamos uma nova classe derivada de 'Command'
   e a registramos, sem jamais precisar alterar o código do loop de eventos.
2. Injeção de Contexto ('CommandContext'): Cada comando recebe tudo o que precisa
   (banco de dados, UI, agente de IA) de maneira explícita, evitando acoplamento
   a singletons ou variáveis globais.
3. Testabilidade: Podemos testar comandos individualmente passando contextos simulados (mocks).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List

@dataclass
class CommandContext:
    """Contexto de execução compartilhado fornecido a todos os comandos.
    
    Attributes:
        ui: Instância do renderizador de interface para exibir mensagens.
        agent: Instância do agente de IA para consultas ou verificações.
        db: Instância do banco de dados (atualmente MockDatabase, futuramente SQLite).
        registry: Referência ao registro geral de comandos (usado por /help).
    """
    ui: Any
    agent: Any
    db: Any
    registry: Any

class Command(ABC):
    """Classe base abstrata para todos os comandos de controle do sistema."""

    def __init__(self, name: str, description: str, aliases: List[str] = None) -> None:
        self.name = name
        self.description = description
        self.aliases = aliases or []

    @abstractmethod
    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        """Executa a lógica do comando.

        Args:
            args: Argumentos passados após o nome do comando (ex: ['C:/Musicas'] para '/scan C:/Musicas').
            ctx: Contexto do sistema com acesso à UI, Banco e Agente.

        Returns:
            bool: True se o loop de eventos deve continuar rodando;
                  False se o comando solicitar a finalização do programa (ex: /exit).
        """
        pass
