"""Factory dei modelli LLM (OpenRouter / OpenAI-compatibile)."""
from agno.models.openai import OpenAIChat

from .config import Settings


def make_model(s: Settings, strong: bool = False) -> OpenAIChat:
    return OpenAIChat(
        id=s.strong_model_id if strong else s.llm_model_id,
        api_key=s.api_key,
        base_url=s.openrouter_base_url or None,
    )
