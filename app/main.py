"""FastAPI application factory and route registration."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.config import get_settings
from app.errors import OpsMemoryError
from app.api.health import router as health_router
from app.api.chat import router as chat_router
from app.api.conversations import router as conv_router
from app.api.memories import router as mem_router
from app.api.tasks import router as task_router
from app.api.admin import router as admin_router
from app.api.graph import router as graph_router
from app.api.agents import router as agents_router
from app.api.entities import router as entities_router
from app.core.logging import get_logger
import os

logger = get_logger("main")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="OpsMemory",
        description="Persistent-memory and multi-agent coordination system for incident response",
        version="0.1.0",
        debug=settings.DEBUG
    )

    # Global domain exception handler
    @app.exception_handler(OpsMemoryError)
    async def opsmemory_error_handler(request: Request, exc: OpsMemoryError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.__class__.__name__,
                "message": exc.message,
                "details": exc.details
            }
        )

    # Register API routers
    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(conv_router)
    app.include_router(mem_router)
    app.include_router(task_router)
    app.include_router(admin_router)
    app.include_router(graph_router)
    app.include_router(agents_router)
    app.include_router(entities_router)

    # Mount static UI
    static_dir = os.path.join(os.path.dirname(__file__), "ui", "static")
    if os.path.exists(static_dir):
        app.mount("/ui", StaticFiles(directory=static_dir, html=True), name="ui")

    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse(url="/ui/")

    return app


app = create_app()
