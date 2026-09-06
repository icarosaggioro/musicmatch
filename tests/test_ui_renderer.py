"""Testes unitários para a camada de visualização ConsoleUI usando pytest capsys.

CONCEITO DIDÁTICO:
------------------
A fixture 'capsys' nativa do pytest captura tudo o que é enviado para 'sys.stdout'
e 'sys.stderr'. Isso nos permite testar se a interface gráfica ou textual está
renderizando exatamente o que projetamos (emojis, cabeçalhos, tabelas de ajuda),
sem sujar o terminal do desenvolvedor durante a execução dos testes!
"""

from unittest.mock import MagicMock, patch
from musicmatch.commands.base import Command
from musicmatch.ui.renderer import ConsoleUI

def test_render_banner(capsys):
    ui = ConsoleUI()
    ui.render_banner("gemini-3.6-flash")
    captured = capsys.readouterr().out
    
    assert "🎵 MusicMatch" in captured
    assert "Modelo Conectado: gemini-3.6-flash" in captured
    assert "/help" in captured

def test_render_event_stages(capsys):
    ui = ConsoleUI()

    # INPUT
    ui.render_event("INPUT", "Como medir BPM?")
    captured = capsys.readouterr().out
    assert "[USER PROMPT" in captured
    assert "Como medir BPM?" in captured

    # TOOL_CALL
    ui.render_event("TOOL_CALL", "scan_library")
    captured = capsys.readouterr().out
    assert "[AGENTE - TOOL CALL" in captured
    assert "scan_library" in captured

    # OBSERVATION
    ui.render_event("OBSERVATION", "5 faixas encontradas")
    captured = capsys.readouterr().out
    assert "[TOOL OBSERVATION" in captured
    assert "5 faixas encontradas" in captured

    # ERROR
    ui.render_event("ERROR", "Erro de conexão")
    captured = capsys.readouterr().out
    assert "Erro de conexão" in captured

    # RESPONSE
    ui.render_event("RESPONSE", "Esta é a resposta final.")
    captured = capsys.readouterr().out
    assert "[AGENT RESPONSE" in captured
    assert "Esta é a resposta final." in captured

def test_render_help(capsys):
    ui = ConsoleUI()
    
    cmd1 = MagicMock(spec=Command)
    cmd1.name = "/help"
    cmd1.description = "Exibe ajuda"
    cmd1.aliases = []

    cmd2 = MagicMock(spec=Command)
    cmd2.name = "/exit"
    cmd2.description = "Sai do app"
    cmd2.aliases = ["sair", "quit"]

    ui.render_help([cmd1, cmd2])
    captured = capsys.readouterr().out

    assert "📋 COMANDOS DISPONÍVEIS (Harness Commands):" in captured
    assert "/help" in captured
    assert "/exit" in captured
    assert "aliases: sair, quit" in captured

def test_render_status(capsys):
    ui = ConsoleUI()
    status_data = {
        "Modelo": "gemini-3.6-flash",
        "Total Faixas": "42 faixas"
    }
    ui.render_status(status_data)
    captured = capsys.readouterr().out

    assert "📊 STATUS ATUAL DO SISTEMA:" in captured
    assert "Modelo" in captured
    assert "gemini-3.6-flash" in captured
    assert "42 faixas" in captured

def test_render_helpers(capsys):
    ui = ConsoleUI()

    ui.render_info("Carregando...")
    assert "Carregando..." in capsys.readouterr().out

    ui.render_success("Operação concluída!")
    assert "Operação concluída!" in capsys.readouterr().out

    ui.render_error("Falha ao abrir arquivo.")
    assert "Falha ao abrir arquivo." in capsys.readouterr().out

    ui.render_warning("Aviso de teste.")
    assert "Aviso de teste." in capsys.readouterr().out

    ui.render_goodbye()
    assert "Encerrando sessão do MusicMatch. Até logo!" in capsys.readouterr().out

def test_clear_screen():
    ui = ConsoleUI()
    with patch("os.system") as mock_os_system:
        ui.clear_screen()
        mock_os_system.assert_called_once()

def test_render_track_page(capsys):
    ui = ConsoleUI()
    track1 = MagicMock(title="Bohemian Rhapsody", artist="Queen", file_path="C:/1.mp3")
    track2 = MagicMock(title="Under Pressure", artist="Queen & Bowie", file_path="C:/2.mp3")

    ui.render_track_page([track1, track2], page=1, total_pages=2, total_count=4, start_idx=1)
    captured = capsys.readouterr().out

    assert "BIBLIOTECA DE MÚSICAS [Página 1/2 - Total: 4 faixa(s)]" in captured
    assert "1. Bohemian Rhapsody - Queen" in captured
    assert "Caminho: C:/1.mp3" in captured
    assert "2. Under Pressure - Queen & Bowie" in captured

def test_prompt_pagination(monkeypatch):
    ui = ConsoleUI()

    monkeypatch.setattr("builtins.input", lambda _: "  ")
    assert ui.prompt_pagination() == ""

    monkeypatch.setattr("builtins.input", lambda _: "Q")
    assert ui.prompt_pagination() == "q"

    def mock_interrupt(_):
        raise KeyboardInterrupt()

    monkeypatch.setattr("builtins.input", mock_interrupt)
    assert ui.prompt_pagination() == "q"
