"""Testes de inicialização e tratamento de erro do Agente."""

import pytest
from musicmatch.agent.core import SingleTurnAgent

def test_agent_initialization_requires_api_key(monkeypatch):
    monkeypatch.setattr("musicmatch.config.settings.GEMINI_API_KEY", "")
    with pytest.raises(ValueError, match="GEMINI_API_KEY não configurada"):
        SingleTurnAgent(api_key="")

def test_agent_tool_registry():
    agent = SingleTurnAgent(api_key="fake_key_for_testing")
    assert "scan_library" in agent.tool_map
    assert callable(agent.tool_map["scan_library"])
    assert "search_tracks" in agent.tool_map
    assert callable(agent.tool_map["search_tracks"])
