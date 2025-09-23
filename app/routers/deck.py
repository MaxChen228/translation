from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Request

from app.llm import load_deck_prompt
from app.schemas import DeckMakeRequest, DeckMakeResponse
from app.services.deck_maker import make_deck_from_request
from app.providers.llm import LLMProvider, get_provider


router = APIRouter()


def _resolve_model(provider: LLMProvider, override: str | None) -> str:
    try:
        return provider.resolve_model(override)
    except ValueError as e:
        from json import loads

        try:
            detail = loads(e.args[0])
        except Exception:
            detail = {"invalid_model": str(override)}
        raise HTTPException(status_code=422, detail=detail)


@router.post("/make_deck", response_model=DeckMakeResponse)
def make_deck(req: DeckMakeRequest, request: Request, provider: LLMProvider = Depends(get_provider)):
    route = request.url.path
    device_id = getattr(request.state, "device_id", "unknown")
    try:
        chosen_model = _resolve_model(provider, req.model)
        deck_prompt = load_deck_prompt()
        return make_deck_from_request(
            req,
            deck_prompt,
            chosen_model,
            device_id=device_id,
            route=route,
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        status = 500
        msg = str(e)
        if "status=429" in msg:
            status = 429
        raise HTTPException(status_code=status, detail=msg)
