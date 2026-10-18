"""Groq LLM integration targeting ultra-fast inference with fallback support."""
import asyncio
from typing import Dict, Any, Optional
from app.config import Settings, get_settings
from app.errors import LLMUnavailableError
from app.llm.base import BaseLLMClient, extract_json_from_text
from app.core.logging import get_logger

logger = get_logger("groq")


class GroqClient(BaseLLMClient):
    """Client for Groq Cloud API with multi-model retry and Google GenAI/Mock fallback."""

    def __init__(self, settings: Optional[Settings] = None, allow_fallback: bool = True):
        self.allow_fallback = allow_fallback
        self.settings = settings or get_settings()
        self.api_key = self.settings.effective_groq_api_key
        self.primary_model = self.settings.GROQ_PRIMARY_MODEL or self.settings.LLM_MODEL_ID or "qwen/qwen3.8-27b"
        self.fallback_model = self.settings.GROQ_FALLBACK_MODEL or "openai/gpt-oss-20b"
        self._client = None
        self._init_client()

    def _init_client(self) -> None:
        if not self.api_key:
            return
        try:
            from groq import AsyncGroq
            self._client = AsyncGroq(api_key=self.api_key)
        except Exception as e:
            logger.error(f"Groq client NOT available ({e}). Install the `groq` package; falling back.")

    async def _execute_text_fallback(self, prompt: str, system_prompt: Optional[str] = None, reason: str = "") -> str:
        if not self.allow_fallback:
            logger.warning(f"Groq unavailable ({reason}). Fallback disabled; using Mock.")
            from app.llm.mock import MockLLMClient
            return await MockLLMClient().generate_text(prompt, system_prompt)

        logger.warning(f"Groq unavailable ({reason}). Trying Google GenAI fallback...")
        if self.settings.effective_google_api_key:
            try:
                from app.llm.google_genai import GoogleGenAIClient
                google_client = GoogleGenAIClient(self.settings, allow_fallback=False)
                return await asyncio.wait_for(google_client.generate_text(prompt, system_prompt), timeout=30.0)
            except Exception as e:
                logger.warning(f"Google GenAI fallback failed ({e}). Falling back to MockLLMClient.")
        else:
            logger.warning("No Google GenAI API key configured. Falling back to MockLLMClient.")

        from app.llm.mock import MockLLMClient
        mock = MockLLMClient()
        return await mock.generate_text(prompt, system_prompt)

    async def _execute_json_fallback(self, prompt: str, system_prompt: Optional[str] = None, reason: str = "") -> Dict[str, Any]:
        if not self.allow_fallback:
            logger.warning(f"Groq JSON unavailable ({reason}). Fallback disabled; using Mock.")
            from app.llm.mock import MockLLMClient
            return await MockLLMClient().generate_json(prompt, system_prompt)

        logger.warning(f"Groq JSON unavailable ({reason}). Trying Google GenAI fallback...")
        if self.settings.effective_google_api_key:
            try:
                from app.llm.google_genai import GoogleGenAIClient
                google_client = GoogleGenAIClient(self.settings, allow_fallback=False)
                return await asyncio.wait_for(google_client.generate_json(prompt, system_prompt), timeout=30.0)
            except Exception as e:
                logger.warning(f"Google GenAI fallback failed ({e}). Falling back to MockLLMClient.")
        else:
            logger.warning("No Google GenAI API key configured. Falling back to MockLLMClient.")

        from app.llm.mock import MockLLMClient
        mock = MockLLMClient()
        return await mock.generate_json(prompt, system_prompt)

    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if not self._client:
            return await self._execute_text_fallback(prompt, system_prompt, reason="client not initialized or missing GROQ_API_KEY")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        models_to_try = [self.primary_model]
        if self.fallback_model and self.fallback_model != self.primary_model:
            models_to_try.append(self.fallback_model)

        for model in models_to_try:
            for attempt in range(self.settings.LLM_MAX_RETRIES + 1):
                try:
                    response = await asyncio.wait_for(
                        self._client.chat.completions.create(
                            model=model,
                            messages=messages,
                            temperature=self.settings.LLM_TEMPERATURE,
                            max_tokens=self.settings.LLM_MAX_OUTPUT_TOKENS,
                        ),
                        timeout=float(self.settings.LLM_TIMEOUT_SECONDS)
                    )
                    content = response.choices[0].message.content
                    if content:
                        return content
                except Exception as e:
                    logger.warning(f"Groq attempt {attempt + 1} with model {model} failed: {e}")
                    if attempt < self.settings.LLM_MAX_RETRIES:
                        await asyncio.sleep(1.0 * (attempt + 1))

        return await self._execute_text_fallback(
            prompt, system_prompt, reason=f"All Groq models {models_to_try} exhausted retries"
        )

    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        if not self._client:
            return await self._execute_json_fallback(prompt, system_prompt, reason="client not initialized or missing GROQ_API_KEY")

        json_sys_prompt = (
            (system_prompt or "") + "\nRespond with valid JSON only. Do not wrap in markdown or commentary."
        ).strip()

        messages = [
            {"role": "system", "content": json_sys_prompt},
            {"role": "user", "content": prompt}
        ]

        models_to_try = [self.primary_model]
        if self.fallback_model and self.fallback_model != self.primary_model:
            models_to_try.append(self.fallback_model)

        for model in models_to_try:
            for attempt in range(self.settings.LLM_MAX_RETRIES + 1):
                try:
                    try:
                        response = await asyncio.wait_for(
                            self._client.chat.completions.create(
                                model=model,
                                messages=messages,
                                temperature=self.settings.LLM_TEMPERATURE,
                                max_tokens=self.settings.LLM_MAX_OUTPUT_TOKENS,
                                response_format={"type": "json_object"}
                            ),
                            timeout=float(self.settings.LLM_TIMEOUT_SECONDS)
                        )
                        content = response.choices[0].message.content
                    except Exception as rf_err:
                        logger.warning(f"Groq response_format failed ({rf_err}), retrying without response_format constraint")
                        response = await asyncio.wait_for(
                            self._client.chat.completions.create(
                                model=model,
                                messages=messages,
                                temperature=self.settings.LLM_TEMPERATURE,
                                max_tokens=self.settings.LLM_MAX_OUTPUT_TOKENS,
                            ),
                            timeout=float(self.settings.LLM_TIMEOUT_SECONDS)
                        )
                        content = response.choices[0].message.content

                    if content:
                        try:
                            return extract_json_from_text(content)
                        except Exception as parse_err:
                            logger.warning(f"JSON parsing error on model {model}: {parse_err}. Attempting 1 repair retry.")
                            repair_messages = list(messages) + [
                                {"role": "assistant", "content": content},
                                {"role": "user", "content": "The previous output was not valid JSON. Provide ONLY valid JSON:"}
                            ]
                            repair_resp = await asyncio.wait_for(
                                self._client.chat.completions.create(
                                    model=model,
                                    messages=repair_messages,
                                    temperature=0.1,
                                    max_tokens=self.settings.LLM_MAX_OUTPUT_TOKENS
                                ),
                                timeout=float(self.settings.LLM_TIMEOUT_SECONDS)
                            )
                            return extract_json_from_text(repair_resp.choices[0].message.content)
                except Exception as e:
                    logger.warning(f"Groq JSON attempt {attempt + 1} with model {model} failed: {e}")
                    if attempt < self.settings.LLM_MAX_RETRIES:
                        await asyncio.sleep(1.0 * (attempt + 1))

        return await self._execute_json_fallback(prompt, system_prompt, reason="Groq JSON retry loop exhausted")
