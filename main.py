from __future__ import annotations

import os
import json
import time
import uuid
from typing import List, Optional, Dict

import requests
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover - optional
    load_dotenv = None
try:
    from openai import OpenAI  # type: ignore
except Exception:
    OpenAI = None  # optional, fallback to requests if unavailable


# ----- Schemas (aligned with iOS app) -----

class RangeDTO(BaseModel):
    start: int
    length: int


class ErrorHintsDTO(BaseModel):
    before: Optional[str] = None
    after: Optional[str] = None
    occurrence: Optional[int] = Field(default=None, ge=1)


class ErrorDTO(BaseModel):
    id: Optional[str] = None
    span: str
    type: str  # morphological | syntactic | lexical | phonological | pragmatic
    explainZh: str
    suggestion: Optional[str] = None
    hints: Optional[ErrorHintsDTO] = None
    originalRange: Optional[RangeDTO] = None
    suggestionRange: Optional[RangeDTO] = None
    correctedRange: Optional[RangeDTO] = None


class CorrectResponse(BaseModel):
    corrected: str
    score: int
    errors: List[ErrorDTO]


class CorrectRequest(BaseModel):
    zh: str
    en: str
    # Optional linkage to a bank item and device for progress tracking
    bankItemId: Optional[str] = None
    deviceId: Optional[str] = None


# ----- LLM Provider -----

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

# Load .env if present (repo root or backend/). Simplifies local dev.
if load_dotenv is not None:
    # try project root
    root_env = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(dotenv_path=root_env)
    # then backend/.env (takes precedence)
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-mini")


def _load_system_prompt() -> str:
    """Load prompt text from a .txt file.
    Order of precedence:
    1) env PROMPT_FILE
    2) backend/prompt.txt
    If missing/unreadable, raise clear error to avoid accidental empty prompts.
    """
    default_path = os.path.join(os.path.dirname(__file__), "prompt.txt")
    path = os.environ.get("PROMPT_FILE", default_path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                raise RuntimeError("prompt_file_empty")
            return content
    except Exception as e:
        raise RuntimeError(f"prompt_file_error: {e}")


SYSTEM_PROMPT = _load_system_prompt()


def _load_deck_prompt() -> str:
    default_path = os.path.join(os.path.dirname(__file__), "prompt_deck.txt")
    path = os.environ.get("DECK_PROMPT_FILE", default_path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                raise RuntimeError("deck_prompt_file_empty")
            return content
    except Exception as e:
        raise RuntimeError(f"deck_prompt_file_error: {e}")


DECK_PROMPT = _load_deck_prompt()

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


def call_openai(zh: str, en: str) -> CorrectResponse:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    user_content = (
        "請批改以下內容並輸出 JSON。\n"
        f"zh: {zh}\n"
        f"en: {en}\n"
    )

    # Preferred: official SDK (no temperature, new models)
    if OpenAI is not None:
        client = OpenAI()
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
            )
        except Exception as e:
            raise RuntimeError(f"openai_sdk_error: {e}")
        content = resp.choices[0].message.content
        try:
            obj = json.loads(content)
        except Exception as e:
            raise RuntimeError(f"invalid_model_json: {e}\ncontent={str(content)[:400]}")
        return _to_response_or_422(obj)

    # Fallback: raw HTTP
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }
    r = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=60)
    if r.status_code // 100 != 2:
        raise RuntimeError(f"openai_error status={r.status_code} body={r.text[:400]}")
    data = r.json()
    content = data["choices"][0]["message"]["content"]
    try:
        obj = json.loads(content)
    except Exception as e:
        raise RuntimeError(f"invalid_model_json: {e}\ncontent={content[:400]}")
    return _to_response_or_422(obj)


# ----- FastAPI -----

app = FastAPI(title="Local Correct Backend", version="0.1.0")


