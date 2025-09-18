from __future__ import annotations

import os
import json
import time
import uuid
from typing import List, Optional, Dict

import requests
from fastapi import FastAPI, HTTPException, Query
from app.llm import (
    GEMINI_BASE,
    get_current_model,
)
from fastapi import APIRouter
from app.routers.correct import router as correct_router
from app.routers.deck import router as deck_router
from app.routers.cloud import router as cloud_router
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover - optional
    load_dotenv = None


"""Main FastAPI app entry.

Step 1 modularization: Pydantic schemas moved to app.schemas.
"""


# Load .env if present (repo root or backend/). Simplifies local dev.
if load_dotenv is not None:
    # try project root
    root_env = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(dotenv_path=root_env)
    # then backend/.env (takes precedence)
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# Prompts, model-resolution, and LLM calls are handled in routers/services


# ----- FastAPI -----

app = FastAPI(title="Local Correct Backend", version="0.4.3")


# simple/offline analyzer removed: backend now requires a working LLM


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


# Cloud endpoints moved into app.routers.cloud


_BANK_DATA = []  # legacy; no longer used


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


# Make-deck endpoint moved into app.routers.deck


def dev():  # uvicorn entry helper
    import uvicorn

    # Bind to all interfaces by default so phones on the same LAN can connect.
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    # Run by passing the app object directly to avoid import path issues
    uvicorn.run(app, host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    dev()

# Mount routers
app.include_router(correct_router)
app.include_router(deck_router)
app.include_router(cloud_router)
