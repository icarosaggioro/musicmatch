"""Testes unitários para o Harness e o Loop de Eventos."""

import pytest
from unittest.mock import MagicMock, patch
from musicmatch.harness.loop import Harness

def test_harness_routes_command_to_registry():
    mock_agent = MagicMock()
    mock_agent.model_name = "gemini-3.6-flash"
    mock_ui = MagicMock()
    mock_registry = MagicMock()
    mock_registry.is_command.return_value = True
    # O comando retorna False para encerrar o loop após a primeira iteração
    mock_registry.dispatch.return_value = False

    harness = Harness(agent=mock_agent, ui=mock_ui, registry=mock_registry, database=MagicMock())

    with patch("builtins.input", return_value="/help"):
        harness.start()

    mock_ui.render_banner.assert_called_once_with("gemini-3.6-flash")
    mock_registry.is_command.assert_called_once_with("/help")
    mock_registry.dispatch.assert_called_once_with("/help", harness.ctx)
    # Garante que o agente de IA NÃO foi chamado para um comando de sistema
    mock_agent.run.assert_not_called()

def test_harness_routes_natural_language_to_agent():
    mock_agent = MagicMock()
    mock_agent.model_name = "gemini-3.6-flash"
    mock_ui = MagicMock()
    mock_registry = MagicMock()
    
    # Simula primeira entrada como pergunta de IA e a segunda como comando de saída
    mock_registry.is_command.side_effect = [False, True]
    mock_registry.dispatch.return_value = False

    harness = Harness(agent=mock_agent, ui=mock_ui, registry=mock_registry, database=MagicMock())

    inputs = ["O que é LUFS?", "/exit"]
    with patch("builtins.input", side_effect=inputs):
        harness.start()

    # O agente de IA deve ser chamado com a pergunta do usuário e o callback da UI
    mock_agent.run.assert_called_once_with(
        user_prompt="O que é LUFS?",
        log_callback=mock_ui.render_event
    )

def test_harness_handles_keyboard_interrupt_gracefully():
    mock_agent = MagicMock()
    mock_agent.model_name = "gemini-3.6-flash"
    mock_ui = MagicMock()
    mock_registry = MagicMock()

    harness = Harness(agent=mock_agent, ui=mock_ui, registry=mock_registry, database=MagicMock())

    with patch("builtins.input", side_effect=KeyboardInterrupt):
        harness.start()

    mock_ui.render_goodbye.assert_called_once()

def test_harness_error_boundary_recovers_from_exception(caplog):
    mock_agent = MagicMock()
    mock_agent.model_name = "gemini-3.6-flash"
    mock_ui = MagicMock()
    mock_registry = MagicMock()

    # Simula uma exceção na primeira chamada e depois encerra o loop
    mock_registry.is_command.side_effect = [False, True]
    mock_agent.run.side_effect = RuntimeError("Falha de conexão com a API")
    mock_registry.dispatch.return_value = False

    harness = Harness(agent=mock_agent, ui=mock_ui, registry=mock_registry, database=MagicMock())

    inputs = ["Pergunta que falha", "/exit"]
    with patch("builtins.input", side_effect=inputs):
        harness.start()

    # Capturado pela fronteira (ADR 0019): uma linha na tela com a referência, traceback no log, REPL vivo
    mock_ui.render_unexpected_error.assert_called_once()
    command, ref = mock_ui.render_unexpected_error.call_args.args[:2]
    assert command == "Pergunta"
    assert "RuntimeError: Falha de conexão com a API" in mock_ui.render_unexpected_error.call_args.kwargs["reason"]
    record = next(r for r in caplog.records if f"[ref {ref}]" in r.getMessage())
    assert record.exc_info[0] is RuntimeError and "Pergunta que falha" in record.getMessage()
    assert harness.exit_code == 0 and mock_registry.dispatch.called  # the session went on to /exit

def test_harness_ignores_empty_inputs():
    """Garante que apertar Enter em branco não quebra o loop nem chama o agente."""
    mock_agent = MagicMock()
    mock_agent.model_name = "gemini-3.6-flash"
    mock_ui = MagicMock()
    mock_registry = MagicMock()
    mock_registry.is_command.return_value = True
    mock_registry.dispatch.return_value = False

    harness = Harness(agent=mock_agent, ui=mock_ui, registry=mock_registry, database=MagicMock())

    # Duas entradas vazias seguidas do comando de saída
    inputs = ["", "   ", "/exit"]
    with patch("builtins.input", side_effect=inputs):
        harness.start()

    mock_agent.run.assert_not_called()
    mock_registry.dispatch.assert_called_once_with("/exit", harness.ctx)

def test_harness_initialization_error_when_no_agent():
    """Testa a captura de erro quando a instanciação do SingleTurnAgent padrão falha."""
    mock_ui = MagicMock()
    with patch("musicmatch.harness.loop.SingleTurnAgent", side_effect=ValueError("Chave ausente")):
        with pytest.raises(ValueError, match="Chave ausente"):
            Harness(agent=None, ui=mock_ui, database=MagicMock())
        mock_ui.render_error.assert_called_once()
        mock_ui.render_info.assert_called_once()
