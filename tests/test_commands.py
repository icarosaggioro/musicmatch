"""Testes unitários para o CommandRegistry e comandos do Harness."""

import pytest
from unittest.mock import MagicMock
from musicmatch.commands.base import CommandContext
from musicmatch.commands.registry import CommandRegistry

@pytest.fixture
def mock_context():
    """Cria um contexto simulado para execução isolada de comandos."""
    ctx = CommandContext(
        ui=MagicMock(),
        agent=MagicMock(),
        db=MagicMock(),
        registry=None
    )
    ctx.agent.model_name = "gemini-3.6-flash"
    ctx.db.count.return_value = 10
    return ctx

def test_command_registry_defaults():
    registry = CommandRegistry()
    commands = registry.get_all_commands()
    names = [c.name for c in commands]
    
    assert "/help" in names
    assert "/status" in names
    assert "/scan" in names
    assert "/clear" in names
    assert "/exit" in names

def test_is_command_detection():
    registry = CommandRegistry()
    
    # Slash commands
    assert registry.is_command("/help") is True
    assert registry.is_command("/status") is True
    assert registry.is_command("/scan C:/Audio") is True
    assert registry.is_command("/custom") is True
    
    # Aliases permitidos exclusivamente para saída
    assert registry.is_command("sair") is True
    assert registry.is_command("exit") is True
    assert registry.is_command("quit") is True
    assert registry.is_command("q") is True
    
    # Linguagem natural livre (NÃO devem ser comandos)
    assert registry.is_command("Qual o melhor formato de áudio?") is False
    assert registry.is_command("escanear pasta de musicas") is False
    assert registry.is_command("ajuda") is False
    assert registry.is_command("") is False

def test_dispatch_help(mock_context):
    registry = CommandRegistry()
    mock_context.registry = registry
    
    should_continue = registry.dispatch("/help", mock_context)
    assert should_continue is True
    mock_context.ui.render_help.assert_called_once()

def test_dispatch_status(mock_context):
    registry = CommandRegistry()
    mock_context.registry = registry
    
    should_continue = registry.dispatch("/status", mock_context)
    assert should_continue is True
    mock_context.ui.render_status.assert_called_once()
    status_dict = mock_context.ui.render_status.call_args[0][0]
    assert status_dict["Modelo Gemini Ativo"] == "gemini-3.6-flash"
    assert "10 faixa(s)" in status_dict["Total de Faixas no Banco"]

def test_dispatch_scan_with_argument(mock_context, monkeypatch):
    registry = CommandRegistry()
    mock_context.registry = registry
    
    # Mock do scanner para evitar tocar no disco ou banco de dados
    mock_scan = MagicMock(return_value={
        "tracks_indexed": 5,
        "duration_ms": 12.5
    })
    monkeypatch.setattr("musicmatch.commands.registry.scan_library", mock_scan)
    
    should_continue = registry.dispatch("/scan C:/Audio/Albuns", mock_context)
    assert should_continue is True
    mock_scan.assert_called_once_with(path="C:/Audio/Albuns")
    mock_context.ui.render_success.assert_called_once()

def test_dispatch_scan_missing_argument(mock_context):
    registry = CommandRegistry()
    mock_context.registry = registry
    
    should_continue = registry.dispatch("/scan", mock_context)
    assert should_continue is True
    mock_context.ui.render_error.assert_called_once_with(
        "Uso incorreto. Especifique o caminho da pasta: /scan <caminho>"
    )

def test_dispatch_exit(mock_context):
    registry = CommandRegistry()
    mock_context.registry = registry
    
    # /exit deve solicitar parada (retornando False)
    assert registry.dispatch("/exit", mock_context) is False
    assert registry.dispatch("sair", mock_context) is False
    mock_context.ui.render_goodbye.assert_called()

def test_dispatch_unknown_command(mock_context):
    registry = CommandRegistry()
    mock_context.registry = registry
    
    should_continue = registry.dispatch("/comando_inexistente", mock_context)
    assert should_continue is True
    mock_context.ui.render_error.assert_called_once()

def test_dispatch_clear(mock_context):
    registry = CommandRegistry()
    mock_context.registry = registry
    should_continue = registry.dispatch("/clear", mock_context)
    assert should_continue is True
    mock_context.ui.clear_screen.assert_called_once()
    mock_context.ui.render_banner.assert_called_once_with(mock_context.agent.model_name)

def test_dispatch_unclosed_quotes_fallback(mock_context):
    registry = CommandRegistry()
    mock_context.registry = registry
    # String com aspas não fechadas dispara ValueError no shlex, caindo no split normal
    should_continue = registry.dispatch('/scan "C:/Musica_Sem_Fechar_Aspas', mock_context)
    assert should_continue is True

def test_dispatch_empty_input(mock_context):
    registry = CommandRegistry()
    mock_context.registry = registry
    assert registry.dispatch("", mock_context) is True
