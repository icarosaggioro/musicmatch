"""Agente Monoturno (Single-Turn Agent) com suporte a Function Calling / Tools."""

from typing import Any, Callable, Dict, List, Optional
from google import genai
from google.genai import types

from musicmatch.config import settings
from musicmatch.tools.scanner import scan_library

SYSTEM_INSTRUCTION = """
Você é o Agente Inteligente do MusicMatch, um assistente especialista em música,
gerenciamento de bibliotecas de áudio local (MP3/FLAC), curadoria acústica e processamento de sinal (DSP).

Diretrizes:
1. Seja prestativo, claro, técnico quando apropriado e conciso.
2. Quando o usuário solicitar indexar, escanear ou carregar músicas de um diretório/pasta, use a ferramenta 'scan_library'.
3. Se a solicitação for uma dúvida conceitual sobre áudio, DSP ou engenharia de som, responda diretamente sem chamar ferramentas desnecessárias.
4. Após o retorno de uma ferramenta, sintetize o resultado de forma amigável para o usuário.
"""

class SingleTurnAgent:
    """Agente de ciclo único (Single-Turn) que recebe uma instrução, despacha ferramentas e sintetiza a resposta."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY não configurada. Defina a variável de ambiente ou crie um arquivo .env na raiz."
            )
        
        self.model_name = model_name or settings.GEMINI_MODEL
        self.client = genai.Client(api_key=self.api_key)
        
        # Mapeamento de ferramentas disponíveis
        self.tools_list: List[Callable[..., Any]] = [scan_library]
        self.tool_map: Dict[str, Callable[..., Any]] = {
            "scan_library": scan_library
        }

    def run(self, user_prompt: str, log_callback: Optional[Callable[[str, str], None]] = None) -> str:
        """Executa o ciclo completo ReAct de um turno:
        1. Envia o prompt do usuário com as ferramentas registradas.
        2. Se o modelo decidir chamar uma ferramenta, executa a função localmente.
        3. Devolve a observação para o modelo sintetizar a resposta final.
        """
        def log(stage: str, message: str) -> None:
            if log_callback:
                log_callback(stage, message)

        log("INPUT", f"Instrução do Usuário: '{user_prompt}'")

        # Configuração da chamada com tools e system instruction
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.2,
            tools=self.tools_list
        )

        # Passo 1: Primeira invocação do modelo
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=user_prompt,
            config=config
        )

        # Verifica se o modelo requisitou chamadas de ferramentas (Function Calling)
        if response.function_calls:
            first_candidate_content = response.candidates[0].content
            function_response_parts: List[types.Part] = []

            for call in response.function_calls:
                func_name = call.name
                func_args = dict(call.args) if call.args else {}
                
                log("TOOL_CALL", f"Ferramenta Solicitada: '{func_name}' com argumentos {func_args}")

                if func_name in self.tool_map:
                    # Executa a função Python correspondente
                    tool_result = self.tool_map[func_name](**func_args)
                    log("OBSERVATION", f"Retorno da Ferramenta ({func_name}): {tool_result}")
                    
                    function_response_parts.append(
                        types.Part.from_function_response(
                            name=func_name,
                            response={"result": tool_result}
                        )
                    )
                else:
                    error_msg = f"Erro: Ferramenta '{func_name}' não encontrada no catálogo."
                    log("ERROR", error_msg)
                    function_response_parts.append(
                        types.Part.from_function_response(
                            name=func_name,
                            response={"error": error_msg}
                        )
                    )

            # Passo 2: Envia a observação de volta para o modelo para a síntese final
            conversation_history = [
                types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)]),
                first_candidate_content,
                types.Content(role="user", parts=function_response_parts)
            ]

            final_response = self.client.models.generate_content(
                model=self.model_name,
                contents=conversation_history,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.3
                )
            )
            
            final_text = final_response.text or ""
            log("RESPONSE", final_text)
            return final_text

        # Se o modelo respondeu diretamente sem chamar ferramentas
        final_text = response.text or ""
        log("RESPONSE", final_text)
        return final_text
