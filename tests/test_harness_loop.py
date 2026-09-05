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

    harness = Harness(agent=mock_agent, ui=mock_ui, registry=mock_registry)

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

    harness = Harness(agent=mock_agent, ui=mock_ui, registry=mock_registry)

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

    harness = Harness(agent=mock_agent, ui=mock_ui, registry=mock_registry)

    with patch("builtins.input", side_effect=KeyboardInterrupt):
        harness.start()

    mock_ui.render_goodbye.assert_called_once()

def test_harness_error_boundary_recovers_from_exception():
    mock_agent = MagicMock()
    mock_agent.model_name = "gemini-3.6-flash"
    mock_ui = MagicMock()
    mock_registry = MagicMock()

    # Simula uma exceção na primeira chamada e depois encerra o loop
    mock_registry.is_command.side_effect = [False, True]
    mock_agent.run.side_effect = RuntimeError("Falha de conexão com a API")
    mock_registry.dispatch.return_value = False

    harness = Harness(agent=mock_agent, ui=mock_ui, registry=mock_registry)

    inputs = ["Pergunta que falha", "/exit"]
    with patch("builtins.input", side_effect=inputs):
        harness.start()

    # Verifica que o erro foi capturado pela fronteira e exibido sem quebrar o REPL
    mock_ui.render_error.assert_called_once()
    assert "Falha de conexão com a API" in mock_ui.render_error.call_args[0][0]
