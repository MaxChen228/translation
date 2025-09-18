from __future__ import annotations

import os
import json
import time
import uuid
from typing import List, Optional, Dict

import requests
from fastapi import FastAPI, HTTPException, Query
from app.content_store import ContentStore
from app.llm import (
    GEMINI_BASE,
    load_system_prompt,
    load_deck_prompt,
    call_gemini_json as llm_call_json,
    resolve_model as llm_resolve_model,
    get_current_model,
)
from app.services.corrector import build_user_content, validate_correct_response
from app.schemas import (
    RangeDTO,
    InputHintDTO,
    ErrorHintsDTO,
    ErrorDTO,
    CorrectResponse,
    CorrectRequest,
    CloudDeckSummary,
    CloudCard,
    CloudDeckDetail,
    CloudBookSummary,
    CloudBookDetail,
    BankHint,
    BankSuggestion,
    BankItem,
    ProgressRecord,
    ProgressMarkRequest,
    ProgressRecordOut,
    ProgressSummary,
    ImportRequest,
    ImportResponse,
    DeckMakeItem,
    DeckMakeRequest,
    DeckCard,
    DeckMakeResponse,
)
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover - optional
    load_dotenv = None


"""Main FastAPI app entry.

Step 1 modularization: Pydantic schemas moved to app.schemas.
"""


# ----- LLM Provider (Gemini only) -----

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Load .env if present (repo root or backend/). Simplifies local dev.
if load_dotenv is not None:
    # try project root
    root_env = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(dotenv_path=root_env)
    # then backend/.env (takes precedence)
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# Model selection (Gemini). You can override via LLM_MODEL or GEMINI_MODEL.
GENERIC_MODEL = os.environ.get("LLM_MODEL")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", GENERIC_MODEL or "gemini-2.5-flash")
# Allow-list for request-time model override (extendable via env ALLOWED_MODELS)
_ALLOWED_MODEL_ENV = os.environ.get("ALLOWED_MODELS")
if _ALLOWED_MODEL_ENV:
    ALLOWED_MODELS = {m.strip() for m in _ALLOWED_MODEL_ENV.split(",") if m.strip()}
else:
    ALLOWED_MODELS = {"gemini-2.5-pro", "gemini-2.5-flash"}


SYSTEM_PROMPT = load_system_prompt()
DECK_PROMPT = load_deck_prompt()

# ----- Deck debug logging -----
def _deck_debug_enabled() -> bool:
    v = os.environ.get("DECK_DEBUG_LOG", "1").lower()
    return v in ("1", "true", "yes", "on")

def _deck_debug_write(payload: Dict):
    if not _deck_debug_enabled():
        return
    try:
        log_dir = os.path.join(os.path.dirname(__file__), "_test_logs")
        os.makedirs(log_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        fn = f"deck_{ts}_{uuid.uuid4().hex[:8]}.json"
        path = os.path.join(log_dir, fn)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _resolve_model(override: Optional[str]) -> str:
    try:
        return llm_resolve_model(override)
    except ValueError as e:
        # e.args[0] carries a JSON string with details
        detail = None
        try:
            detail = json.loads(e.args[0])
        except Exception:
            detail = {"invalid_model": str(override)}
        raise HTTPException(status_code=422, detail=detail)


def call_gemini_correct(req: CorrectRequest) -> CorrectResponse:
    # Pack user content as compact JSON to avoid parsing ambiguity.
    user_content = build_user_content(req)
    chosen_model = _resolve_model(req.model)
    obj = llm_call_json(SYSTEM_PROMPT, user_content, model=chosen_model)
    return validate_correct_response(obj)


# ----- FastAPI -----

app = FastAPI(title="Local Correct Backend", version="0.4.2")


# Validation moved to app.services.corrector.validate_correct_response


# simple/offline analyzer removed: backend now requires a working LLM


@app.post("/correct", response_model=CorrectResponse)
def correct(req: CorrectRequest):
    try:
        resp = call_gemini_correct(req)
    except HTTPException as he:
        # Propagate 4xx like 422 invalid types directly
        raise he
    except Exception as e:
        # No offline fallback: require working LLM
        msg = str(e)
        status = 500
        if "status=429" in msg:
            status = 429
        raise HTTPException(status_code=status, detail=msg)
    # Update progress if linked to a bank item; best-effort only
    try:
        _update_progress_after_correct(req.bankItemId, req.deviceId, resp.score)
    except Exception:
        pass
    return resp


@app.get("/healthz")
def healthz() -> dict:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"status": "no_key", "provider": "gemini"}
    try:
        r = requests.get(f"{GEMINI_BASE}/models?key={api_key}", timeout=10)
        if r.status_code // 100 == 2:
            return {"status": "ok", "provider": "gemini", "model": get_current_model()}
        return {"status": "auth_error", "provider": "gemini", "code": r.status_code}
    except Exception as e:
        return {"status": "error", "provider": "gemini", "message": str(e)}


