from __future__ import annotations

import json
import os
import uuid
from typing import Dict, List, Optional

from app.schemas import BankHint, BankItem, BankSuggestion
from app.core.settings import get_settings
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
        "id": "daily-conversations",
        "name": "Daily Conversations",
        "summary": "常用寒暄與日常互動句型。",
        "coverImage": "https://picsum.photos/seed/daily-conversations/720/400",
        "items": [
            {"id": "conv-greet", "zh": "跟陌生人打招呼", "hints": [], "suggestions": [], "tags": ["daily"], "difficulty": 1},
            {"id": "conv-order", "zh": "點餐時的常見句型", "hints": [], "suggestions": [], "tags": ["daily"], "difficulty": 2},
        ],
    },
    {
        "id": "academic-writing",
        "name": "Academic Writing",
        "summary": "研究論文常見段落組織與動詞用法。",
        "coverImage": "https://picsum.photos/seed/academic-writing/720/400",
        "items": [
            {"id": "acad-intro", "zh": "撰寫研究引言", "hints": [], "suggestions": [], "tags": ["academic"], "difficulty": 3},
            {"id": "acad-method", "zh": "描述研究方法", "hints": [], "suggestions": [], "tags": ["academic"], "difficulty": 3},
        ],
    },
]

CLOUD_COURSES_SEED = [
    {
        "id": "starter-course",
        "title": "Starter Course",
        "summary": "預設示範課程，帶你熟悉題庫格式。",
        "coverImage": "https://picsum.photos/seed/starter-course/960/540",
        "tags": ["starter"],
        "books": [
            {
                "id": "daily-conversations",
                "title": "Daily Conversations",
                "summary": "暖身日常對話。",
                "coverImage": "https://picsum.photos/seed/daily-conversations/720/400",
                "tags": ["daily"],
                "difficulty": 1,
                "source": {"type": "book", "id": "daily-conversations"},
            },
            {
                "id": "academic-writing",
                "title": "Academic Writing",
                "summary": "學術寫作核心句型。",
                "coverImage": "https://picsum.photos/seed/academic-writing/720/400",
                "tags": ["academic"],
                "difficulty": 3,
                "source": {"type": "book", "id": "academic-writing"},
            },
        ],
    }
]