def _to_response_or_422(obj: dict) -> CorrectResponse:
    """Validate that all error types are within the five categories.
    If any are invalid, raise 422 with details; otherwise coerce and return.
    """
    import uuid
    allowed = {"morphological", "syntactic", "lexical", "phonological", "pragmatic"}
    errs = obj.get("errors") or []
    invalid = []
    for idx, e in enumerate(errs):
        t = (e.get("type") or "").strip().lower()
        if t not in allowed:
            invalid.append({"index": idx, "value": t})
        else:
            e["type"] = t
        # Drop any range-like keys entirely (prompt不再提及 range)
        e.pop("originalRange", None)
        e.pop("suggestionRange", None)
        e.pop("correctedRange", None)
        # Always assign server-side UUID to id（不要求模型輸出 id）
        e["id"] = str(uuid.uuid4())
    if invalid:
        raise HTTPException(status_code=422, detail={"invalid_types": invalid, "allowed": sorted(allowed)})
    return CorrectResponse.model_validate(obj)


def _simple_analyze(zh: str, en: str) -> CorrectResponse:
    # Lightweight fallback mirroring backend/server.py rules
    import re, uuid
    corrected = en
    errors: List[ErrorDTO] = []
    def err(span, etype, explain, suggestion=None, before=None, after=None, occurrence=None):
        return ErrorDTO(id=str(uuid.uuid4()), span=span, type=etype, explainZh=explain, suggestion=suggestion, hints=ErrorHintsDTO(before=before, after=after, occurrence=occurrence))
    if re.search(r"\byesterday\b", en, flags=re.I) and re.search(r"\bgo\b", en):
        errors.append(err("go", "morphological", "應使用過去式。", "went", before="I ", after=" to", occurrence=1))
        corrected = re.sub(r"\bgo\b", "went", corrected, count=1)
    if re.search(r"\bshop\b", en, flags=re.I):
        errors.append(err("shop", "lexical", "在此語境更常用 store。", "store", before="the ", after=" "))
        corrected = re.sub(r"\bshop\b", "store", corrected, count=1, flags=re.I)
    if re.search(r"\bfruits\b", en, flags=re.I):
        errors.append(err("fruits", "pragmatic", "一般泛指時常用不可數名詞 fruit。", "fruit", before="some "))
        corrected = re.sub(r"\bfruits\b", "fruit", corrected, count=1, flags=re.I)
    score = max(60, 100 - 5 * len(errors))
    return CorrectResponse(corrected=corrected, score=score, errors=errors)


@app.post("/correct", response_model=CorrectResponse)
def correct(req: CorrectRequest):
    # Optional offline switch: bypass OpenAI and use simple analyzer
    if os.environ.get("FORCE_SIMPLE_CORRECT") in ("1", "true", "yes"):
        resp = _simple_analyze(req.zh, req.en)
        try:
            _update_progress_after_correct(req.bankItemId, req.deviceId, resp.score)
        except Exception:
            pass
        return resp
    try:
        resp = call_openai(req.zh, req.en)
    except HTTPException as he:
        # Propagate 4xx like 422 invalid types directly
        raise he
    except Exception as e:
        # Graceful handling: for 429/insufficient_quota optionally fallback to simple rules
        msg = str(e)
        allow_fallback = os.environ.get("ALLOW_FALLBACK_ON_FAILURE") in ("1", "true", "yes")
        if "status=429" in msg and allow_fallback:
            resp = _simple_analyze(req.zh, req.en)
        # Propagate with appropriate status
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
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"status": "no_key"}
    try:
        r = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if r.status_code // 100 == 2:
            return {"status": "ok", "provider": "openai", "model": OPENAI_MODEL}
        return {"status": "auth_error", "code": r.status_code}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# -----------------------------
# Bank (題庫)
# -----------------------------

class BankHint(BaseModel):
    category: str  # grammar | structure | collocation | idiom | usage | style | translation | pitfall
    text: str


class BankSuggestion(BaseModel):
    text: str
    category: Optional[str] = None


class BankItem(BaseModel):
    id: str
    zh: str
    hints: List[BankHint] = []
    suggestions: List[BankSuggestion] = []
    tags: List[str] = []
    difficulty: int = Field(ge=1, le=5)


_BANK_DATA: List[BankItem] = []


# -----------------------------
# Progress tracking (per device)
# -----------------------------

class ProgressRecord(BaseModel):
    completed: bool = False
    attempts: int = 0
    lastScore: Optional[int] = None
    updatedAt: float = Field(default_factory=lambda: time.time())


# in-memory: deviceId -> itemId -> ProgressRecord
_PROGRESS: Dict[str, Dict[str, ProgressRecord]] = {}

_PROGRESS_FILE = os.path.join(os.path.dirname(__file__), "progress.json")


