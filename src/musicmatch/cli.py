"""Interface de Linha de Comando (CLI REPL) do MusicMatch."""

import sys
from musicmatch.agent.core import SingleTurnAgent
from musicmatch.config import settings

def format_log(stage: str, message: str) -> None:
    """Imprime eventos de observabilidade com marcadores textuais claros."""
    if stage == "INPUT":
        print(f"\n>>> [PROMPT RECEBIDO]: {message}")
    elif stage == "TOOL_CALL":
        print(f"⚙️  [DECISÃO DO AGENTE - TOOL CALL]: {message}")
    elif stage == "OBSERVATION":
        print(f"📦 [OBSERVAÇÃO DA FERRAMENTA]: {message}")
    elif stage == "ERROR":
        print(f"❌ [ERRO]: {message}")
    elif stage == "RESPONSE":
        print("\n" + "=" * 70)
        print("💬 [RESPOSTA FINAL DO AGENTE]:")
        print(message)
        print("=" * 70 + "\n")

def main() -> None:
    """Ponto de entrada do CLI interativo do MusicMatch."""
    print("=" * 70)
    print("   🎵 MusicMatch - Laboratório de Agentes de IA & Engenharia de Áudio")
    print(f"   Modelo Conectado: {settings.GEMINI_MODEL}")
    print("=" * 70)
    print("Digite sua instrução (ou 'sair' / 'exit' para encerrar):\n")

    try:
        agent = SingleTurnAgent()
    except ValueError as e:
        print(f"❌ Erro de Inicialização: {e}")
        print("💡 Dica: Crie um arquivo .env na raiz com 'GEMINI_API_KEY=sua_chave'.")
        sys.exit(1)

    while True:
        try:
            user_input = input("MusicMatch > ").strip()
            if not user_input:
                continue

            if user_input.lower() in ["sair", "exit", "quit", "q"]:
                print("\nEncerrando sessão do MusicMatch. Até mais!")
                break

            # Executa o turno único do agente com logs em tempo real
            agent.run(user_prompt=user_input, log_callback=format_log)

        except (KeyboardInterrupt, EOFError):
            print("\n\nSessão interrompida pelo usuário. Até mais!")
            break
        except Exception as e:
            print(f"\n❌ Ocorreu um erro durante a execução: {e}\n")

if __name__ == "__main__":
    main()