class ContentStore:
    """Load curated decks/courses/books from JSON files if present; otherwise, fallback to seeds.

    Layout (default base from $CONTENT_DIR or backend/data):
      data/decks/<id>.json    -> { id, name, cards:[{ id?, front, back, frontNote?, backNote? }] }
      data/books/<id>.json    -> { id, name, items:[{ id, zh, hints:[], suggestions:[], tags?, difficulty? }] }
      data/courses/<id>.json  -> { id, title, summary?, coverImage?, tags?, books:[{ id?, title?, summary?, coverImage?, tags?, difficulty?, source?:{id}, items?:[...] }] }
    """

    def __init__(self) -> None:
        settings = get_settings()
        base_cfg = settings.CONTENT_DIR
        if os.path.isabs(base_cfg):
            self.base = base_cfg
        else:
            here = os.path.dirname(__file__)
            backend_dir = os.path.abspath(os.path.join(here, ".."))
            self.base = os.path.abspath(os.path.join(backend_dir, base_cfg))
        self._decks_by_id: Dict[str, dict] = {}
        self._books_by_id: Dict[str, dict] = {}
        self._courses_by_id: Dict[str, dict] = {}
        self._loaded = False

    def _json_files(self, sub: str) -> List[str]:
        path = os.path.join(self.base, sub)
        try:
            return [os.path.join(path, f) for f in os.listdir(path) if f.endswith(".json")]
        except FileNotFoundError:
            return []

    def _read(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _ensure_card_ids(self, deck: dict) -> dict:
        deck_id = deck.get("id") or deck.get("name") or "deck"
        cards = []
        for idx, card in enumerate(deck.get("cards", [])):
            cid = card.get("id") or str(uuid.uuid5(uuid.NAMESPACE_URL, f"deck:{deck_id}:{idx}"))
            cards.append(
                {
                    "id": cid,
                    "front": card.get("front", ""),
                    "back": card.get("back", ""),
                    **({"frontNote": card["frontNote"]} if card.get("frontNote") is not None else {}),
                    **({"backNote": card["backNote"]} if card.get("backNote") is not None else {}),
                }
            )
        clone = dict(deck)
        clone["cards"] = cards
        return clone

    def _normalize_bank_items(self, raw_items: List[dict]) -> List[dict]:
        items: List[dict] = []
        for entry in raw_items:
            try:
                hint_objs = [BankHint(**hint) for hint in entry.get("hints", [])]
                sugg_objs = [BankSuggestion(**sugg) for sugg in entry.get("suggestions", [])]
                bank_item = BankItem(
                    id=entry.get("id") or str(uuid.uuid4()),
                    zh=entry.get("zh", ""),
                    hints=hint_objs,
                    suggestions=sugg_objs,
                    tags=entry.get("tags", []),
                    difficulty=int(entry.get("difficulty", 1)),
                )
                items.append(bank_item.model_dump())
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("cloud_bank_item_invalid", extra={"error": str(exc), "entry": entry})
        return items

    def load(self) -> None:
        if self._loaded:
            return
        self._load_decks(self._json_files("decks"))
        self._load_books(self._json_files("books"))
        self._load_courses(self._json_files("courses"))
        self._loaded = True

    # ----- Loaders -----------------------------------------------------
    def _load_decks(self, deck_files: List[str]) -> None:
        decks: Dict[str, dict] = {}
        for fp in deck_files:
            try:
                deck = self._read(fp)
                deck_id = deck.get("id") or os.path.splitext(os.path.basename(fp))[0]
                deck["id"] = deck_id
                if not deck.get("name"):
                    deck["name"] = deck_id
                decks[deck_id] = self._ensure_card_ids(deck)
            except Exception as exc:
                logger.warning("cloud_deck_load_error", extra={"path": fp, "error": str(exc)})
        if not decks:
            decks = {seed["id"]: self._ensure_card_ids(seed) for seed in CLOUD_DECKS_SEED}
        self._decks_by_id = decks

    def _load_books(self, book_files: List[str]) -> None:
        books: Dict[str, dict] = {}
        for fp in book_files:
            try:
                raw = self._read(fp)
                book_id = raw.get("id") or os.path.splitext(os.path.basename(fp))[0]
                name = raw.get("name") or book_id
                items = self._normalize_bank_items(raw.get("items", []))
                tags = sorted({tag for it in items for tag in it.get("tags", []) if tag})
                books[book_id] = {
                    "id": book_id,
                    "name": name,
                    "summary": raw.get("summary"),
                    "coverImage": raw.get("coverImage"),
                    "tags": tags or raw.get("tags", []),
                    "items": items,
                }
            except Exception as exc:
                logger.warning("cloud_book_load_error", extra={"path": fp, "error": str(exc)})
        if not books:
            for seed in CLOUD_BOOKS_SEED:
                items = self._normalize_bank_items(seed.get("items", []))
                tags = sorted({tag for it in items for tag in it.get("tags", []) if tag})
                books[seed["id"]] = {
                    "id": seed["id"],
                    "name": seed["name"],
                    "summary": seed.get("summary"),
                    "coverImage": seed.get("coverImage"),
                    "tags": tags or seed.get("tags", []),
                    "items": items,
                }
        self._books_by_id = books

    def _load_courses(self, course_files: List[str]) -> None:
        courses: Dict[str, dict] = {}
        for fp in course_files:
            try:
                raw = self._read(fp)
                course_id = raw.get("id") or os.path.splitext(os.path.basename(fp))[0]
                title = raw.get("title") or raw.get("name") or course_id
                summary = raw.get("summary")
                cover = raw.get("coverImage")
                tags = raw.get("tags", [])
                books = self._build_course_books(course_id, raw.get("books", []))
                courses[course_id] = {
                    "id": course_id,
                    "title": title,
                    "summary": summary,
                    "coverImage": cover,
                    "tags": tags,
                    "books": books,
                }
            except Exception as exc:
                logger.warning("cloud_course_load_error", extra={"path": fp, "error": str(exc)})
        if not courses:
            for seed in CLOUD_COURSES_SEED:
                books = self._build_course_books(seed["id"], seed.get("books", []))
                courses[seed["id"]] = {
                    "id": seed["id"],
                    "title": seed["title"],
                    "summary": seed.get("summary"),
                    "coverImage": seed.get("coverImage"),
                    "tags": seed.get("tags", []),
                    "books": books,
                }
        if not courses and self._books_by_id:
            courses["default"] = {
                "id": "default",
                "title": "Cloud Library",
                "summary": "包含所有雲端題庫的預設課程。",
                "coverImage": None,
                "tags": [],
                "books": [self._book_to_course_entry(book) for book in self._books_by_id.values()],
            }
        self._courses_by_id = courses

    def _book_to_course_entry(self, book: dict, overrides: Optional[dict] = None) -> dict:
        data = overrides or {}
        title = data.get("title") or book.get("name") or book.get("id")
        summary = data.get("summary") or book.get("summary")
        cover = data.get("coverImage") or book.get("coverImage")
        tags = data.get("tags") or book.get("tags", [])
        difficulty = data.get("difficulty")
        if data.get("items") is not None:
            clone_items = [dict(item) for item in data.get("items", [])]
        else:
            clone_items = [dict(item) for item in book.get("items", [])]
        return {
            "id": data.get("id") or book.get("id"),
            "title": title,
            "summary": summary,
            "coverImage": cover,
            "tags": tags,
            "difficulty": difficulty,
            "items": clone_items,
            "itemCount": len(clone_items),
        }

    def _build_course_books(self, course_id: str, raw_books: List[dict]) -> List[dict]:
        books: List[dict] = []
        seen: set[str] = set()
        for entry in raw_books:
            try:
                resolved = self._resolve_course_book(entry)
            except Exception as exc:
                logger.warning(
                    "cloud_course_book_error",
                    extra={"course": course_id, "entry": entry, "error": str(exc)},
                )
                continue
            if not resolved:
                logger.warning(
                    "cloud_course_book_missing",
                    extra={"course": course_id, "entry": entry},
                )
                continue
            book_id = resolved.get("id")
            if book_id in seen:
                continue
            seen.add(book_id)
            books.append(resolved)
        return books

    def _resolve_course_book(self, entry: dict) -> Optional[dict]:
        source_info = entry.get("source") or {}
        source_id = source_info.get("id") or entry.get("sourceId") or entry.get("id")
        base = self._books_by_id.get(source_id) if source_id else None
        if entry.get("items"):
            items = self._normalize_bank_items(entry.get("items", []))
        elif base is not None:
            items = [dict(item) for item in base.get("items", [])]
        else:
            return None
        overrides = {
            "id": entry.get("id"),
            "title": entry.get("title"),
            "summary": entry.get("summary"),
            "coverImage": entry.get("coverImage"),
            "tags": entry.get("tags"),
            "difficulty": entry.get("difficulty"),
        }
        if base is None:
            # allow inline-only definitions
            temp_book = {
                "id": overrides.get("id") or str(uuid.uuid4()),
                "name": overrides.get("title") or overrides.get("id") or "book",
                "summary": overrides.get("summary"),
                "coverImage": overrides.get("coverImage"),
                "tags": overrides.get("tags", []),
                "items": items,
            }
            return self._book_to_course_entry(temp_book, overrides)
        return self._book_to_course_entry(base, {**overrides, "items": items})

    # ----- Public accessors -------------------------------------------
    def list_decks(self) -> List[dict]:
        self.load()
        return list(self._decks_by_id.values())

    def get_deck(self, deck_id: str) -> Optional[dict]:
        self.load()
        deck = self._decks_by_id.get(deck_id)
        return self._ensure_card_ids(deck) if deck else None

    def list_course_summaries(self) -> List[dict]:
        self.load()
        return [self._course_summary(course) for course in self._courses_by_id.values()]

    def get_course(self, course_id: str) -> Optional[dict]:
        self.load()
        course = self._courses_by_id.get(course_id)
        if not course:
            return None
        return {
            **self._course_summary(course),
            "books": [self._book_detail(book) for book in course.get("books", [])],
        }

    def get_course_book(self, course_id: str, book_id: str) -> Optional[dict]:
        course = self.get_course(course_id)
        if not course:
            return None
        for book in course.get("books", []):
            if book.get("id") == book_id:
                return book
        return None

    def search(self, query: str) -> dict:
        self.load()
        term = (query or "").strip().lower()
        if not term:
            return {"courses": [], "books": []}
        course_hits: List[dict] = []
        book_hits: List[tuple[str, dict]] = []
        seen_courses: set[str] = set()
        seen_books: set[tuple[str, str]] = set()
        for course in self._courses_by_id.values():
            haystack = " ".join(
                filter(
                    None,
                    [
                        course.get("title"),
                        course.get("summary"),
                        " ".join(course.get("tags", [])),
                    ],
                )
            ).lower()
            if term in haystack and course["id"] not in seen_courses:
                seen_courses.add(course["id"])
                course_hits.append(self._course_summary(course))
            for book in course.get("books", []):
                book_key = (course["id"], book.get("id"))
                if book_key in seen_books:
                    continue
                book_text = " ".join(
                    filter(
                        None,
                        [
                            book.get("title"),
                            book.get("summary"),
                            " ".join(book.get("tags", [])),
                        ],
                    )
                ).lower()
                matched = term in book_text
                if not matched:
                    for item in book.get("items", []):
                        if term in item.get("zh", "").lower():
                            matched = True
                            break
                if matched:
                    seen_books.add(book_key)
                    book_hits.append((course["id"], self._book_summary(book)))
        return {
            "courses": course_hits,
            "books": [
                {
                    **book_summary,
                    "courseId": course_id,
                }
                for course_id, book_summary in book_hits
            ],
        }

    # ----- Helpers ----------------------------------------------------
    def _course_summary(self, course: dict) -> dict:
        books = course.get("books", [])
        return {
            "id": course.get("id"),
            "title": course.get("title"),
            "summary": course.get("summary"),
            "coverImage": course.get("coverImage"),
            "tags": course.get("tags", []),
            "bookCount": len(books),
        }

    def _book_summary(self, book: dict) -> dict:
        return {
            "id": book.get("id"),
            "title": book.get("title"),
            "summary": book.get("summary"),
            "coverImage": book.get("coverImage"),
            "tags": book.get("tags", []),
            "difficulty": book.get("difficulty"),
            "itemCount": book.get("itemCount") or len(book.get("items", [])),
        }

    def _book_detail(self, book: dict) -> dict:
        return {
            **self._book_summary(book),
            "items": [dict(item) for item in book.get("items", [])],
        }
