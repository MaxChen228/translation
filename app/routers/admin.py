from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.content_store import get_content_store
from app.core.settings import get_settings
from app.core.logging import logger
from app.services.content_manager import get_content_manager
from app.schemas import (
    ContentUploadRequest,
    ContentUploadResponse,
    BulkUploadRequest,
)

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


@router.post("/content/upload", response_model=ContentUploadResponse)
def upload_content(req: ContentUploadRequest, _: None = Depends(_verify_content_token)):
    """上傳單個內容文件"""
    content_manager = get_content_manager()

    result = content_manager.upload_content(
        filename=req.filename,
        content=req.content,
        content_type=req.content_type
    )

    # 如果上傳成功，重新載入內容
    if result.success:
        try:
            _CONTENT.reload()
            logger.info("content_uploaded_and_reloaded", extra={
                "upload_filename": req.filename,
                "content_type": req.content_type
            })
        except Exception as e:
            logger.warning("content_reload_after_upload_failed", extra={"error": str(e)})

    return ContentUploadResponse(
        results=[result],
        success_count=1 if result.success else 0,
        error_count=0 if result.success else 1
    )


@router.post("/content/upload/bulk", response_model=ContentUploadResponse)
def upload_bulk_content(req: BulkUploadRequest, _: None = Depends(_verify_content_token)):
    """批量上傳內容文件"""
    content_manager = get_content_manager()
    results = []

    for file_data in req.files:
        result = content_manager.upload_content(
            filename=file_data.filename,
            content=file_data.content,
            content_type=file_data.content_type
        )
        results.append(result)

    success_count = sum(1 for r in results if r.success)
    error_count = len(results) - success_count

    # 如果有成功上傳的文件且設定要重新載入，則重新載入內容
    if success_count > 0 and req.reload_after_upload:
        try:
            _CONTENT.reload()
            logger.info("content_bulk_uploaded_and_reloaded", extra={
                "total_files": len(req.files),
                "success_count": success_count,
                "error_count": error_count,
                "upload_filenames": [f.filename for f in req.files],
            })
        except Exception as e:
            logger.warning("content_reload_after_bulk_upload_failed", extra={"error": str(e)})

    return ContentUploadResponse(
        results=results,
        success_count=success_count,
        error_count=error_count
    )


@router.get("/content/stats")
def get_content_stats(_: None = Depends(_verify_content_token)):
    """獲取內容統計信息"""
    content_manager = get_content_manager()
    manager_stats = content_manager.get_content_stats()
    store_stats = _CONTENT.stats()

    return {
        "status": "ok",
        "file_system": manager_stats,
        "loaded_in_memory": store_stats
    }
