from __future__ import annotations

import json
import os
import uuid
from typing import Dict, List, Optional

from app.schemas import BankHint, BankItem, BankSuggestion
from app.config import content_dir
from app.core.logging import logger


# Fallback in-code seeds (used only when data/ folders are empty)
CLOUD_DECKS_SEED = [
    {
        "id": "starter-phrases",
        "name": "Starter Phrases",
        "cards": [
            {"front": "Hello!", "back": "你好！"},
            {"front": "How are you?", "back": "你最近好嗎？"},
            {"front": "Thank you.", "back": "謝謝你。"},
        ],
    },
    {
        "id": "common-errors",
        "name": "Common Errors",
        "cards": [
            {"front": "I look forward to hear from you.", "back": "更自然：I look forward to hearing from you."},
            {"front": "He suggested me to go.", "back": "更自然：He suggested that I go / He suggested going."},
        ],
    },
]

CLOUD_BOOKS_SEED = [
    {
        "name": "Daily Conversations",
        "items": [
            {"id": "conv-greet", "zh": "跟陌生人打招呼", "hints": [], "suggestions": [], "tags": ["daily"], "difficulty": 1},
            {"id": "conv-order", "zh": "點餐時的常見句型", "hints": [], "suggestions": [], "tags": ["daily"], "difficulty": 2},
        ],
    },
    {
        "name": "Academic Writing",
        "items": [
            {"id": "acad-intro", "zh": "撰寫研究引言", "hints": [], "suggestions": [], "tags": ["academic"], "difficulty": 3},
            {"id": "acad-method", "zh": "描述研究方法", "hints": [], "suggestions": [], "tags": ["academic"], "difficulty": 3},
        ],
    },
]


class ContentStore:
    """Load curated decks/books from JSON files if present; otherwise, fallback to seeds.

    Layout (default base from $CONTENT_DIR or backend/data):
      data/decks/<id>.json  { id, name, cards:[{ id?, front, back, frontNote?, backNote? }] }
      data/books/<id>.json  { id, name, items:[{ id, zh, hints:[], suggestions:[], tags?, difficulty? }] }
    """

    def __init__(self) -> None:
        # Use centralized content directory resolution
        self.base = content_dir()
        self._decks_by_id: Dict[str, dict] = {}
        self._books_by_name: Dict[str, dict] = {}
        self._loaded = False

    def _json_files(self, sub: str) -> List[str]:
        p = os.path.join(self.base, sub)
        try:
            return [os.path.join(p, f) for f in os.listdir(p) if f.endswith(".json")]
        except FileNotFoundError:
            return []

    def _read(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _ensure_card_ids(self, deck: dict) -> dict:
        deck_id = deck.get("id") or deck.get("name") or "deck"
        cards = []
        for idx, c in enumerate(deck.get("cards", [])):
            cid = c.get("id") or str(uuid.uuid5(uuid.NAMESPACE_URL, f"deck:{deck_id}:{idx}"))
            cards.append({
                "id": cid,
                "front": c.get("front", ""),
                "back": c.get("back", ""),
                **({"frontNote": c.get("frontNote")} if c.get("frontNote") is not None else {}),
                **({"backNote": c.get("backNote")} if c.get("backNote") is not None else {}),
            })
        d = dict(deck)
        d["cards"] = cards
        return d

    def load(self) -> None:
        if self._loaded:
            return
        deck_files = self._json_files("decks")
        book_files = self._json_files("books")
        if not deck_files and not book_files:
            # fallback to in-code lists
            self._decks_by_id = {d["id"]: d for d in CLOUD_DECKS_SEED}
            self._books_by_name = {b["name"]: b for b in CLOUD_BOOKS_SEED}
            self._loaded = True
            return
        # Load decks
        decks: Dict[str, dict] = {}
        for fp in deck_files:
            try:
                d = self._read(fp)
                did = d.get("id") or os.path.splitext(os.path.basename(fp))[0]
                d["id"] = did
                if not d.get("name"):
                    d["name"] = did
                d = self._ensure_card_ids(d)
                decks[did] = d
            except Exception as e:
                logger.warning("cloud_deck_load_error", extra={"path": fp, "error": str(e)})
        # Load books (strict validation: hints.category must be one of five allowed)
        books_by_name: Dict[str, dict] = {}
        for fp in book_files:
            try:
                b = self._read(fp)
                if not b.get("name"):
                    b["name"] = b.get("id") or os.path.splitext(os.path.basename(fp))[0]
                # Normalize and strictly validate items using Pydantic models
                items: List[dict] = []
                for it in b.get("items", []):
                    hint_objs = [BankHint(**h) for h in it.get("hints", [])]
                    sugg_objs = [BankSuggestion(**s) for s in it.get("suggestions", [])]
                    bi = BankItem(
                        id=it.get("id") or str(uuid.uuid4()),
                        zh=it.get("zh", ""),
                        hints=hint_objs,
                        suggestions=sugg_objs,
                        tags=it.get("tags", []),
                        difficulty=int(it.get("difficulty", 1)),
                    )
                    items.append(bi.model_dump())
                b["items"] = items
                books_by_name[b["name"]] = b
            except Exception as e:
                logger.warning("cloud_book_load_error", extra={"path": fp, "error": str(e)})
        if not decks:
            self._decks_by_id = {d["id"]: d for d in CLOUD_DECKS_SEED}
        else:
            self._decks_by_id = decks
        if not books_by_name:
            self._books_by_name = {b["name"]: b for b in CLOUD_BOOKS_SEED}
        else:
            self._books_by_name = books_by_name
        self._loaded = True

    # API helpers
    def list_decks(self) -> List[dict]:
        self.load()
        return list(self._decks_by_id.values())

    def get_deck(self, deck_id: str) -> Optional[dict]:
        self.load()
        d = self._decks_by_id.get(deck_id)
        return self._ensure_card_ids(d) if d else None

    def list_books(self) -> List[dict]:
        self.load()
        return list(self._books_by_name.values())

    def get_book_by_name(self, name: str) -> Optional[dict]:
        self.load()
        return self._books_by_name.get(name)
