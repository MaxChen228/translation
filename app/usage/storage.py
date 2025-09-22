from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterable, List, Optional

from app.core.settings import get_settings
from .models import LLMUsage, LLMUsageSummary

_DB_INSTANCE: Optional["UsageStorage"] = None


class UsageStorage:
    def __init__(self, db_path: str) -> None:
        self.db_path = os.path.abspath(db_path)
        self._ensure_directory()
        self._init_db()

    def _ensure_directory(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    provider TEXT NOT NULL,
                    api_kind TEXT NOT NULL,
                    model TEXT NOT NULL,
                    api_endpoint TEXT NOT NULL,
                    route TEXT,
                    device_id TEXT,
                    inline_parts INTEGER NOT NULL,
                    prompt_chars INTEGER NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    latency_ms REAL NOT NULL,
                    status_code INTEGER,
                    cost_input REAL NOT NULL,
                    cost_output REAL NOT NULL,
                    cost_total REAL NOT NULL,
                    request_payload TEXT NOT NULL,
                    response_payload TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON llm_usage(timestamp DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_device ON llm_usage(device_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_route ON llm_usage(route)")
            self._ensure_columns(conn)
            conn.commit()

    def _ensure_columns(self, conn: sqlite3.Connection) -> None:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(llm_usage)")}
        required = {
            "cost_input": "ALTER TABLE llm_usage ADD COLUMN cost_input REAL NOT NULL DEFAULT 0",
            "cost_output": "ALTER TABLE llm_usage ADD COLUMN cost_output REAL NOT NULL DEFAULT 0",
            "cost_total": "ALTER TABLE llm_usage ADD COLUMN cost_total REAL NOT NULL DEFAULT 0",
            "request_payload": "ALTER TABLE llm_usage ADD COLUMN request_payload TEXT NOT NULL DEFAULT ''",
            "response_payload": "ALTER TABLE llm_usage ADD COLUMN response_payload TEXT NOT NULL DEFAULT ''",
        }
        for name, stmt in required.items():
            if name not in columns:
                conn.execute(stmt)
        conn.commit()

    def record(self, usage: LLMUsage) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_usage (
                    timestamp, provider, api_kind, model, api_endpoint,
                    route, device_id, inline_parts, prompt_chars,
                    input_tokens, output_tokens, total_tokens,
                    latency_ms, status_code, cost_input, cost_output, cost_total,
                    request_payload, response_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usage.timestamp,
                    usage.provider,
                    usage.api_kind,
                    usage.model,
                    usage.api_endpoint,
                    usage.route,
                    usage.device_id,
                    usage.inline_parts,
                    usage.prompt_chars,
                    usage.input_tokens,
                    usage.output_tokens,
                    usage.total_tokens,
                    usage.latency_ms,
                    usage.status_code,
                    usage.cost_input,
                    usage.cost_output,
                    usage.cost_total,
                    usage.request_payload,
                    usage.response_payload,
                ),
            )
            conn.commit()

    def _build_filters(
        self,
        *,
        device_id: Optional[str] = None,
        route: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
    ) -> tuple[str, list]:
        clauses = []
        params: list = []
        if device_id:
            clauses.append("device_id = ?")
            params.append(device_id)
        if route:
            clauses.append("route = ?")
            params.append(route)
        if model:
            clauses.append("model = ?")
            params.append(model)
        if provider:
            clauses.append("provider = ?")
            params.append(provider)
        if since is not None:
            clauses.append("timestamp >= ?")
            params.append(since)
        if until is not None:
            clauses.append("timestamp <= ?")
            params.append(until)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        return where, params

    def query(
        self,
        *,
        device_id: Optional[str] = None,
        route: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[LLMUsage]:
        where, params = self._build_filters(
            device_id=device_id,
            route=route,
            model=model,
            provider=provider,
            since=since,
            until=until,
        )
        sql = (
            "SELECT timestamp, provider, api_kind, model, api_endpoint, route, device_id, inline_parts, "
            "prompt_chars, input_tokens, output_tokens, total_tokens, latency_ms, status_code, "
            "cost_input, cost_output, cost_total, request_payload, response_payload "
            "FROM llm_usage"
            f"{where} ORDER BY timestamp DESC"
        )
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        if offset:
            if limit is None:
                sql += " LIMIT -1 OFFSET ?"
                params.append(offset)
            else:
                sql += " OFFSET ?"
                params.append(offset)
        elif limit is None:
            sql += " LIMIT -1"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [LLMUsage(**dict(row)) for row in rows]

    def summarize(
        self,
        *,
        device_id: Optional[str] = None,
        route: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
    ) -> LLMUsageSummary:
        where, params = self._build_filters(
            device_id=device_id,
            route=route,
            model=model,
            provider=provider,
            since=since,
            until=until,
        )
        sql = (
            "SELECT COUNT(*) as count, "
            "COALESCE(SUM(input_tokens), 0) as total_input_tokens, "
            "COALESCE(SUM(output_tokens), 0) as total_output_tokens, "
            "COALESCE(SUM(total_tokens), 0) as total_tokens, "
            "COALESCE(SUM(prompt_chars), 0) as total_prompt_chars, "
            "COALESCE(AVG(latency_ms), 0) as avg_latency_ms, "
            "COALESCE(SUM(cost_input), 0) as total_input_cost_usd, "
            "COALESCE(SUM(cost_output), 0) as total_output_cost_usd, "
            "COALESCE(SUM(cost_total), 0) as total_cost_usd "
            "FROM llm_usage"
            f"{where}"
        )
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return LLMUsageSummary(**dict(row))

    def reset(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM llm_usage")
            conn.commit()


def get_storage() -> UsageStorage:
    global _DB_INSTANCE
    if _DB_INSTANCE is None:
        settings = get_settings()
        path_value = getattr(settings, "USAGE_DB_PATH", "data/usage.db")
        path = Path(path_value)
        if not path.is_absolute():
            backend_dir = Path(__file__).resolve().parent.parent
            path = backend_dir / path
        _DB_INSTANCE = UsageStorage(str(path))
    return _DB_INSTANCE
