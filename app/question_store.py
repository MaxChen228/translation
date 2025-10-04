from __future__ import annotations

import datetime as dt
import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

try:
    import psycopg2
    from psycopg2.extras import Json
except ImportError:  # pragma: no cover - optional dependency
    psycopg2 = None  # type: ignore[assignment]
    Json = None  # type: ignore[assignment]


@dataclass
class QuestionRecord:
    id: str
    question_date: dt.date
    zh: str
    reference_en: str
    difficulty: int
    tags: Sequence[str]
    hints: Sequence[dict]
    suggestions: Sequence[dict]
    raw: dict
    model: str
    prompt_hash: str
    created_at: dt.datetime

    @classmethod
    def from_payload(
        cls,
        *,
        question_date: dt.date,
        item: dict,
        reference_en: str,
        model: str,
        prompt_hash: str,
    ) -> "QuestionRecord":
        identifier = item.get("id") or str(uuid.uuid4())
        created_at = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
        return cls(
            id=identifier,
            question_date=question_date,
            zh=item.get("zh", ""),
            reference_en=reference_en,
            difficulty=int(item.get("difficulty", 1)),
            tags=list(item.get("tags", [])),
            hints=list(item.get("hints", [])),
            suggestions=list(item.get("suggestions", [])),
            raw=item,
            model=model,
            prompt_hash=prompt_hash,
            created_at=created_at,
        )


@dataclass
class SaveSummary:
    inserted: int = 0
    duplicates: int = 0


class QuestionStore:
    def __init__(self, *, db_url: Optional[str], db_path: str) -> None:
        self._backend = "postgres" if db_url else "sqlite"
        if self._backend == "postgres":
            if not db_url:
                raise ValueError("db_url required for postgres backend")
            if psycopg2 is None:
                raise RuntimeError("psycopg2 is required for Postgres backend")
            self._conn = psycopg2.connect(db_url)
            self._conn.autocommit = True
            self._init_postgres()
        else:
            root = Path(__file__).resolve().parent.parent
            path = Path(db_path)
            if not path.is_absolute():
                path = (root / db_path).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(path), detect_types=sqlite3.PARSE_DECLTYPES)
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
            self._init_sqlite()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    # --- Schema ---
    def _init_sqlite(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS generated_questions (
            id TEXT PRIMARY KEY,
            question_date TEXT NOT NULL,
            zh TEXT NOT NULL,
            reference_en TEXT NOT NULL,
            difficulty INTEGER NOT NULL,
            tags TEXT NOT NULL,
            hints TEXT NOT NULL,
            suggestions TEXT NOT NULL,
            raw TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(question_date, zh)
        );
        """
        self._conn.execute(ddl)
        self._conn.commit()

    def _init_postgres(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS generated_questions (
            id UUID PRIMARY KEY,
            question_date DATE NOT NULL,
            zh TEXT NOT NULL,
            reference_en TEXT NOT NULL,
            difficulty INTEGER NOT NULL,
            tags JSONB NOT NULL,
            hints JSONB NOT NULL,
            suggestions JSONB NOT NULL,
            raw JSONB NOT NULL,
            model TEXT NOT NULL,
            prompt_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(question_date, zh)
        );
        """
        with self._conn.cursor() as cur:
            cur.execute(ddl)

    # --- Persistence ---
    def save_many(self, records: Iterable[QuestionRecord]) -> SaveSummary:
        inserted = 0
        duplicates = 0
        if self._backend == "postgres":
            with self._conn.cursor() as cur:
                for rec in records:
                    cur.execute(
                        """
                        INSERT INTO generated_questions
                        (id, question_date, zh, reference_en, difficulty, tags, hints, suggestions, raw, model, prompt_hash, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (question_date, zh) DO NOTHING
                        """,
                        (
                            rec.id,
                            rec.question_date,
                            rec.zh,
                            rec.reference_en,
                            rec.difficulty,
                            Json(list(rec.tags)),
                            Json(list(rec.hints)),
                            Json(list(rec.suggestions)),
                            Json(rec.raw),
                            rec.model,
                            rec.prompt_hash,
                            rec.created_at,
                        ),
                    )
                    if cur.rowcount == 0:
                        duplicates += 1
                    else:
                        inserted += 1
        else:
            sql = """
            INSERT INTO generated_questions
            (id, question_date, zh, reference_en, difficulty, tags, hints, suggestions, raw, model, prompt_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(question_date, zh) DO NOTHING
            """
            cursor = self._conn.cursor()
            for rec in records:
                tags_json = json.dumps(list(rec.tags), ensure_ascii=False)
                hints_json = json.dumps(list(rec.hints), ensure_ascii=False)
                sugg_json = json.dumps(list(rec.suggestions), ensure_ascii=False)
                raw_json = json.dumps(rec.raw, ensure_ascii=False)
                cursor.execute(
                    sql,
                    (
                        rec.id,
                        rec.question_date.isoformat(),
                        rec.zh,
                        rec.reference_en,
                        rec.difficulty,
                        tags_json,
                        hints_json,
                        sugg_json,
                        raw_json,
                        rec.model,
                        rec.prompt_hash,
                        rec.created_at.isoformat(),
                    ),
                )
                if cursor.rowcount == 0:
                    duplicates += 1
                else:
                    inserted += 1
            self._conn.commit()
        return SaveSummary(inserted=inserted, duplicates=duplicates)


__all__ = ["QuestionStore", "QuestionRecord", "SaveSummary"]
