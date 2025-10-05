from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.providers.llm import LLMProvider, get_provider
from app.routers.model_utils import resolve_model_or_422
from app.schemas import FlashcardCompletionRequest, FlashcardCompletionResponse
from app.services.flashcard_completion import complete_flashcard

router = APIRouter()


@router.post("/flashcards/complete", response_model=FlashcardCompletionResponse)
async def flashcard_complete(
    req: FlashcardCompletionRequest,
    request: Request,
    provider: LLMProvider = Depends(get_provider),
):
    device_id = getattr(request.state, "device_id", "unknown")
    route = request.url.path
    try:
        chosen_model = resolve_model_or_422(provider, req.model)
        return await complete_flashcard(
            req,
            provider=provider,
            chosen_model=chosen_model,
            device_id=device_id,
            route=route,
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=str(exc)) from exc
