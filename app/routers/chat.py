from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.providers.llm import LLMProvider, get_provider
from app.schemas import (
    ChatTurnRequest,
    ChatTurnResponse,
    ChatResearchRequest,
    ChatResearchResponse,
)
from app.services.chat import run_turn, run_research

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
