"""Unit tests for /model command and agent model configuration (Issue #5)."""

from unittest.mock import MagicMock
import pytest

from musicmatch.agent.core import SingleTurnAgent
from musicmatch.commands.base import CommandContext
from musicmatch.commands.model import ModelCommand
from musicmatch.commands.registry import CommandRegistry
from musicmatch.config import settings


@pytest.fixture
def mock_context():
    """Creates a mock command context for isolated command execution."""
    agent_mock = MagicMock()
    agent_mock.model_name = "gemini-3.6-flash"
    agent_mock.get_model.return_value = "gemini-3.6-flash"
    ctx = CommandContext(
        ui=MagicMock(),
        agent=agent_mock,
        db=MagicMock(),
        registry=MagicMock(),
    )
    return ctx


def test_model_command_properties():
    cmd = ModelCommand()
    assert cmd.name == "/model"
    assert "/llm" in cmd.aliases
    assert "LLM" in cmd.description or "modelo" in cmd.description.lower()
    assert "usage" in cmd.default_error_messages


def test_model_command_show_current_model(mock_context):
    cmd = ModelCommand()
    res = cmd.execute([], mock_context)
    assert res is True
    mock_context.ui.render_info.assert_called()
    # Ensure current model is displayed to user
    rendered_text = " ".join(call.args[0] for call in mock_context.ui.render_info.call_args_list)
    assert "gemini-3.6-flash" in rendered_text


def test_model_command_switch_model(mock_context):
    cmd = ModelCommand()
    res = cmd.execute(["gemini-3.1-pro"], mock_context)
    assert res is True

    # Check agent model was updated
    if hasattr(mock_context.agent, "set_model"):
        mock_context.agent.set_model.assert_called_with("gemini-3.1-pro")
    else:
        assert mock_context.agent.model_name == "gemini-3.1-pro"

    mock_context.ui.render_success.assert_called_once()
    assert "gemini-3.1-pro" in mock_context.ui.render_success.call_args[0][0]


def test_model_command_reset_to_default(mock_context):
    cmd = ModelCommand()
    mock_context.agent.model_name = "gemini-3.1-pro"

    res = cmd.execute(["default"], mock_context)
    assert res is True

    if hasattr(mock_context.agent, "set_model"):
        mock_context.agent.set_model.assert_called_with(settings.GEMINI_MODEL)
    else:
        assert mock_context.agent.model_name == settings.GEMINI_MODEL

    mock_context.ui.render_success.assert_called_once()
    assert settings.GEMINI_MODEL in mock_context.ui.render_success.call_args[0][0]


def test_model_command_registered_in_registry():
    registry = CommandRegistry()
    assert "/model" in registry.lookup_map
    assert "/llm" in registry.lookup_map
    names = [c.name for c in registry.get_all_commands()]
    assert "/model" in names


def test_single_turn_agent_set_and_get_model(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-12345")
    agent = SingleTurnAgent(api_key="test-key-12345", model_name="gemini-3.6-flash")
    assert agent.get_model() == "gemini-3.6-flash"

    agent.set_model("gemini-3.1-pro")
    assert agent.get_model() == "gemini-3.1-pro"
    assert agent.model_name == "gemini-3.1-pro"

    with pytest.raises(ValueError):
        agent.set_model("")

    with pytest.raises(ValueError):
        agent.set_model("   ")
