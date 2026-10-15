"""Ollama client for local fallback model inference."""
import httpx
from typing import Dict, Any, Optional
from app.config import Settings, get_settings
from app.errors import LLMUnavailableError
from app.llm.base import BaseLLMClient, extract_json_from_text
from app.core.logging import get_logger

logger = get_logger("ollama")


class OllamaClient(BaseLLMClient):
    """Client for local Ollama HTTP API."""
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.base_url = self.settings.OLLAMA_BASE_URL.rstrip("/")
        self.model_id = self.settings.OLLAMA_MODEL_ID or "gemma4-e2b:latest"

    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None, json_format: bool = False) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_id,
            "prompt": prompt,
            "system": system_prompt or "",
            "stream": False,
        }
        if json_format:
            payload["format"] = "json"
        timeout = float(max(self.settings.LLM_TIMEOUT_SECONDS, 45.0))
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.post(url, json=payload)
                res.raise_for_status()
                return res.json().get("response", "")
        except Exception as e:
            if self.settings.LLM_FALLBACK_PROVIDER == "mock":
                logger.warning(f"Ollama request failed ({e}). Falling back to MockLLMClient.")
                from app.llm.mock import MockLLMClient
                return await MockLLMClient().generate_text(prompt, system_prompt)
            raise LLMUnavailableError(f"Ollama API request failed: {e}")

    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        try:
            text = await self.generate_text(prompt, system_prompt, json_format=True)
            return extract_json_from_text(text)
        except Exception as e:
            if self.settings.LLM_FALLBACK_PROVIDER == "mock":
                logger.warning(f"Ollama JSON generation failed ({e}). Falling back to MockLLMClient.")
                from app.llm.mock import MockLLMClient
                return await MockLLMClient().generate_json(prompt, system_prompt)
            raise LLMUnavailableError(f"Ollama JSON extraction failed: {e}")