# -----------------------------
# Cloud Library (curated, read-only)
# -----------------------------


_CONTENT = ContentStore()


@app.get("/cloud/decks", response_model=List[CloudDeckSummary])
def cloud_decks():
    decks = _CONTENT.list_decks()
    return [CloudDeckSummary(id=d["id"], name=d["name"], count=len(d.get("cards", []))) for d in decks]


@app.get("/cloud/decks/{deck_id}", response_model=CloudDeckDetail)
def cloud_deck_detail(deck_id: str):
    deck = _CONTENT.get_deck(deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="not_found")
    cards = [CloudCard.model_validate(c) for c in deck.get("cards", [])]
    return CloudDeckDetail(id=deck["id"], name=deck["name"], cards=cards)


@app.get("/cloud/books", response_model=List[CloudBookSummary])
def cloud_books():
    books = _CONTENT.list_books()
    return [CloudBookSummary(name=b["name"], count=len(b.get("items", []))) for b in books]


@app.get("/cloud/books/{name}", response_model=CloudBookDetail)
def cloud_book_detail(name: str):
    # name is URL-decoded by FastAPI
    book = _CONTENT.get_book_by_name(name)
    if not book:
        raise HTTPException(status_code=404, detail="not_found")
    items = [BankItem.model_validate(it) for it in book.get("items", [])]
    return CloudBookDetail(name=book["name"], items=items)


_BANK_DATA: List[BankItem] = []  # legacy; no longer used


# -----------------------------
# Progress tracking (per device)
# -----------------------------

# in-memory: deviceId -> itemId -> ProgressRecord
_PROGRESS: Dict[str, Dict[str, ProgressRecord]] = {}  # legacy; no longer used
_PROGRESS_FILE = os.path.join(os.path.dirname(__file__), "progress.json")  # legacy; no longer used


def _load_progress() -> None:
    pass  # removed


def _save_progress() -> None:
    pass  # removed


def _update_progress_after_correct(bank_item_id: Optional[str], device_id: Optional[str], score: Optional[int]):
    pass  # removed


def _load_bank() -> None:
    pass  # removed


def _save_bank() -> None:
    pass  # removed


# (removed) startup loading of bank/progress; app uses local-only bank


## Bank remote endpoints removed; keeping minimal types for cloud responses


## /bank/items removed


## /bank/random removed


## /bank/books removed


## ImportRequest/ImportResponse moved to app.schemas


def _parse_bank_text(text: str, default_tag: Optional[str]) -> tuple[List[BankItem], List[str]]:
    # Clipboard-friendly plain text parser.
    # Supported keys per block:
    #   ZH:/中文:/題:/句:
    #   DIFF:/難:/難度:    -> 1..5, default 2
    #   TAGS:/標:/標籤:    -> comma separated
    #   HINTS:/提示:       -> lines starting with "- [category]: text" or "- text"
    # Blocks separated by blank lines.
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    items: List[BankItem] = []
    errors: List[str] = []

    def finish(cur: dict):
        if not cur.get("zh"):
            return
        difficulty = cur.get("difficulty") or 2
        try:
            difficulty = int(difficulty)
            if difficulty < 1 or difficulty > 5:
                difficulty = 2
        except Exception:
            difficulty = 2
        tags = cur.get("tags") or []
        if default_tag:
            if default_tag not in tags:
                tags.append(default_tag)
        hints = cur.get("hints") or []
        try:
            items.append(
                BankItem(
                    id=str(uuid.uuid4()),
                    zh=cur["zh"],
                    hints=[BankHint(**h) for h in hints],
                    suggestions=[],
                    tags=tags,
                    difficulty=difficulty,
                )
            )
        except Exception as e:
            errors.append(f"invalid_item: {e}")

    cur: dict = {}
    in_hints = False
    for raw in lines + [""]:  # sentinel
        s = raw.strip()
        if s == "":
            if cur:
                finish(cur)
            cur = {}
            in_hints = False
            continue
        # Hints section handling
        if in_hints and s.startswith("-"):
            body = s.lstrip("- ")
            # accept "category: text" or just "text"
            if ":" in body:
                cat, txt = body.split(":", 1)
                cat_norm = cat.strip().lower()
                # map various labels to five fixed categories used by the app
                def map_cat(c: str) -> str:
                    c = c.lower()
                    if c in {"morphological", "morphology", "morph", "tense", "plural", "singular", "agreement", "grammar"}:
                        return "morphological"
                    if c in {"syntactic", "syntax", "structure", "order", "article", "preposition"}:
                        return "syntactic"
                    if c in {"lexical", "lexicon", "word", "wording", "collocation", "idiom", "choice"}:
                        return "lexical"
                    if c in {"phonological", "phonology", "spelling", "pronunciation"}:
                        return "phonological"
                    if c in {"pragmatic", "usage", "register", "tone", "politeness", "style"}:
                        return "pragmatic"
                    return "lexical"
                cur.setdefault("hints", []).append({"category": map_cat(cat_norm), "text": txt.strip()})
            else:
                # default to lexical if not specified
                cur.setdefault("hints", []).append({"category": "lexical", "text": body.strip()})
            continue
        # Keys
        up = s.upper()
        if up.startswith("ZH:") or s.startswith("中文:") or s.startswith("題:") or s.startswith("句:"):
            cur["zh"] = s.split(":", 1)[1].strip()
            continue
        if up.startswith("DIFF:") or s.startswith("難:") or s.startswith("難度:"):
            cur["difficulty"] = s.split(":", 1)[1].strip()
            continue
        if up.startswith("TAGS:") or s.startswith("標:") or s.startswith("標籤:") or up.startswith("TAG:"):
            val = s.split(":", 1)[1].strip()
            tags = [t.strip() for t in val.replace("；", ",").split(",") if t.strip()]
            cur["tags"] = tags
            continue
        if up.startswith("HINTS:") or s.startswith("提示:"):
            in_hints = True
            continue
        # Otherwise, treat as continuation of zh if zh exists
        if "zh" in cur:
            cur["zh"] = (cur["zh"] + " " + s).strip()
        else:
            errors.append(f"unrecognized_line: {s[:40]}")

    return items, errors


