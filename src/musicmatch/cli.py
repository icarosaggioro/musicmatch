"""Ponto de Entrada de Linha de Comando (CLI Bootstrap) do MusicMatch.

CONCEITO ARQUITETURAL DIDÁTICO:
--------------------------------
Nesta arquitetura refatorada, o 'cli.py' deixa de acumular lógica de formatação,
strings soltas de terminal ou loops infinitos com múltiplos 'if/elif'.

Ele passa a atuar como um 'Thin Bootstrap' (Inicializador Leve):
1. Apenas instancia as dependências necessárias.
2. Inicializa o 'Harness' (que orquestra o loop de eventos e comandos).
3. Inicia o ciclo com 'harness.start()'.
"""

import sys
from musicmatch.harness.loop import Harness

def main() -> None:
    """Função principal executada pelo comando de terminal 'musicmatch'."""
    try:
        harness = Harness()
        harness.start()
    except ValueError:
        # Erro de configuração inicial (ex: falta de chave no .env) já logado pelo Harness
        sys.exit(1)

if __name__ == "__main__":
    main()
