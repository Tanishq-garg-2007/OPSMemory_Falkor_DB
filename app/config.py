"""Application configuration using Pydantic Settings."""
import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    # LLM Settings
    LLM_PROVIDER: str = "google_genai"
    LLM_MODEL_ID: str = "gemma-4-31b-it"
    GOOGLE_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    LLM_TIMEOUT_SECONDS: int = 60
    LLM_MAX_RETRIES: int = 2
    LLM_MAX_OUTPUT_TOKENS: int = 700
    LLM_TEMPERATURE: float = 0.1
    REAL_LLM: int = 0
    LLM_FALLBACK_PROVIDER: str = "mock"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL_ID: Optional[str] = None

    # FalkorDB settings
    FALKORDB_HOST: str = "localhost"
    FALKORDB_PORT: int = 6379
    FALKORDB_PASSWORD: Optional[str] = None
    FALKORDB_TIMEOUT_SECONDS: float = 3.0

    # SQLite persistence & FTS
    SQLITE_DB_PATH: str = "opsmemory.db"

    # Retrieval
    ENABLE_EMBEDDINGS: bool = False
    EVIDENCE_TOKEN_BUDGET: int = 1200
    RRF_K: int = 60

    @property
    def effective_google_api_key(self) -> Optional[str]:
        return self.GOOGLE_API_KEY or self.GEMINI_API_KEY or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

    def tenant_graph_name(self, tenant_id: str) -> str:
        """Derive server-side FalkorDB graph name for tenant."""
        clean_tenant = "".join(c for c in tenant_id.lower() if c.isalnum() or c == "_")
        if not clean_tenant:
            raise ValueError(f"Invalid tenant_id '{tenant_id}'")
        return f"tenant_{clean_tenant}"


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
