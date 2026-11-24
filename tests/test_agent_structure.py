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


def test_agent_request_with_tools_can_be_built():
    """Regression: the SDK could not describe the tools' injected 'service' parameter, so every
    prompt failed before leaving the machine. Only the HTTP layer is replaced here: mocking
    generate_content, as the other tests do, hides this kind of error."""
    agent = SingleTurnAgent(api_key="fake_test_key", model_name="gemini-3.6-flash")
    sent = {}

    class _Sent(Exception):
        pass

    def fake_request(method, path, body, *args, **kwargs):
        sent.update(body)
        raise _Sent

    agent.client._api_client.request = fake_request
    with pytest.raises(_Sent):
        agent.run("oi")

    declared = {d["name"]: d for tool in sent["tools"] for d in tool["functionDeclarations"]}
    assert set(declared) == set(agent.tool_map)
    for name, declaration in declared.items():
        assert declaration["description"]
        text = str(declaration)
        assert "'service'" not in text and "'player'" not in text and "LibraryService" not in declaration["description"], name
