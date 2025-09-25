from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Depends, Request

from app.llm import load_system_prompt, load_merge_prompt
from app.providers.llm import LLMProvider, get_provider
from app.schemas import (
    CorrectRequest,
    CorrectResponse,
    MergeErrorsRequest,
    MergeErrorResponse,
)
from app.services.corrector import build_user_content, validate_correct_response
from app.services.merge import build_merge_user_content, validate_merge_response
from app.usage.recorder import record_usage


router = APIRouter()


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
async def correct(req: CorrectRequest, request: Request, provider: LLMProvider = Depends(get_provider)):
    route = request.url.path
    device_id = getattr(request.state, "device_id", "unknown")
    try:
        system_prompt = load_system_prompt()
        user_content = build_user_content(req)
        chosen_model = _resolve_model(provider, req.model)
        obj, usage = await provider.generate_json(
            system_prompt=system_prompt,
            user_content=user_content,
            model=chosen_model,
        )
        record_usage(usage, route=route, device_id=device_id)
        resp = validate_correct_response(obj)
    except HTTPException as he:
        raise he
    except Exception as e:
        msg = str(e)
        status = 500
        if "status=429" in msg:
            status = 429
        raise HTTPException(status_code=status, detail=msg)
    return resp


@router.post("/correct/merge", response_model=MergeErrorResponse)
async def merge(req: MergeErrorsRequest, request: Request, provider: LLMProvider = Depends(get_provider)):
    route = request.url.path
    device_id = getattr(request.state, "device_id", "unknown")
    try:
        merge_prompt = load_merge_prompt()
        user_content = build_merge_user_content(req)
        chosen_model = _resolve_model(provider, req.model)
        obj, usage = await provider.generate_json(
            system_prompt=merge_prompt,
            user_content=user_content,
            model=chosen_model,
        )
        record_usage(usage, route=route, device_id=device_id)
        resp = validate_merge_response(obj)
    except HTTPException as he:
        raise he
    except Exception as e:
        msg = str(e)
        status = 500
        if "status=429" in msg:
            status = 429
        raise HTTPException(status_code=status, detail=msg)
    return resp
