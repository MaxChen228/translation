from __future__ import annotations

import contextlib
import os
import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

from app.core.settings import get_settings

from .models import LLMUsage, LLMUsageSummary

try:  # psycopg2 僅在需要 Postgres 時才會用到
    import psycopg2
    import psycopg2.extras
    from psycopg2.pool import ThreadedConnectionPool
except Exception:  # pragma: no cover - 避免本地未安裝時導致 ImportError
    psycopg2 = None  # type: ignore
    ThreadedConnectionPool = None  # type: ignore


class _BaseStorage:
    def record(self, usage: LLMUsage) -> int:  # pragma: no cover - 介面定義
        raise NotImplementedError

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
    ) -> List[LLMUsage]:  # pragma: no cover
        raise NotImplementedError

    def get(self, usage_id: int) -> Optional[LLMUsage]:  # pragma: no cover
        raise NotImplementedError

    def summarize(
        self,
        *,
        device_id: Optional[str] = None,
        route: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
    ) -> LLMUsageSummary:  # pragma: no cover
        raise NotImplementedError

    def reset(self) -> None:  # pragma: no cover
        raise NotImplementedError


class _SQLiteUsageStorage(_BaseStorage):
    def __init__(self, db_path: str) -> None:
        self.db_path = os.path.abspath(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

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

    def _build_filters(
        self,
        *,
        device_id: Optional[str] = None,
        route: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
    ) -> Tuple[str, list]:
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

    def record(self, usage: LLMUsage) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
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
            return int(cursor.lastrowid)

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
            "SELECT id, timestamp, provider, api_kind, model, api_endpoint, route, device_id, inline_parts, "
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

    def get(self, usage_id: int) -> Optional[LLMUsage]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, timestamp, provider, api_kind, model, api_endpoint, route, device_id, inline_parts, "
                "prompt_chars, input_tokens, output_tokens, total_tokens, latency_ms, status_code, "
                "cost_input, cost_output, cost_total, request_payload, response_payload "
                "FROM llm_usage WHERE id = ?",
                (usage_id,),
            ).fetchone()
        if row is None:
            return None
        return LLMUsage(**dict(row))

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