def _load_progress() -> None:
    global _PROGRESS
    if not os.path.exists(_PROGRESS_FILE):
        _PROGRESS = {}
        return
    try:
        with open(_PROGRESS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        _PROGRESS = {
            dev: {iid: ProgressRecord.model_validate(rec) for iid, rec in recs.items()}
            for dev, recs in (raw or {}).items()
        }
    except Exception:
        _PROGRESS = {}


def _save_progress() -> None:
    try:
        payload = {
            dev: {iid: rec.model_dump() for iid, rec in recs.items()}
            for dev, recs in _PROGRESS.items()
        }
        with open(_PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _update_progress_after_correct(bank_item_id: Optional[str], device_id: Optional[str], score: Optional[int]):
    if not bank_item_id:
        return
    dev = device_id or "default"
    recs = _PROGRESS.setdefault(dev, {})
    rec = recs.get(bank_item_id) or ProgressRecord()
    rec.attempts += 1
    rec.lastScore = score
    # Mark as completed; optional min score threshold
    try:
        min_score = int(os.environ.get("BANK_COMPLETE_MIN_SCORE", "0"))
    except Exception:
        min_score = 0
    if score is None or score >= min_score:
        rec.completed = True
    rec.updatedAt = time.time()
    recs[bank_item_id] = rec
    _save_progress()


def _load_bank() -> None:
    global _BANK_DATA
    path = os.path.join(os.path.dirname(__file__), "bank.json")
    if not os.path.exists(path):
        _BANK_DATA = []
        return
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    _BANK_DATA = [BankItem.model_validate(it) for it in raw]


def _save_bank() -> None:
    path = os.path.join(os.path.dirname(__file__), "bank.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump([it.model_dump() for it in _BANK_DATA], f, ensure_ascii=False, indent=2)


@app.on_event("startup")
def _startup_load_bank():
    _load_bank()
    _load_progress()


class BankItemWithStatus(BankItem):
    completed: bool = False


@app.get("/bank/items", response_model=List[BankItemWithStatus])
def bank_items(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    difficulty: Optional[int] = Query(None, ge=1, le=5),
    tag: Optional[str] = None,
    deviceId: Optional[str] = Query(None, alias="deviceId"),
):
    data: List[BankItemWithStatus] = []
    dev = deviceId or "default"
    recs = _PROGRESS.get(dev, {})
    src = _BANK_DATA
    if difficulty is not None:
        src = [x for x in src if x.difficulty == difficulty]
    if tag:
        src = [x for x in src if tag in (x.tags or [])]
    for it in src[offset : offset + limit]:
        completed = bool(recs.get(it.id).completed) if it.id in recs else False
        data.append(BankItemWithStatus(**it.model_dump(), completed=completed))
    return data


@app.get("/bank/random", response_model=BankItemWithStatus)
def bank_random(
    difficulty: Optional[int] = Query(None, ge=1, le=5),
    tag: Optional[str] = None,
    deviceId: Optional[str] = None,
    skipCompleted: bool = Query(False),
):
    import random

    dev = deviceId or "default"
    recs = _PROGRESS.get(dev, {})
    data: List[BankItem] = _BANK_DATA
    if difficulty is not None:
        data = [x for x in data if x.difficulty == difficulty]
    if tag:
        data = [x for x in data if tag in (x.tags or [])]
    if skipCompleted:
        data = [x for x in data if not recs.get(x.id, ProgressRecord()).completed]
    if not data:
        raise HTTPException(status_code=404, detail="no_item")
    pick = random.choice(data)
    completed = bool(recs.get(pick.id).completed) if pick.id in recs else False
    return BankItemWithStatus(**pick.model_dump(), completed=completed)


class BankBook(BaseModel):
    name: str
    count: int
    difficultyMin: int
    difficultyMax: int


@app.get("/bank/books", response_model=List[BankBook])
def bank_books():
    # Aggregate by tag as "book" name. If no tag, put under "default".
    buckets: dict[str, List[BankItem]] = {}
    for it in _BANK_DATA:
        tags = it.tags or ["default"]
        for t in tags:
            buckets.setdefault(t, []).append(it)

    books: List[BankBook] = []
    for name, items in buckets.items():
        counts = len(items)
        dmin = min(i.difficulty for i in items) if items else 1
        dmax = max(i.difficulty for i in items) if items else 1
        books.append(BankBook(name=name, count=counts, difficultyMin=dmin, difficultyMax=dmax))
    # stable order
    books.sort(key=lambda b: b.name)
    return books


class ImportRequest(BaseModel):
    text: str
    defaultTag: Optional[str] = None
    replace: bool = False


class ImportResponse(BaseModel):
    imported: int
    errors: List[str] = []


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


@app.post("/bank/import", response_model=ImportResponse)
def bank_import(req: ImportRequest):
    items, errs = _parse_bank_text(req.text, req.defaultTag)
    if req.replace:
        _BANK_DATA.clear()
    _BANK_DATA.extend(items)
    try:
        _save_bank()
    except Exception as e:
        errs.append(f"save_error: {e}")
    return ImportResponse(imported=len(items), errors=errs)


# ----- Progress endpoints -----

class ProgressMarkRequest(BaseModel):
    itemId: str
    deviceId: Optional[str] = None
    score: Optional[int] = None
    completed: bool = True


class ProgressRecordOut(ProgressRecord):
    itemId: str


class ProgressSummary(BaseModel):
    deviceId: str
    completedIds: List[str]
    records: List[ProgressRecordOut]


@app.post("/bank/progress/complete", response_model=ProgressRecordOut)
def progress_complete(req: ProgressMarkRequest):
    dev = req.deviceId or "default"
    recs = _PROGRESS.setdefault(dev, {})
    rec = recs.get(req.itemId) or ProgressRecord()
    rec.completed = bool(req.completed)
    rec.attempts += 1
    if req.score is not None:
        rec.lastScore = req.score
    rec.updatedAt = time.time()
    recs[req.itemId] = rec
    _save_progress()
    return ProgressRecordOut(itemId=req.itemId, **rec.model_dump())


@app.get("/bank/progress", response_model=ProgressSummary)
def progress_get(deviceId: Optional[str] = None):
    dev = deviceId or "default"
    recs = _PROGRESS.get(dev, {})
    completed_ids = [iid for iid, r in recs.items() if r.completed]
    records = [ProgressRecordOut(itemId=iid, **r.model_dump()) for iid, r in recs.items()]
    return ProgressSummary(deviceId=dev, completedIds=completed_ids, records=records)


# -----------------------------
# Make Deck (flashcards)
# -----------------------------

class DeckMakeItem(BaseModel):
    zh: Optional[str] = None
    en: Optional[str] = None
    corrected: Optional[str] = None
    span: Optional[str] = None
    suggestion: Optional[str] = None
    explainZh: Optional[str] = None
    type: Optional[str] = None


class DeckMakeRequest(BaseModel):
    name: Optional[str] = "未命名"
    items: List[DeckMakeItem]


class DeckCard(BaseModel):
    # 四欄位卡片：正面中文、正面備註（可選）、背面英文、背面備註（可選）
    front: str
    frontNote: Optional[str] = None
    back: str
    backNote: Optional[str] = None


class DeckMakeResponse(BaseModel):
    name: str
    cards: List[DeckCard]


def call_openai_make_deck(req: DeckMakeRequest) -> DeckMakeResponse:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
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

    debug_info: Dict[str, object] = {
        "ts": time.time(),
        "model": OPENAI_MODEL,
        "system_prompt": DECK_PROMPT,
        "user_content": user_content,
        "items_in": len(items),
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": OPENAI_MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": DECK_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }
    r = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=60)
    if r.status_code // 100 != 2:
        debug_info.update({
            "http_error": r.status_code,
            "http_body_head": r.text[:800],
        })
        _deck_debug_write(debug_info)
        raise RuntimeError(f"openai_error status={r.status_code} body={r.text[:400]}")
    data = r.json()
    content = data["choices"][0]["message"]["content"]
    debug_info["response_raw"] = content
    try:
        obj = json.loads(content)
    except Exception as e:
        debug_info.update({"json_error": str(e)})
        _deck_debug_write(debug_info)
        raise RuntimeError(f"invalid_model_json: {e}\ncontent={content[:400]}")
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
        return call_openai_make_deck(req)
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

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    # Run by passing the app object directly to avoid import path issues
    uvicorn.run(app, host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    dev()
