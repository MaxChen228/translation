from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.providers.llm import LLMProvider, get_provider
from app.schemas import (
    ChatResearchRequest,
    ChatResearchResponse,
    ChatTurnRequest,
    ChatTurnResponse,
)
from app.services.chat import run_research, run_turn

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/respond", response_model=ChatTurnResponse)
async def chat_respond(
    req: ChatTurnRequest,
    request: Request,
    provider: LLMProvider = Depends(get_provider),
) -> ChatTurnResponse:
    route = request.url.path
    device_id = getattr(request.state, "device_id", "unknown")
    return await run_turn(req, provider, device_id=device_id, route=route)


@router.post("/research", response_model=ChatResearchResponse)
async def chat_research(
    req: ChatResearchRequest,
    request: Request,
    provider: LLMProvider = Depends(get_provider),
) -> ChatResearchResponse:
    route = request.url.path
    device_id = getattr(request.state, "device_id", "unknown")
    return await run_research(req, provider, device_id=device_id, route=route)
