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

import os
import sys
from typing import Any, Dict, List

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
        for cmd in commands:
            aliases_str = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
            print(f"  {cmd.name:<8} : {cmd.description}{aliases_str}")
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
            print(f"  {i:>3}. {t.title}{artist_str}")
            print(f"       Caminho: {t.file_path}")
        print("-" * 72)

    def prompt_pagination(self) -> str:
        """Solicita ação do usuário para controle da paginação."""
        try:
            return input("⏩ Pressione [Enter] para a próxima página ou ['q'/'c'] para cancelar: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return "q"

    def render_goodbye(self) -> None:
        """Exibe a mensagem de encerramento da sessão."""
        print("\nEncerrando sessão do MusicMatch. Até logo!\n")

    def clear_screen(self) -> None:
        """Limpa o console de maneira compatível com Windows e Unix."""
        os.system("cls" if os.name == "nt" else "clear")
