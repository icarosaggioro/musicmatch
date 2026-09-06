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
    assert "/list" in names
    assert "/scan" in names
    assert "/search" in names
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
    mock_context.db.get_stats.return_value = {
        "total_duration_hours": 2.5,
        "avg_bpm": 128.0,
        "db_size_kb": 64.0,
    }
    
    should_continue = registry.dispatch("/status", mock_context)
    assert should_continue is True
    mock_context.ui.render_status.assert_called_once()
    status_dict = mock_context.ui.render_status.call_args[0][0]
    assert status_dict["Modelo Gemini Ativo"] == "gemini-3.6-flash"
    assert "10 faixa(s)" in status_dict["Total de Faixas no Banco"]
    assert "2.5 horas" in status_dict["Duração Total"]
    assert "128.0" in status_dict["BPM Médio"]
    assert "64.0 KB" in status_dict["Tamanho do Arquivo .db"]

def test_dispatch_scan_with_argument(mock_context, monkeypatch):
    registry = CommandRegistry()
    mock_context.registry = registry
    
    # Mock do scanner para evitar tocar no disco ou banco de dados
    mock_scan = MagicMock(return_value={
        "status": "success",
        "total_files_scanned": 10,
        "tracks_indexed": 5,
        "tracks_added": 3,
        "tracks_updated": 2,
        "tracks_unchanged": 5,
        "tracks_missing": 1,
        "errors_count": 1,
        "duration_ms": 12.5
    })
    monkeypatch.setattr("musicmatch.commands.registry.scan_library", mock_scan)
    
    should_continue = registry.dispatch("/scan C:/Audio/Albuns do Rock", mock_context)
    assert should_continue is True
    mock_scan.assert_called_once_with(path="C:/Audio/Albuns do Rock")
    mock_context.ui.render_success.assert_called_once()
    assert mock_context.ui.render_warning.call_count == 2

def test_dispatch_scan_with_error(mock_context, monkeypatch):
    registry = CommandRegistry()
    mock_context.registry = registry
    
    mock_scan = MagicMock(return_value={
        "status": "error",
        "message": "Diretório não encontrado."
    })
    monkeypatch.setattr("musicmatch.commands.registry.scan_library", mock_scan)
    
    should_continue = registry.dispatch("/scan C:/PathInvalido", mock_context)
    assert should_continue is True
    mock_context.ui.render_error.assert_called_once_with("Diretório não encontrado.")

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

def test_dispatch_search_missing_argument(mock_context):
    registry = CommandRegistry()
    mock_context.registry = registry
    should_continue = registry.dispatch("/search", mock_context)
    assert should_continue is True
    mock_context.ui.render_error.assert_called_once_with(
        "Uso incorreto. Especifique o termo de busca: /search <termo>"
    )

def test_dispatch_search_with_results(mock_context):
    registry = CommandRegistry()
    mock_context.registry = registry
    mock_track = MagicMock()
    mock_track.artist = "Queen"
    mock_track.title = "Bohemian Rhapsody"
    mock_track.genre = "Rock"
    mock_track.bpm = 72.0
    mock_context.db.search_fulltext.return_value = [mock_track]

    should_continue = registry.dispatch("/search Queen", mock_context)
    assert should_continue is True
    mock_context.ui.render_success.assert_called_once()

def test_dispatch_search_no_results(mock_context):
    registry = CommandRegistry()
    mock_context.registry = registry
    mock_context.db.search_fulltext.return_value = []

    should_continue = registry.dispatch("/search Desconhecido", mock_context)
    assert should_continue is True
    mock_context.ui.render_info.assert_called()

def test_dispatch_list_empty_library(mock_context):
    registry = CommandRegistry()
    mock_context.registry = registry
    mock_context.db.count.return_value = 0

    should_continue = registry.dispatch("/list", mock_context)
    assert should_continue is True
    mock_context.ui.render_info.assert_called_with(
        "A biblioteca está vazia. Use '/scan <caminho>' para adicionar músicas."
    )

def test_dispatch_list_invalid_page_size(mock_context):
    registry = CommandRegistry()
    mock_context.registry = registry

    should_continue = registry.dispatch("/list abc", mock_context)
    assert should_continue is True
    mock_context.ui.render_error.assert_called_with(
        "O tamanho da página deve ser um número inteiro positivo."
    )

    should_continue_zero = registry.dispatch("/list 0", mock_context)
    assert should_continue_zero is True

def test_dispatch_list_single_page(mock_context):
    registry = CommandRegistry()
    mock_context.registry = registry
    mock_context.db.count.return_value = 2
    mock_tracks = [MagicMock(title="T1", file_path="C:/1.mp3"), MagicMock(title="T2", file_path="C:/2.mp3")]
    mock_context.db.get_all_tracks.return_value = mock_tracks

    should_continue = registry.dispatch("/list", mock_context)
    assert should_continue is True
    mock_context.ui.render_track_page.assert_called_once_with(mock_tracks, 1, 1, 2, start_idx=1)
    mock_context.ui.render_info.assert_called_with("Fim da listagem.")

def test_dispatch_list_multiple_pages_with_continue(mock_context):
    registry = CommandRegistry()
    mock_context.registry = registry
    mock_context.db.count.return_value = 3
    t1 = MagicMock(title="T1", file_path="C:/1.mp3")
    t2 = MagicMock(title="T2", file_path="C:/2.mp3")
    t3 = MagicMock(title="T3", file_path="C:/3.mp3")

    mock_context.db.get_all_tracks.side_effect = [
        [t1, t2],
        [t3]
    ]
    mock_context.ui.prompt_pagination.return_value = ""  # Usuário aperta Enter

    should_continue = registry.dispatch("/list 2", mock_context)
    assert should_continue is True
    assert mock_context.ui.render_track_page.call_count == 2
    mock_context.ui.prompt_pagination.assert_called_once()
    mock_context.ui.render_info.assert_called_with("Fim da listagem.")

def test_dispatch_list_multiple_pages_with_cancel(mock_context):
    registry = CommandRegistry()
    mock_context.registry = registry
    mock_context.db.count.return_value = 4
    t1 = MagicMock(title="T1", file_path="C:/1.mp3")
    t2 = MagicMock(title="T2", file_path="C:/2.mp3")
    mock_context.db.get_all_tracks.return_value = [t1, t2]
    mock_context.ui.prompt_pagination.return_value = "q"  # Usuário cancela

    should_continue = registry.dispatch("/list 2", mock_context)
    assert should_continue is True
    assert mock_context.ui.render_track_page.call_count == 1
    mock_context.ui.render_info.assert_called_with("Listagem cancelada pelo usuário.")

def test_dispatch_list_with_type_error_fallback(mock_context):
    registry = CommandRegistry()
    mock_context.registry = registry
    mock_context.db.count.return_value = 2
    t1 = MagicMock(title="T1", file_path="C:/1.mp3")
    t2 = MagicMock(title="T2", file_path="C:/2.mp3")

    # Simula repositório sem suporte aos argumentos limit/offset
    def mock_get_all_tracks(**kwargs):
        if kwargs:
            raise TypeError("unexpected keyword argument")
        return [t1, t2]

    mock_context.db.get_all_tracks.side_effect = mock_get_all_tracks
    should_continue = registry.dispatch("/list", mock_context)
    assert should_continue is True
    mock_context.ui.render_track_page.assert_called_once()
