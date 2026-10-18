"""LLM Gateway initialization and factory."""
from typing import Optional
from app.config import Settings, get_settings
from app.llm.base import BaseLLMClient
from app.llm.mock import MockLLMClient
from app.llm.groq import GroqClient
from app.llm.google_genai import GoogleGenAIClient
from app.llm.ollama import OllamaClient
from app.core.logging import get_logger

logger = get_logger("llm_factory")

_client_instance: Optional[BaseLLMClient] = None


def get_llm_client(settings: Optional[Settings] = None) -> BaseLLMClient:
    """Obtain configured LLM client obeying REAL_LLM constraint and provider fallbacks."""
    global _client_instance
    if _client_instance is not None:
        return _client_instance

    s = settings or get_settings()

    if s.REAL_LLM == 1:
        if s.LLM_PROVIDER == "groq" and s.effective_groq_api_key:
            logger.info(f"Using Groq provider with primary model {s.GROQ_PRIMARY_MODEL or s.LLM_MODEL_ID}")
            _client_instance = GroqClient(s)
            return _client_instance
        elif s.LLM_PROVIDER == "google_genai" and s.effective_google_api_key:
            logger.info(f"Using Google GenAI provider with model {s.LLM_MODEL_ID}")
            _client_instance = GoogleGenAIClient(s)
            return _client_instance
        elif s.effective_groq_api_key:
            logger.info(f"Defaulting to Groq provider with model {s.GROQ_PRIMARY_MODEL or s.LLM_MODEL_ID}")
            _client_instance = GroqClient(s)
            return _client_instance
        elif s.LLM_PROVIDER == "ollama":
            logger.info(f"Using Ollama provider at {s.OLLAMA_BASE_URL}")
            _client_instance = OllamaClient(s)
            return _client_instance
        else:
            logger.warning("REAL_LLM=1 specified but missing credentials or unsupported provider. Falling back to Mock.")

    if s.REAL_LLM != 1:
        logger.warning("REAL_LLM!=1: using the Mock LLM. Set REAL_LLM=1 plus a provider key for real answers.")
    # Default to deterministic Mock client
    _client_instance = MockLLMClient()
    return _client_instance


def reset_llm_client() -> None:
    """Reset cached LLM client for tests."""
    global _client_instance
    _client_instance = None