## /bank/import removed


# ----- Progress endpoints removed (schemas available in app.schemas) -----


# -----------------------------
# Make Deck (flashcards)
# -----------------------------

## DeckMake* schemas moved to app.schemas


def call_gemini_make_deck(req: DeckMakeRequest) -> DeckMakeResponse:
    # Compact user JSON to save tokens
    items = [
        {
            k: v
            for k, v in {
                "zh": it.zh,
                "en": it.en,
                "corrected": it.corrected,
                "span": it.span,
                "suggestion": it.suggestion,
                "explainZh": it.explainZh,
                "type": it.type,
            }.items()
            if v not in (None, "")
        }
        for it in req.items
    ]
    compact = {"name": req.name or "未命名", "items": items}
    user_content = json.dumps(compact, ensure_ascii=False)

    chosen_model = _resolve_model(req.model)
    debug_info: Dict[str, object] = {
        "ts": time.time(),
        "provider": "gemini",
        "model": chosen_model,
        "system_prompt": DECK_PROMPT,
        "user_content": user_content,
        "items_in": len(items),
    }
    try:
        obj = llm_call_json(DECK_PROMPT, user_content, model=chosen_model)
    except Exception as e:
        debug_info.update({"json_error": str(e)})
        _deck_debug_write(debug_info)
        raise
    # Validate shape
    if not isinstance(obj, dict) or not isinstance(obj.get("cards"), list):
        debug_info.update({"parsed_obj_head": json.dumps(obj, ensure_ascii=False)[:800]})
        _deck_debug_write(debug_info)
        raise HTTPException(status_code=422, detail="deck_json_invalid_shape")
    # Ensure name falls back to request
    name = (obj.get("name") or req.name or "未命名").strip()
    cards_raw = obj.get("cards") or []
    cards = []
    for c in cards_raw:
        # 支援 camelCase 與 snake_case 鍵名
        fron = (c.get("front") or c.get("zh") or "").strip()
        back = (c.get("back") or c.get("en") or "").strip()
        if not fron or not back:
            continue
        f_note_raw = c.get("frontNote") or c.get("front_note") or ""
        b_note_raw = c.get("backNote") or c.get("back_note") or ""
        f_note = f_note_raw.strip() or None
        b_note = b_note_raw.strip() or None
        cards.append(DeckCard(front=fron, back=back, frontNote=f_note, backNote=b_note))
    debug_info.update({
        "cards_parsed": len(cards),
        "cards_raw_len": len(cards_raw),
        "name_resolved": name,
    })
    _deck_debug_write(debug_info)
    if not cards:
        raise HTTPException(status_code=422, detail="deck_cards_empty")
    return DeckMakeResponse(name=name, cards=cards)


@app.post("/make_deck", response_model=DeckMakeResponse)
def make_deck(req: DeckMakeRequest):
    try:
        return call_gemini_make_deck(req)
    except HTTPException as he:
        raise he
    except Exception as e:
        status = 500
        msg = str(e)
        if "status=429" in msg:
            status = 429
        raise HTTPException(status_code=status, detail=msg)


def dev():  # uvicorn entry helper
    import uvicorn

    # Bind to all interfaces by default so phones on the same LAN can connect.
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    # Run by passing the app object directly to avoid import path issues
    uvicorn.run(app, host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    dev()
