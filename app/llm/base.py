"""Base interface and utilities for LLM providers."""
import json
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from app.errors import LLMUnavailableError


def extract_json_from_text(text: str) -> Dict[str, Any]:
    """Robustly extract and parse JSON object from LLM response text."""
    text = text.strip()
    # Try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # Try fenced code block
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    # Try matching first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end+1]
        try:
            return json.loads(candidate)
        except Exception:
            # Simple repair: remove trailing commas
            repaired = re.sub(r",\s*([\]}])", r"\1", candidate)
            try:
                return json.loads(repaired)
            except Exception:
                pass

    raise ValueError(f"Could not parse valid JSON from text: {text[:120]}...")


class BaseLLMClient(ABC):
    """Abstract base LLM client."""

    @abstractmethod
    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate raw text response."""
        pass

    @abstractmethod
    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Generate structured JSON response."""
        pass
