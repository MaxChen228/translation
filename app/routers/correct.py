from __future__ import annotations

import json
from typing import Dict

from fastapi import APIRouter, HTTPException, Depends, Request

from app.llm import load_system_prompt
from app.providers.llm import LLMProvider, get_provider
from app.schemas import CorrectRequest, CorrectResponse
from app.services.corrector import build_user_content, validate_correct_response
from app.services.progress import update_after_correct
from app.usage.recorder import record_usage


router = APIRouter()
SYSTEM_PROMPT = load_system_prompt()


def _resolve_model(provider: LLMProvider, override: str | None) -> str:
    try:
        return provider.resolve_model(override)
    except ValueError as e:
        try:
            detail = json.loads(e.args[0])
        except Exception:
            detail = {"invalid_model": str(override)}
        raise HTTPException(status_code=422, detail=detail)


@router.post("/correct", response_model=CorrectResponse)
def correct(req: CorrectRequest, request: Request, provider: LLMProvider = Depends(get_provider)):
    route = request.url.path
    device_id = getattr(request.state, "device_id", "unknown")
    try:
        user_content = build_user_content(req)
        chosen_model = _resolve_model(provider, req.model)
        obj, usage = provider.generate_json(
            system_prompt=SYSTEM_PROMPT,
            user_content=user_content,
            model=chosen_model,
        )
        record_usage(usage.model_copy(update={"route": route, "device_id": device_id}))
        resp = validate_correct_response(obj)
    except HTTPException as he:
        raise he
    except Exception as e:
        msg = str(e)
        status = 500
        if "status=429" in msg:
            status = 429
        raise HTTPException(status_code=status, detail=msg)
    try:
        update_after_correct(req.bankItemId, req.deviceId, resp.score)
    except Exception:
        pass
    return resp
