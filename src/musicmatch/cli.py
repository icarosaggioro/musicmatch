"""Ponto de Entrada de Linha de Comando (CLI Bootstrap) do MusicMatch.

CONCEITO ARQUITETURAL DIDÁTICO:
--------------------------------
Nesta arquitetura refatorada, o 'cli.py' deixa de acumular lógica de formatação,
strings soltas de terminal ou loops infinitos com múltiplos 'if/elif'.

Ele passa a atuar como um 'Thin Bootstrap' (Inicializador Leve):
1. Configura o diagnóstico (ADR 0019): o log de desenvolvimento (arquivo texto) e o
   registro de Problemas (Issues) no banco do catálogo. Só o ponto de entrada faz isso,
   para que testes e uso como biblioteca nunca escrevam nos dados reais.
2. Instancia as dependências necessárias e inicializa o 'Harness'.
3. Inicia o ciclo com 'harness.start()' e, ao sair, grava os Problemas pendentes.
"""

import sys

from musicmatch.diagnostics.logging_setup import configure_logging, log_unexpected
from musicmatch.harness.loop import Harness
from musicmatch.services.issues import configure_issue_reporter, shutdown_issue_reporter


def main() -> None:
    """Função principal executada pelo comando de terminal 'musicmatch'."""
    log_file = configure_logging()
    try:
        harness = Harness()
    except ValueError:
        # Erro de configuração inicial (ex: falta de chave no .env) já exibido pelo Harness
        sys.exit(1)
    except Exception as exc:
        ref = log_unexpected("MusicMatch failed to start", exc)
        print(f"❌ O MusicMatch não pôde iniciar. Detalhes em {log_file} (ref. {ref}).")
        sys.exit(1)

    exit_code = 0
    try:
        db_path = getattr(harness.db, "db_path", None)
        if isinstance(db_path, str) and db_path != ":memory:":
            configure_issue_reporter(db_path)
        harness.start()
        code = getattr(harness, "exit_code", 0)
        exit_code = code if isinstance(code, int) else 0
    except Exception as exc:  # outside every command's error boundary: the session cannot go on
        ref = log_unexpected("Unhandled error outside the command loop; shutting down", exc)
        print(f"\n⛔ O MusicMatch encontrou um erro inesperado e será encerrado. Detalhes em {log_file} (ref. {ref}).")
        exit_code = 1
    finally:
        shutdown_issue_reporter()  # persists issues still queued
    if exit_code:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
