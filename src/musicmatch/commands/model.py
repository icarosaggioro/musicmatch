"""Model Management Command (/model).

Allows inspecting and dynamically switching the active Gemini LLM model used by the AI agent.
"""

from typing import List

from musicmatch.commands.base import Command, CommandContext
from musicmatch.config import settings

# Curated catalog of verified Gemini models for quick user discovery
RECOMMENDED_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.1-pro",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]


class ModelCommand(Command):
    """Exibe ou altera o modelo de inteligência artificial (LLM) conectado ao agente."""

    def __init__(self) -> None:
        super().__init__()
        self._name = "/model"
        self._description = "Exibe ou altera o modelo de IA (LLM) ativo: /model [nome_do_modelo]"
        self._aliases = ["/llm"]
        self._default_error_messages = {
            "usage": "Uso: /model [nome_do_modelo]. Exemplo: /model gemini-3.1-pro",
            "invalid_args": "Nome de modelo inválido. Especifique um modelo ou use /model para ver as opções.",
        }

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        current_model = (
            ctx.agent.get_model()
            if hasattr(ctx.agent, "get_model")
            else getattr(ctx.agent, "model_name", settings.GEMINI_MODEL)
        )

        if not args:
            # Display current model and suggestions
            ctx.ui.render_info(f"Modelo LLM atualmente ativo: '{current_model}'")
            ctx.ui.render_info(f"Modelos recomendados: {', '.join(RECOMMENDED_MODELS)}")
            ctx.ui.render_info("Para trocar de modelo: /model <nome_do_modelo>")
            ctx.ui.render_info(f"Para restaurar o padrão ({settings.GEMINI_MODEL}): /model default")
            return True

        target_model = args[0].strip()
        if not target_model:
            ctx.ui.render_error("Nome de modelo inválido. Especifique um modelo válido.")
            return True

        if target_model.lower() in ("default", "--default", "reset", "--reset"):
            target_model = settings.GEMINI_MODEL

        old_model = current_model
        try:
            if hasattr(ctx.agent, "set_model"):
                ctx.agent.set_model(target_model)
            else:
                ctx.agent.model_name = target_model
            ctx.ui.render_success(
                f"Modelo LLM alterado com sucesso para '{target_model}' (anterior: '{old_model}')."
            )
        except Exception as e:
            ctx.ui.render_error(f"Erro ao alterar modelo LLM: {e}")

        return True
