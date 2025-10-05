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
    psycopg2 = None
    Json = None


@dataclass
class QuestionRecord:
    id: str
    question_date: dt.date
    zh: str
    reference_en: str
    difficulty: int
    tags: Sequence[str]
    hints: Sequence[dict]
    raw: dict
    model: str
    prompt_hash: str
    created_at: dt.datetime
    review_note: Optional[str] = None

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
            raw=item,
            model=model,
            prompt_hash=prompt_hash,
            created_at=created_at,
            review_note=_extract_review_note(item),
        )


@dataclass
class SaveSummary:
    inserted: int = 0
    duplicates: int = 0


def _extract_review_note(item: dict) -> Optional[str]:
    note = item.get("reviewNote") or item.get("suggestion")
    if isinstance(note, str):
        stripped = note.strip()
        if stripped:
            return stripped
    suggestion_items = item.get("suggestions") or []
    if suggestion_items:
        joined = "\n".join(
            str(sugg.get("text", "")).strip()
            for sugg in suggestion_items
            if str(sugg.get("text", "")).strip()
        ).strip()
        return joined or None
    return None


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
        self._init_delivery_tables()

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
            review_note TEXT,
            UNIQUE(question_date, zh)
        );
        """
        self._conn.execute(ddl)
        self._conn.commit()
        self._ensure_sqlite_column("generated_questions", "review_note", "TEXT")

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
            raw JSONB NOT NULL,
            model TEXT NOT NULL,
            prompt_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            review_note TEXT,
            UNIQUE(question_date, zh)
        );
        """
        with self._conn.cursor() as cur:
            cur.execute(ddl)
            cur.execute(
                """
                ALTER TABLE generated_questions
                ADD COLUMN IF NOT EXISTS review_note TEXT
                """
            )

    def _ensure_sqlite_column(self, table: str, column: str, definition: str) -> None:
        cursor = self._conn.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cursor.fetchall()}
        if column not in existing:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            self._conn.commit()

    def _init_delivery_tables(self) -> None:
        if self._backend == "postgres":
            ddl = """
            CREATE TABLE IF NOT EXISTS generated_question_deliveries (
                id SERIAL PRIMARY KEY,
                question_id UUID NOT NULL REFERENCES generated_questions(id) ON DELETE CASCADE,
                device_id TEXT NOT NULL,
                delivered_date DATE NOT NULL,
                delivered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(question_id, device_id)
            );
            """
            with self._conn.cursor() as cur:
                cur.execute(ddl)
        else:
            ddl = """
            CREATE TABLE IF NOT EXISTS generated_question_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                delivered_date TEXT NOT NULL,
                delivered_at TEXT NOT NULL,
                UNIQUE(question_id, device_id)
            );
            """
            self._conn.execute(ddl)
            self._conn.commit()

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
                        (id, question_date, zh, reference_en, difficulty, tags, hints, suggestions, raw, review_note, model, prompt_hash, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                            Json([]),
                            Json(rec.raw),
                            rec.review_note,
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
            (id, question_date, zh, reference_en, difficulty, tags, hints, suggestions, raw, review_note, model, prompt_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(question_date, zh) DO NOTHING
            """
            cursor = self._conn.cursor()
            for rec in records:
                tags_json = json.dumps(list(rec.tags), ensure_ascii=False)
                hints_json = json.dumps(list(rec.hints), ensure_ascii=False)
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
                        json.dumps([], ensure_ascii=False),
                        raw_json,
                        rec.review_note,
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

    def reserve_questions_for_delivery(
        self,
        *,
        question_date: dt.date,
        count: int,
        device_id: str,
    ) -> list[QuestionRecord]:
        if count <= 0:
            return []

        if self._backend == "postgres":
            query = (
                "SELECT id, question_date, zh, reference_en, difficulty, tags, hints, suggestions, raw, review_note, model, prompt_hash, created_at "
                "FROM generated_questions "
                "WHERE question_date = %s "
                "AND id NOT IN (SELECT question_id FROM generated_question_deliveries WHERE device_id = %s) "
                "ORDER BY created_at ASC LIMIT %s"
            )
            with self._conn.cursor() as cur:
                cur.execute(query, (question_date, device_id, count))
                rows = cur.fetchall()
                records = [self._row_to_record(row) for row in rows]
                if records:
                    delivered_at = dt.datetime.utcnow()
                    insert_sql = (
                        "INSERT INTO generated_question_deliveries (question_id, device_id, delivered_date, delivered_at) "
                        "VALUES (%s, %s, %s, %s) ON CONFLICT (question_id, device_id) DO NOTHING"
                    )
                    payload = [
                        (rec.id, device_id, question_date, delivered_at)
                        for rec in records
                    ]
                    cur.executemany(insert_sql, payload)
            return records

        query = (
            "SELECT id, question_date, zh, reference_en, difficulty, tags, hints, suggestions, raw, review_note, model, prompt_hash, created_at "
            "FROM generated_questions "
            "WHERE question_date = ? "
            "AND id NOT IN (SELECT question_id FROM generated_question_deliveries WHERE device_id = ?) "
            "ORDER BY datetime(created_at) ASC LIMIT ?"
        )
        cursor = self._conn.cursor()
        cursor.execute(query, (question_date.isoformat(), device_id, count))
        rows = cursor.fetchall()
        records = [self._row_to_record(row) for row in rows]
        if records:
            delivered_at_dt = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
            delivered_at_str = delivered_at_dt.isoformat()
            insert_sql = (
                "INSERT OR IGNORE INTO generated_question_deliveries (question_id, device_id, delivered_date, delivered_at) "
                "VALUES (?, ?, ?, ?)"
            )
            payload_sqlite: list[tuple[str, str, str, str]] = [
                (rec.id, device_id, question_date.isoformat(), delivered_at_str)
                for rec in records
            ]
            cursor.executemany(insert_sql, payload_sqlite)
            self._conn.commit()
        return records

    def remaining_questions_for_date(self, *, question_date: dt.date, device_id: str) -> int:
        if self._backend == "postgres":
            query = (
                "SELECT COUNT(*) FROM generated_questions "
                "WHERE question_date = %s "
                "AND id NOT IN (SELECT question_id FROM generated_question_deliveries WHERE device_id = %s)"
            )
            with self._conn.cursor() as cur:
                cur.execute(query, (question_date, device_id))
                row = cur.fetchone()
                return int(row[0]) if row else 0
        query = (
            "SELECT COUNT(*) FROM generated_questions "
            "WHERE question_date = ? "
            "AND id NOT IN (SELECT question_id FROM generated_question_deliveries WHERE device_id = ?)"
        )
        cursor = self._conn.cursor()
        cursor.execute(query, (question_date.isoformat(), device_id))
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def reset_deliveries_for_device(self, *, question_date: dt.date, device_id: str) -> None:
        if self._backend == "postgres":
            query = "DELETE FROM generated_question_deliveries WHERE device_id = %s AND delivered_date = %s"
            with self._conn.cursor() as cur:
                cur.execute(query, (device_id, question_date))
            self._conn.commit()
            return

        query = "DELETE FROM generated_question_deliveries WHERE device_id = ? AND delivered_date = ?"
        cursor = self._conn.cursor()
        cursor.execute(query, (device_id, question_date.isoformat()))
        self._conn.commit()

    def recent_summary(self, limit: int = 7) -> list[dict]:
        limit = max(1, limit)
        if self._backend == "postgres":
            query = (
                "SELECT g.question_date, COUNT(*) AS question_count, "
                "COUNT(DISTINCT d.device_id) AS delivered_devices "
                "FROM generated_questions AS g "
                "LEFT JOIN generated_question_deliveries AS d ON g.id = d.question_id "
                "GROUP BY g.question_date "
                "ORDER BY g.question_date DESC "
                "LIMIT %s"
            )
            with self._conn.cursor() as cur:
                cur.execute(query, (limit,))
                rows = cur.fetchall()
        else:
            query = (
                "SELECT g.question_date, COUNT(*) AS question_count, "
                "COUNT(DISTINCT d.device_id) AS delivered_devices "
                "FROM generated_questions AS g "
                "LEFT JOIN generated_question_deliveries AS d ON g.id = d.question_id "
                "GROUP BY g.question_date "
                "ORDER BY g.question_date DESC "
                "LIMIT ?"
            )
            cursor = self._conn.cursor()
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()

        summary: list[dict] = []
        for row in rows:
            question_date, question_count, delivered_devices = row
            if isinstance(question_date, str):
                question_date = dt.date.fromisoformat(question_date)
            summary.append(
                {
                    "question_date": question_date,
                    "question_count": int(question_count or 0),
                    "delivered_devices": int(delivered_devices or 0),
                }
            )
        return summary

    def _row_to_record(self, row: tuple) -> QuestionRecord:
        if self._backend == "postgres":
            (
                qid,
                question_date,
                zh,
                reference_en,
                difficulty,
                tags,
                hints,
                suggestions,
                raw,
                review_note,
                model,
                prompt_hash,
                created_at,
            ) = row
        else:
            (
                qid,
                question_date,
                zh,
                reference_en,
                difficulty,
                tags,
                hints,
                suggestions,
                raw,
                review_note,
                model,
                prompt_hash,
                created_at,
            ) = row
            question_date = dt.date.fromisoformat(question_date)
            if isinstance(created_at, str):
                created_at = dt.datetime.fromisoformat(created_at)
            tags = json.loads(tags) if isinstance(tags, str) else tags
            hints = json.loads(hints) if isinstance(hints, str) else hints
            suggestions = json.loads(suggestions) if isinstance(suggestions, str) else suggestions
            raw = json.loads(raw) if isinstance(raw, str) else raw

        if isinstance(tags, str):
            tags = json.loads(tags)
        if isinstance(hints, str):
            hints = json.loads(hints)
        if isinstance(suggestions, str):
            suggestions = json.loads(suggestions)
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(created_at, str):
            created_at = dt.datetime.fromisoformat(created_at)
        if isinstance(review_note, bytes):
            review_note = review_note.decode("utf-8")
        if isinstance(review_note, str) and not review_note.strip():
            review_note = None
        derived_note = review_note or _extract_review_note(raw or {})

        return QuestionRecord(
            id=str(qid),
            question_date=question_date,
            zh=zh,
            reference_en=reference_en,
            difficulty=int(difficulty),
            tags=list(tags) if tags is not None else [],
            hints=list(hints) if hints is not None else [],
            raw=dict(raw) if raw is not None else {},
            model=model,
            prompt_hash=prompt_hash,
            created_at=created_at if isinstance(created_at, dt.datetime) else dt.datetime.fromisoformat(str(created_at)),
            review_note=derived_note,
        )


__all__ = ["QuestionStore", "QuestionRecord", "SaveSummary"]
