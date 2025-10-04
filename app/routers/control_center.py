from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.content_store import get_content_store
from app.core.settings import get_settings
from app.routers.admin import _verify_content_token
from app.routers.sys import healthz as sys_health_check
from app.question_store import QuestionStore
from app.usage.recorder import summarize_usage
from app.services.content_manager import get_content_manager
from app.services.prompt_manager import list_prompts, read_prompt, write_prompt
from app.schemas import (
    PromptUploadRequest,
    PromptUploadResponse,
    PromptUploadResult,
)
from app.llm import reload_prompts

router = APIRouter(prefix="/admin/control-center", tags=["admin-control-center"])
_templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


class PromptMetadata(BaseModel):
    promptId: str
    path: str
    cacheKey: str
    lastModified: Optional[float] = None


class PromptListPayload(BaseModel):
    prompts: List[PromptMetadata]


def _load_daily_summary(limit: int, settings) -> List[dict]:
    limit = max(1, min(limit, 30))
    store = QuestionStore(db_url=settings.QUESTION_DB_URL, db_path=settings.QUESTION_DB_PATH)
    try:
        return store.recent_summary(limit=limit)
    finally:
        store.close()


@router.get("", response_class=HTMLResponse)
def render_control_center(request: Request) -> HTMLResponse:
    return _templates.TemplateResponse("admin/control_center.html", {"request": request})


@router.get("/overview")
def control_center_overview(_: None = Depends(_verify_content_token)) -> Dict[str, Any]:
    now = dt.datetime.utcnow()
    since_ts = (now - dt.timedelta(hours=24)).timestamp()
    usage_last24h = summarize_usage(since=since_ts)
    usage_all_time = summarize_usage()

    content_store = get_content_store()
    loaded_stats = content_store.stats()
    manager_stats = get_content_manager().get_content_stats()

    settings = get_settings()
    question_summary = _load_daily_summary(limit=7, settings=settings)

    latest_item = question_summary[0] if question_summary else None
    generated_payload = {
        "latestDate": latest_item["question_date"].isoformat() if latest_item else None,
        "questionCount": latest_item["question_count"] if latest_item else 0,
        "deliveredDevices": latest_item["delivered_devices"] if latest_item else 0,
        "recent": [
            {
                "date": entry["question_date"].isoformat(),
                "questionCount": entry["question_count"],
                "deliveredDevices": entry["delivered_devices"],
            }
            for entry in question_summary
        ],
    }

    overview = {
        "health": sys_health_check(),
        "generated": generated_payload,
        "usage": {
            "last24h": usage_last24h.model_dump(mode="json"),
            "allTime": usage_all_time.model_dump(mode="json"),
        },
        "content": {
            "loaded": loaded_stats,
            "files": manager_stats,
        },
        "environment": {
            "hasQuestionDbUrl": settings.QUESTION_DB_URL is not None,
            "hasQuestionDbPath": bool(settings.QUESTION_DB_PATH),
        },
    }
    return overview


@router.get("/daily-summary")
def control_center_daily_summary(
    limit: int = 7,
    _: None = Depends(_verify_content_token),
) -> Dict[str, Any]:
    settings = get_settings()
    summary = _load_daily_summary(limit=limit, settings=settings)
    latest = summary[0] if summary else None
    return {
        "limit": limit,
        "latest": {
            "date": latest["question_date"].isoformat() if latest else None,
            "questionCount": latest["question_count"] if latest else 0,
            "deliveredDevices": latest["delivered_devices"] if latest else 0,
        },
        "recent": [
            {
                "date": entry["question_date"].isoformat(),
                "questionCount": entry["question_count"],
                "deliveredDevices": entry["delivered_devices"],
            }
            for entry in summary
        ],
    }


@router.post("/daily/generate")
def control_center_daily_generate(_: None = Depends(_verify_content_token)) -> Dict[str, Any]:
    command = "python -m scripts.generate_daily_questions --count 6"
    return {
        "status": "manual",
        "message": "請在伺服器上執行指令產生題庫，或整合背景 Job 後再更新此端點。",
        "command": command,
    }


@router.get("/content/stats")
def control_center_content_stats(_: None = Depends(_verify_content_token)) -> Dict[str, Any]:
    store = get_content_store()
    manager = get_content_manager()
    return {
        "loaded": store.stats(),
        "files": manager.get_content_stats(),
    }


@router.post("/content/reload")
def control_center_content_reload(_: None = Depends(_verify_content_token)) -> Dict[str, Any]:
    store = get_content_store()
    store.reload()
    reload_prompts()
    return {"status": "ok", "loaded": store.stats()}


@router.get("/prompts", response_model=PromptListPayload)
def control_center_list_prompts(_: None = Depends(_verify_content_token)) -> PromptListPayload:
    summaries = list_prompts()
    items: List[PromptMetadata] = []
    for prompt_id, info in summaries.items():
        path = info.get("path", "")
        cache_key = info.get("cache_key", "")
        try:
            mtime = os.path.getmtime(path) if path else None
        except OSError:
            mtime = None
        items.append(
            PromptMetadata(
                promptId=prompt_id,
                path=path,
                cacheKey=cache_key,
                lastModified=mtime,
            )
        )
    return PromptListPayload(prompts=sorted(items, key=lambda item: item.promptId))


@router.post("/prompts", response_model=PromptUploadResponse)
def control_center_update_prompt(
    payload: PromptUploadRequest,
    _: None = Depends(_verify_content_token),
) -> PromptUploadResponse:
    try:
        result = write_prompt(payload.promptId, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="prompt_write_failed") from exc

    reload_prompts()
    written_bytes = len((payload.content.rstrip() + "\n").encode("utf-8"))
    response_payload = PromptUploadResult(
        promptId=payload.promptId,
        path=result.get("path", ""),
        backupPath=result.get("backup_path"),
        bytesWritten=written_bytes,
    )
    return PromptUploadResponse(result=response_payload)


@router.post("/prompts/reload")
def control_center_reload_prompts(_: None = Depends(_verify_content_token)) -> Dict[str, str]:
    reload_prompts()
    return {"status": "ok"}


@router.get("/prompts/{prompt_id}")
def control_center_prompt_detail(
    prompt_id: str,
    _: None = Depends(_verify_content_token),
) -> Dict[str, str]:
    try:
        content = read_prompt(prompt_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="prompt_read_failed") from exc
    return {"promptId": prompt_id, "content": content}
