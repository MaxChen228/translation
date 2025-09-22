from __future__ import annotations

from fastapi import FastAPI, Request

from app.routers.correct import router as correct_router
from app.routers.deck import router as deck_router
from app.routers.cloud import router as cloud_router
from app.routers.sys import router as sys_router
from app.routers.chat import router as chat_router
from app.usage.router import router as usage_router
from app.routers.admin import router as admin_router


def create_app() -> FastAPI:
    app = FastAPI(title="Local Correct Backend", version="0.4.3")

    @app.middleware("http")
    async def attach_device_id(request: Request, call_next):
        header = request.headers.get("X-Device-Id") or request.headers.get("X-Client-Device")
        request.state.device_id = (header or "unknown").strip() or "unknown"
        return await call_next(request)

    app.include_router(sys_router)
    app.include_router(correct_router)
    app.include_router(deck_router)
    app.include_router(cloud_router)
    app.include_router(chat_router)
    app.include_router(usage_router)
    app.include_router(admin_router)
    return app
