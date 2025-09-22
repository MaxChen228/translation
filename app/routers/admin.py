from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.content_store import get_content_store
from app.core.settings import get_settings
from app.core.logging import logger

router = APIRouter(prefix="/admin", tags=["admin"])
_CONTENT = get_content_store()


def _verify_content_token(x_content_token: Optional[str] = Header(default=None)) -> None:
    expected = get_settings().CONTENT_ADMIN_TOKEN
    if expected is None:
        return
    if x_content_token != expected:
        logger.warning("admin_invalid_token")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")


@router.post("/content/reload")
def reload_content(_: None = Depends(_verify_content_token)):
    _CONTENT.reload()
    stats = _CONTENT.stats()
    logger.info("content_reloaded", extra=stats)
    return {"status": "ok", "stats": stats}
