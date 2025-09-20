from __future__ import annotations

from fastapi import APIRouter, Depends

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
def chat_respond(req: ChatTurnRequest, provider: LLMProvider = Depends(get_provider)) -> ChatTurnResponse:
    return run_turn(req, provider)


@router.post("/research", response_model=ChatResearchResponse)
def chat_research(req: ChatResearchRequest, provider: LLMProvider = Depends(get_provider)) -> ChatResearchResponse:
    return run_research(req, provider)
