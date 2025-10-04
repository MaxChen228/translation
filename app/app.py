from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.routers.correct import router as correct_router
from app.routers.deck import router as deck_router
from app.routers.flashcards import router as flashcards_router
from app.routers.cloud import router as cloud_router
from app.routers.sys import router as sys_router
from app.routers.chat import router as chat_router
from app.routers.control_center import router as control_center_router
from app.routers.daily_push import router as daily_push_router
from app.usage.router import router as usage_router
from app.routers.admin import router as admin_router
from app.routers.content_ui import router as content_ui_router
from app.core.http_client import init_http_client, close_http_client


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_http_client()
        try:
            yield
        finally:
            await close_http_client()

    app = FastAPI(title="Local Correct Backend", version="0.5.0", lifespan=lifespan)

    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.middleware("http")
    async def attach_device_id(request: Request, call_next):
        header = request.headers.get("X-Device-Id") or request.headers.get("X-Client-Device")
        request.state.device_id = (header or "unknown").strip() or "unknown"
        return await call_next(request)

    app.include_router(sys_router)
    app.include_router(correct_router)
    app.include_router(deck_router)
    app.include_router(flashcards_router)
    app.include_router(cloud_router)
    app.include_router(chat_router)
    app.include_router(daily_push_router)
    app.include_router(usage_router)
    app.include_router(admin_router)
    app.include_router(content_ui_router)
    app.include_router(control_center_router)
    return app
