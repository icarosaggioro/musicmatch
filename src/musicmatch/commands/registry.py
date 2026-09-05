"""Registro e Despachante de Comandos (Command Registry & Dispatcher).

CONCEITO ARQUITETURAL DIDÁTICO:
--------------------------------
O 'CommandRegistry' funciona como um catálogo centralizado e despachante (Dispatcher).
Ele é o único componente que sabe mapear uma string digitada pelo usuário
para o objeto 'Command' correto que sabe executá-la.

Comportamento importante:
- Comandos do sistema utilizam a convenção '/' (slash commands), ex: /help, /status, /scan.
- Exclusivamente para o encerramento do programa, aceitamos palavras de uso comum
  ('sair', 'exit', 'quit', 'q') como aliases ergonômicos de '/exit'.
"""

import shlex
from typing import Dict, List, Optional
from musicmatch.commands.base import Command, CommandContext
from musicmatch.config import settings
from musicmatch.tools.scanner import scan_library

class HelpCommand(Command):
    """Exibe a documentação de todos os comandos registrados."""

    def __init__(self) -> None:
        super().__init__(
            name="/help",
            description="Exibe esta lista de comandos disponíveis e instruções de uso."
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        commands = ctx.registry.get_all_commands()
        ctx.ui.render_help(commands)
        return True

class StatusCommand(Command):
    """Exibe o status operacional do sistema, modelo conectado e banco de dados."""

    def __init__(self) -> None:
        super().__init__(
            name="/status",
            description="Exibe informações do modelo de IA conectado e tamanho da biblioteca."
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        db_type = type(ctx.db).__name__
        status_info = {
            "Modelo Gemini Ativo": ctx.agent.model_name,
            "Total de Faixas no Banco": f"{ctx.db.count()} faixa(s)",
            "Nível de Log": settings.LOG_LEVEL,
            "Camada de Armazenamento": f"{db_type} ({'FTS5 Ativo' if 'SQLite' in db_type else 'Memória'})",
            "Arquivo de Banco de Dados": getattr(ctx.db, "db_path", "Em Memória"),
            "Ambiente": "Python 3.14 (Clean Architecture + DDD)",
        }
        if hasattr(ctx.db, "get_stats"):
            stats = ctx.db.get_stats()
            if isinstance(stats, dict):
                status_info["Duração Total"] = f"{stats.get('total_duration_hours', 0)} horas"
                status_info["BPM Médio"] = f"{stats.get('avg_bpm', 0)}"
                db_size = stats.get("db_size_kb", 0)
                if isinstance(db_size, (int, float)) and db_size > 0:
                    status_info["Tamanho do Arquivo .db"] = f"{db_size} KB"

        ctx.ui.render_status(status_info)
        return True

class SearchCommand(Command):
    """Executa busca textual instantânea na biblioteca via FTS5 sem acionar a LLM."""

    def __init__(self) -> None:
        super().__init__(
            name="/search",
            description="Busca faixas por texto ou metadados via FTS5: /search <termo>"
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args:
            ctx.ui.render_error("Uso incorreto. Especifique o termo de busca: /search <termo>")
            ctx.ui.render_info("Exemplo: /search Queen  ou  /search Bohemian")
            return True

        query = " ".join(args)
        ctx.ui.render_info(f"Buscando por '{query}' no índice FTS5...")
        
        if hasattr(ctx.db, "search_fulltext"):
            tracks = ctx.db.search_fulltext(query=query, limit=10)
        else:
            tracks = [t for t in ctx.db.get_all_tracks() if query.lower() in t.title.lower() or query.lower() in t.artist.lower()]

        if not tracks:
            ctx.ui.render_info(f"Nenhuma faixa encontrada para '{query}'.")
            return True

        ctx.ui.render_success(f"{len(tracks)} faixa(s) encontrada(s):")
        for i, t in enumerate(tracks, 1):
            print(f"  {i}. {t.artist} - {t.title} [{t.genre}] ({t.bpm:.0f} BPM)")
        return True

class ListCommand(Command):
    """Lista as músicas presentes na biblioteca com paginação e opção de cancelamento."""

    DEFAULT_PAGE_SIZE = 20

    def __init__(self) -> None:
        super().__init__(
            name="/list",
            description="Lista as músicas da biblioteca com paginação (padrão: 20): /list [tamanho_pagina]"
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        page_size = self.DEFAULT_PAGE_SIZE
        if args:
            try:
                parsed_size = int(args[0])
                if parsed_size > 0:
                    page_size = parsed_size
                else:
                    ctx.ui.render_error("O tamanho da página deve ser um número inteiro positivo.")
                    return True
            except ValueError:
                ctx.ui.render_error("O tamanho da página deve ser um número inteiro positivo.")
                return True

        total_tracks = ctx.db.count()
        if total_tracks == 0:
            ctx.ui.render_info("A biblioteca está vazia. Use '/scan <caminho>' para adicionar músicas.")
            return True

        total_pages = (total_tracks + page_size - 1) // page_size

        for page in range(1, total_pages + 1):
            offset = (page - 1) * page_size
            try:
                tracks = ctx.db.get_all_tracks(limit=page_size, offset=offset)
            except TypeError:
                all_tracks = ctx.db.get_all_tracks()
                tracks = all_tracks[offset : offset + page_size]

            start_idx = offset + 1
            ctx.ui.render_track_page(tracks, page, total_pages, total_tracks, start_idx=start_idx)

            if page < total_pages:
                action = ctx.ui.prompt_pagination()
                if action in ("q", "quit", "c", "cancel", "sair", "cancelar"):
                    ctx.ui.render_info("Listagem cancelada pelo usuário.")
                    return True

        ctx.ui.render_info("Fim da listagem.")
        return True

class ScanCommand(Command):
    """Executa a ferramenta de escaneamento diretamente pelo terminal sem acionar a LLM."""

    def __init__(self) -> None:
        super().__init__(
            name="/scan",
            description="Varre um diretório de áudio diretamente: /scan <caminho_da_pasta>"
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args:
            ctx.ui.render_error("Uso incorreto. Especifique o caminho da pasta: /scan <caminho>")
            ctx.ui.render_info("Exemplo: /scan C:/Musicas")
            return True

        path = args[0]
        ctx.ui.render_info(f"Iniciando varredura determinística direta em '{path}'...")
        result = scan_library(path=path)
        
        ctx.ui.render_success(
            f"Varredura concluída: {result['tracks_indexed']} faixas indexadas em {result['duration_ms']}ms."
        )
        ctx.ui.render_info(f"Total na biblioteca agora: {ctx.db.count()} faixa(s).")
        return True

class ClearCommand(Command):
    """Limpa a tela do console."""

    def __init__(self) -> None:
        super().__init__(
            name="/clear",
            description="Limpa a tela do terminal."
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        ctx.ui.clear_screen()
        ctx.ui.render_banner(ctx.agent.model_name)
        return True

class ExitCommand(Command):
    """Encerra a sessão interativa do MusicMatch."""

    def __init__(self) -> None:
        super().__init__(
            name="/exit",
            description="Encerra a aplicação MusicMatch.",
            # Conforme alinhado: apenas o comando de saída aceita palavras comuns sem barra
            aliases=["sair", "exit", "quit", "q"]
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        ctx.ui.render_goodbye()
        return False

class CommandRegistry:
    """Catálogo central onde comandos são registrados, consultados e despachados."""

    def __init__(self) -> None:
        self._commands: Dict[str, Command] = {}
        self._alias_map: Dict[str, Command] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Registra os comandos padrão do sistema."""
        defaults = [
            HelpCommand(),
            StatusCommand(),
            ListCommand(),
            ScanCommand(),
            SearchCommand(),
            ClearCommand(),
            ExitCommand(),
        ]
        for cmd in defaults:
            self.register(cmd)

    def register(self, command: Command) -> None:
        """Registra um novo comando no catálogo."""
        self._commands[command.name.lower()] = command
        for alias in command.aliases:
            self._alias_map[alias.lower()] = command

    def get_all_commands(self) -> List[Command]:
        """Retorna a lista de todos os comandos registrados (sem duplicar aliases)."""
        return list(self._commands.values())

    def is_command(self, raw_input: str) -> bool:
        """Verifica se a entrada do usuário deve ser tratada como um comando do sistema.
        
        Critério:
        - Inicia com '/' (qualquer slash command)
        - Ou é um alias do comando de saída ('sair', 'exit', 'quit', 'q')
        """
        cleaned = raw_input.strip()
        if not cleaned:
            return False
        
        if cleaned.startswith("/"):
            return True
            
        first_token = cleaned.split()[0].lower()
        return first_token in self._alias_map

    def dispatch(self, raw_input: str, ctx: CommandContext) -> bool:
        """Processa e executa um comando a partir da linha digitada pelo usuário.

        Returns:
            bool: True para manter o loop rodando; False para encerrar o REPL.
        """
        try:
            tokens = shlex.split(raw_input)
        except ValueError:
            tokens = raw_input.split()

        if not tokens:
            return True

        trigger = tokens[0].lower()
        args = tokens[1:]

        # Localiza o comando pelo nome primário (/comando) ou por alias cadastrado
        command = self._commands.get(trigger) or self._alias_map.get(trigger)

        if not command:
            ctx.ui.render_error(f"Comando '{trigger}' não reconhecido.")
            ctx.ui.render_info("Digite '/help' para visualizar a lista de comandos disponíveis.")
            return True

        return command.execute(args, ctx)
