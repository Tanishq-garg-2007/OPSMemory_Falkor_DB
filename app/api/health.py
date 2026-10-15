"""Health check endpoint."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from typing import Dict, Any
from app.config import Settings, get_settings

router = APIRouter(tags=["Health"])


@router.get("/healthz")
async def health_check(settings: Settings = Depends(get_settings)):
    """Returns application health, persistence health, and LLM provider configuration."""
    from app.memory.repository import get_memory_repository
    repo = get_memory_repository()
    db_health = repo.check_health()

    body = {
        "status": "ok" if db_health.get("ok") else "unavailable",
        "app": "opsmemory",
        "version": "0.1.0",
        "database": db_health,
        "llm": {
            "provider": settings.LLM_PROVIDER,
            "model_id": settings.LLM_MODEL_ID,
            "real_llm": bool(settings.REAL_LLM),
            "fallback_provider": settings.LLM_FALLBACK_PROVIDER,
            "has_google_key": bool(settings.effective_google_api_key)
        }
    }
    return JSONResponse(status_code=200 if db_health.get("ok") else 503, content=body)