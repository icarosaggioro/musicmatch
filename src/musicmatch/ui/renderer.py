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
            print(f"  {cmd.name:<10} : {cmd.description}{aliases_str}")
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


