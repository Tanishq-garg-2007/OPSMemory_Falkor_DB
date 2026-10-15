"""Ollama client for local fallback model inference."""
import httpx
from typing import Dict, Any, Optional
from app.config import Settings, get_settings
from app.errors import LLMUnavailableError
from app.llm.base import BaseLLMClient, extract_json_from_text


class OllamaClient(BaseLLMClient):
    """Client for local Ollama HTTP API."""
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.base_url = self.settings.OLLAMA_BASE_URL.rstrip("/")
        self.model_id = self.settings.OLLAMA_MODEL_ID or "gemma2"

    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_id,
            "prompt": prompt,
            "system": system_prompt or "",
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(timeout=float(self.settings.LLM_TIMEOUT_SECONDS)) as client:
                res = await client.post(url, json=payload)
                res.raise_for_status()
                return res.json().get("response", "")
        except Exception as e:
            raise LLMUnavailableError(f"Ollama API request failed: {e}")

    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        text = await self.generate_text(prompt, system_prompt)
        return extract_json_from_text(text)