class _PostgresUsageStorage(_BaseStorage):
    def __init__(self, db_url: str, minconn: int = 1, maxconn: int = 5) -> None:
        if psycopg2 is None or ThreadedConnectionPool is None:  # pragma: no cover
            raise RuntimeError("psycopg2-binary is required for Postgres usage logging.")
        self.db_url = db_url
        self._pool = ThreadedConnectionPool(minconn, maxconn, dsn=db_url)
        self._init_db()

    @contextlib.contextmanager
    def _cursor(self):
        conn = self._pool.getconn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def _init_db(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS llm_usage (
            id BIGSERIAL PRIMARY KEY,
            timestamp DOUBLE PRECISION NOT NULL,
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
            latency_ms DOUBLE PRECISION NOT NULL,
            status_code INTEGER,
            cost_input DOUBLE PRECISION NOT NULL,
            cost_output DOUBLE PRECISION NOT NULL,
            cost_total DOUBLE PRECISION NOT NULL,
            request_payload TEXT NOT NULL,
            response_payload TEXT NOT NULL
        )
        """
        with self._cursor() as cursor:
            cursor.execute(ddl)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON llm_usage (timestamp DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_device ON llm_usage (device_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_route ON llm_usage (route)")
            self._ensure_columns(cursor)

    def _ensure_columns(self, cursor) -> None:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'llm_usage'"
        )
        columns = {row["column_name"] for row in cursor.fetchall()}
        required = {
            "cost_input": "ALTER TABLE llm_usage ADD COLUMN cost_input DOUBLE PRECISION NOT NULL DEFAULT 0",
            "cost_output": "ALTER TABLE llm_usage ADD COLUMN cost_output DOUBLE PRECISION NOT NULL DEFAULT 0",
            "cost_total": "ALTER TABLE llm_usage ADD COLUMN cost_total DOUBLE PRECISION NOT NULL DEFAULT 0",
            "request_payload": "ALTER TABLE llm_usage ADD COLUMN request_payload TEXT NOT NULL DEFAULT ''",
            "response_payload": "ALTER TABLE llm_usage ADD COLUMN response_payload TEXT NOT NULL DEFAULT ''",
        }
        for name, stmt in required.items():
            if name not in columns:
                cursor.execute(stmt)

    def _build_filters(
        self,
        *,
        device_id: Optional[str] = None,
        route: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
    ) -> Tuple[str, list]:
        clauses = []
        params: list = []
        if device_id:
            clauses.append("device_id = %s")
            params.append(device_id)
        if route:
            clauses.append("route = %s")
            params.append(route)
        if model:
            clauses.append("model = %s")
            params.append(model)
        if provider:
            clauses.append("provider = %s")
            params.append(provider)
        if since is not None:
            clauses.append("timestamp >= %s")
            params.append(since)
        if until is not None:
            clauses.append("timestamp <= %s")
            params.append(until)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        return where, params

    def record(self, usage: LLMUsage) -> int:
        sql = (
            """
            INSERT INTO llm_usage (
                timestamp, provider, api_kind, model, api_endpoint,
                route, device_id, inline_parts, prompt_chars,
                input_tokens, output_tokens, total_tokens,
                latency_ms, status_code, cost_input, cost_output, cost_total,
                request_payload, response_payload
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """
        )
        params = (
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
        )
        with self._cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
        return int(row["id"]) if row else -1

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
            "SELECT id, timestamp, provider, api_kind, model, api_endpoint, route, device_id, inline_parts, "
            "prompt_chars, input_tokens, output_tokens, total_tokens, latency_ms, status_code, "
            "cost_input, cost_output, cost_total, request_payload, response_payload "
            "FROM llm_usage"
            f"{where} ORDER BY timestamp DESC"
        )
        if limit is not None:
            sql += " LIMIT %s"
            params.append(limit)
        if offset:
            sql += " OFFSET %s"
            params.append(offset)
        with self._cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return [LLMUsage(**dict(row)) for row in rows]

    def get(self, usage_id: int) -> Optional[LLMUsage]:
        sql = (
            "SELECT id, timestamp, provider, api_kind, model, api_endpoint, route, device_id, inline_parts, "
            "prompt_chars, input_tokens, output_tokens, total_tokens, latency_ms, status_code, "
            "cost_input, cost_output, cost_total, request_payload, response_payload "
            "FROM llm_usage WHERE id = %s"
        )
        with self._cursor() as cursor:
            cursor.execute(sql, (usage_id,))
            row = cursor.fetchone()
        if row is None:
            return None
        return LLMUsage(**dict(row))

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
        with self._cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone() or {}
        # RealDictRow 直接是 dict，確保空值為 0 或 0.0
        return LLMUsageSummary(
            count=int(row.get("count", 0) or 0),
            total_input_tokens=int(row.get("total_input_tokens", 0) or 0),
            total_output_tokens=int(row.get("total_output_tokens", 0) or 0),
            total_tokens=int(row.get("total_tokens", 0) or 0),
            total_prompt_chars=int(row.get("total_prompt_chars", 0) or 0),
            avg_latency_ms=float(row.get("avg_latency_ms", 0) or 0.0),
            total_input_cost_usd=float(row.get("total_input_cost_usd", 0) or 0.0),
            total_output_cost_usd=float(row.get("total_output_cost_usd", 0) or 0.0),
            total_cost_usd=float(row.get("total_cost_usd", 0) or 0.0),
        )

    def reset(self) -> None:
        with self._cursor() as cursor:
            cursor.execute("DELETE FROM llm_usage")


class UsageStorage(_BaseStorage):
    def __init__(self, *, db_path: Optional[str], db_url: Optional[str]) -> None:
        if db_url:
            self._impl: _BaseStorage = _PostgresUsageStorage(db_url)
        elif db_path:
            self._impl = _SQLiteUsageStorage(db_path)
        else:  # pragma: no cover - 不應發生
            raise ValueError("Either db_path or db_url must be provided for UsageStorage")

    def record(self, usage: LLMUsage) -> int:
        return self._impl.record(usage)

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
        return self._impl.query(
            device_id=device_id,
            route=route,
            model=model,
            provider=provider,
            since=since,
            until=until,
            limit=limit,
            offset=offset,
        )

    def get(self, usage_id: int) -> Optional[LLMUsage]:
        return self._impl.get(usage_id)

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
        return self._impl.summarize(
            device_id=device_id,
            route=route,
            model=model,
            provider=provider,
            since=since,
            until=until,
        )

    def reset(self) -> None:
        self._impl.reset()


_DB_INSTANCE: Optional[UsageStorage] = None


def get_storage() -> UsageStorage:
    global _DB_INSTANCE
    if _DB_INSTANCE is None:
        settings = get_settings()
        db_url = getattr(settings, "USAGE_DB_URL", None)
        path_value = getattr(settings, "USAGE_DB_PATH", "data/usage.db")
        path = Path(path_value)
        if not path.is_absolute():
            backend_dir = Path(__file__).resolve().parent.parent
            path = backend_dir / path
        _DB_INSTANCE = UsageStorage(db_path=str(path), db_url=db_url)
    return _DB_INSTANCE
