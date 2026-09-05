"""Testes unitários para o ciclo de execução ReAct do SingleTurnAgent com Mocks.

CONCEITO DIDÁTICO:
------------------
Por que testamos o Agente com Mocks em vez de chamar a API real do Gemini?
1. Determinismo e Velocidade: Testes unitários devem rodar em milissegundos,
   sem depender de conexão com a internet ou latência de rede.
2. Custo Zero: Não consumimos créditos ou tokens da API durante o desenvolvimento contínuo (CI/CD).
3. Teste de Casos Extremos (Edge Cases): Podemos forçar o modelo simulado a responder
   com ferramentas desconhecidas ou respostas vazias para garantir que nosso código seja resiliente.
"""

import pytest
from unittest.mock import MagicMock
from google.genai import types
from musicmatch.agent.core import SingleTurnAgent

@pytest.fixture
def agent():
    """Instancia um SingleTurnAgent com chave simulada."""
    return SingleTurnAgent(api_key="fake_test_key", model_name="gemini-3.6-flash")

def test_agent_run_direct_text_response(agent):
    """Testa o caso em que a LLM responde diretamente sem chamar ferramentas."""
    mock_response = MagicMock()
    mock_response.function_calls = None
    mock_response.text = "LUFS é a unidade padrão para medir Loudness percebido segundo a EBU R128."
    
    agent.client.models.generate_content = MagicMock(return_value=mock_response)
    
    logs = []
    def record_log(stage, message):
        logs.append((stage, message))

    result = agent.run("O que é LUFS?", log_callback=record_log)

    assert result == "LUFS é a unidade padrão para medir Loudness percebido segundo a EBU R128."
    assert agent.client.models.generate_content.call_count == 1
    
    # Verifica observabilidade dos estágios
    stages = [stage for stage, _ in logs]
    assert "INPUT" in stages
    assert "RESPONSE" in stages
    assert "TOOL_CALL" not in stages

def test_agent_run_with_function_calling_cycle(agent):
    """Testa o ciclo ReAct completo de 2 turnos:
    1º Turno: LLM decide chamar 'scan_library'.
    Agente: Executa a ferramenta e devolve a observação.
    2º Turno: LLM sintetiza a resposta final com base na observação.
    """
    # 1º Turno da LLM
    mock_call = MagicMock()
    mock_call.name = "scan_library"
    mock_call.args = {"path": "C:/Musicas", "recursive": True}

    turn1_resp = MagicMock()
    turn1_resp.function_calls = [mock_call]
    candidate_content = MagicMock()
    turn1_resp.candidates = [MagicMock(content=candidate_content)]

    # 2º Turno da LLM (Síntese)
    turn2_resp = MagicMock()
    turn2_resp.function_calls = None
    turn2_resp.text = "Escaneei com sucesso 5 faixas no diretório C:/Musicas."

    agent.client.models.generate_content = MagicMock(side_effect=[turn1_resp, turn2_resp])

    logs = []
    def record_log(stage, message):
        logs.append((stage, message))

    result = agent.run("Escaneie a pasta C:/Musicas", log_callback=record_log)

    assert result == "Escaneei com sucesso 5 faixas no diretório C:/Musicas."
    assert agent.client.models.generate_content.call_count == 2
    
    stages = [stage for stage, _ in logs]
    assert stages == ["INPUT", "TOOL_CALL", "OBSERVATION", "RESPONSE"]
    
    # Valida que o segundo turno recebeu o histórico com a observação
    second_call_kwargs = agent.client.models.generate_content.call_args_list[1][1]
    history = second_call_kwargs["contents"]
    assert len(history) == 3
    assert history[0].role == "user"

def test_agent_run_unknown_tool_handling(agent):
    """Testa como o agente lida quando o modelo solicita uma ferramenta não existente."""
    mock_call = MagicMock()
    mock_call.name = "ferramenta_inexistente"
    mock_call.args = {}

    turn1_resp = MagicMock()
    turn1_resp.function_calls = [mock_call]
    turn1_resp.candidates = [MagicMock(content=MagicMock())]

    turn2_resp = MagicMock(text="Desculpe, não consegui executar essa ferramenta.")
    agent.client.models.generate_content = MagicMock(side_effect=[turn1_resp, turn2_resp])

    logs = []
    def record_log(stage, message):
        logs.append((stage, message))

    result = agent.run("Faça algo desconhecido", log_callback=record_log)

    assert result == "Desculpe, não consegui executar essa ferramenta."
    stages = [stage for stage, _ in logs]
    assert "ERROR" in stages
    assert any("ferramenta_inexistente" in msg for stage, msg in logs if stage == "ERROR")
