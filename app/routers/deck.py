from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.llm import load_deck_prompt
from app.providers.llm import LLMProvider, get_provider
from app.routers.model_utils import resolve_model_or_422
from app.schemas import DeckMakeRequest, DeckMakeResponse
from app.services.deck_maker import make_deck_from_request

router = APIRouter()


@router.post("/make_deck", response_model=DeckMakeResponse)
async def make_deck(req: DeckMakeRequest, request: Request, provider: LLMProvider = Depends(get_provider)):
    route = request.url.path
    device_id = getattr(request.state, "device_id", "unknown")
    try:
        chosen_model = resolve_model_or_422(provider, req.model)
        deck_prompt = load_deck_prompt()
        return await make_deck_from_request(
            req,
            deck_prompt,
            chosen_model,
            device_id=device_id,
            route=route,
        )
    except HTTPException as he:
        raise he
    except Exception as exc:
        status = 500
        msg = str(exc)
        if "status=429" in msg:
            status = 429
        raise HTTPException(status_code=status, detail=msg) from exc
