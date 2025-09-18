from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.content_store import ContentStore
from app.schemas import CloudDeckSummary, CloudDeckDetail, CloudCard, CloudBookSummary, CloudBookDetail, BankItem


router = APIRouter()
_CONTENT = ContentStore()


@router.get("/cloud/decks", response_model=list[CloudDeckSummary])
def cloud_decks():
    decks = _CONTENT.list_decks()
    return [CloudDeckSummary(id=d["id"], name=d["name"], count=len(d.get("cards", []))) for d in decks]


@router.get("/cloud/decks/{deck_id}", response_model=CloudDeckDetail)
def cloud_deck_detail(deck_id: str):
    deck = _CONTENT.get_deck(deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="not_found")
    cards = [CloudCard.model_validate(c) for c in deck.get("cards", [])]
    return CloudDeckDetail(id=deck["id"], name=deck["name"], cards=cards)


@router.get("/cloud/books", response_model=list[CloudBookSummary])
def cloud_books():
    books = _CONTENT.list_books()
    return [CloudBookSummary(name=b["name"], count=len(b.get("items", []))) for b in books]


@router.get("/cloud/books/{name}", response_model=CloudBookDetail)
def cloud_book_detail(name: str):
    # name is URL-decoded by FastAPI
    book = _CONTENT.get_book_by_name(name)
    if not book:
        raise HTTPException(status_code=404, detail="not_found")
    items = [BankItem.model_validate(it) for it in book.get("items", [])]
    return CloudBookDetail(name=book["name"], items=items)

