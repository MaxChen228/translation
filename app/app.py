from __future__ import annotations

from fastapi import FastAPI

from app.routers.correct import router as correct_router
from app.routers.deck import router as deck_router
from app.routers.cloud import router as cloud_router
from app.routers.sys import router as sys_router


def create_app() -> FastAPI:
    app = FastAPI(title="Local Correct Backend", version="0.4.3")
    app.include_router(sys_router)
    app.include_router(correct_router)
    app.include_router(deck_router)
    app.include_router(cloud_router)
    return app

