from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.llm import resolve_model as llm_resolve_model, load_deck_prompt
from app.schemas import DeckMakeRequest, DeckMakeResponse
from app.services.deck_maker import make_deck_from_request


router = APIRouter()
DECK_PROMPT = load_deck_prompt()


def _resolve_model(override: str | None) -> str:
    try:
        return llm_resolve_model(override)
    except ValueError as e:
        from json import loads

        try:
            detail = loads(e.args[0])
        except Exception:
            detail = {"invalid_model": str(override)}
        raise HTTPException(status_code=422, detail=detail)


@router.post("/make_deck", response_model=DeckMakeResponse)
def make_deck(req: DeckMakeRequest):
    try:
        chosen_model = _resolve_model(req.model)
        return make_deck_from_request(req, DECK_PROMPT, chosen_model)
    except HTTPException as he:
        raise he
    except Exception as e:
        status = 500
        msg = str(e)
        if "status=429" in msg:
            status = 429
        raise HTTPException(status_code=status, detail=msg)

