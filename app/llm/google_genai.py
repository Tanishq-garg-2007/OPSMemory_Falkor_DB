"""Google GenAI integration targeting Gemma 4 31B."""
import asyncio
from typing import Dict, Any, Optional
from app.config import Settings, get_settings
from app.errors import LLMUnavailableError
from app.llm.base import BaseLLMClient, extract_json_from_text
from app.core.logging import get_logger

logger = get_logger("google_genai")


class GoogleGenAIClient(BaseLLMClient):
    """Client for Google GenAI API targeting Gemma 4 31B (gemma-4-31b-it) with automatic Groq/Mock fallback."""
    def __init__(self, settings: Optional[Settings] = None, allow_fallback: bool = True):
        self.allow_fallback = allow_fallback
        self.settings = settings or get_settings()
        self.api_key = self.settings.effective_google_api_key
        self.model_id = self.settings.LLM_MODEL_ID
        self._client = None
        self._init_client()

    def _init_client(self) -> None:
        if not self.api_key:
            return
        try:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        except Exception as e:
            logger.warning(f"Could not initialize google.genai client: {e}")

    async def _execute_text_fallback(self, prompt: str, system_prompt: Optional[str] = None, reason: str = "") -> str:
        if not self.allow_fallback:
            logger.warning(f"Google GenAI unavailable ({reason}). Fallback disabled; using Mock.")
            from app.llm.mock import MockLLMClient
            return await MockLLMClient().generate_text(prompt, system_prompt)

        logger.warning(f"Google GenAI unavailable ({reason}). Falling back to Groq...")
        try:
            from app.llm.groq import GroqClient
            groq_c = GroqClient(self.settings, allow_fallback=False)
            return await asyncio.wait_for(groq_c.generate_text(prompt, system_prompt), timeout=30.0)
        except Exception as e:
            err_msg = str(e) or type(e).__name__
            logger.warning(f"Groq fallback failed ({err_msg}). Falling back to MockLLMClient.")
            from app.llm.mock import MockLLMClient
            mock = MockLLMClient()
            return await mock.generate_text(prompt, system_prompt)

    async def _execute_json_fallback(self, prompt: str, system_prompt: Optional[str] = None, reason: str = "") -> Dict[str, Any]:
        if not self.allow_fallback:
            logger.warning(f"Google GenAI JSON unavailable ({reason}). Fallback disabled; using Mock.")
            from app.llm.mock import MockLLMClient
            return await MockLLMClient().generate_json(prompt, system_prompt)

        logger.warning(f"Google GenAI JSON generation unavailable ({reason}). Falling back to Groq...")
        try:
            from app.llm.groq import GroqClient
            groq_c = GroqClient(self.settings, allow_fallback=False)
            return await asyncio.wait_for(groq_c.generate_json(prompt, system_prompt), timeout=30.0)
        except Exception as e:
            err_msg = str(e) or type(e).__name__
            logger.warning(f"Groq JSON fallback failed ({err_msg}). Falling back to MockLLMClient.")
            from app.llm.mock import MockLLMClient
            mock = MockLLMClient()
            return await mock.generate_json(prompt, system_prompt)

    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if not self._client:
            return await self._execute_text_fallback(prompt, system_prompt, reason="client not initialized or missing API key")

        full_prompt = f"System: {system_prompt}\n\nUser: {prompt}" if system_prompt else prompt

        for attempt in range(self.settings.LLM_MAX_RETRIES + 1):
            try:
                # Wrap synchronous google.genai call with timeout
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._client.models.generate_content,
                        model=self.model_id,
                        contents=full_prompt,
                    ),
                    timeout=float(self.settings.LLM_TIMEOUT_SECONDS)
                )
                if response and hasattr(response, "text"):
                    return response.text
                return str(response)
            except Exception as e:
                logger.warning(f"Google GenAI attempt {attempt + 1} failed: {e}")
                if attempt == self.settings.LLM_MAX_RETRIES:
                    return await self._execute_text_fallback(
                        prompt,
                        system_prompt,
                        reason=f"Google GenAI failed after {self.settings.LLM_MAX_RETRIES + 1} attempts: {e}"
                    )
                await asyncio.sleep(1.0 * (attempt + 1))
        return await self._execute_text_fallback(prompt, system_prompt, reason="Google GenAI retry loop exhausted")

    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        if not self._client:
            return await self._execute_json_fallback(prompt, system_prompt, reason="client not initialized or missing API key")

        json_sys_prompt = (
            (system_prompt or "") + "\nRespond with valid JSON only. Do not wrap in markdown or commentary."
        ).strip()
        try:
            text = await self.generate_text(prompt, json_sys_prompt)
            try:
                return extract_json_from_text(text)
            except Exception as e:
                logger.warning(f"Malformed JSON from Google GenAI, retrying once: {e}")
                repair_prompt = f"The following output was not valid JSON:\n{text}\n\nProvide ONLY valid JSON:"
                text_retry = await self.generate_text(repair_prompt)
                return extract_json_from_text(text_retry)
        except Exception as e:
            return await self._execute_json_fallback(prompt, system_prompt, reason=str(e))

