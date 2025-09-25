from __future__ import annotations

import asyncio
from typing import Optional

import httpx


_client: Optional[httpx.AsyncClient] = None
_client_lock: Optional[asyncio.Lock] = None


def _build_client() -> httpx.AsyncClient:
    timeout = httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=None)
    limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
    return httpx.AsyncClient(timeout=timeout, limits=limits, http2=True)


async def init_http_client() -> httpx.AsyncClient:
    global _client, _client_lock
    if _client is None:
        if _client_lock is None:
            _client_lock = asyncio.Lock()
        async with _client_lock:
            if _client is None:
                _client = _build_client()
    return _client


def get_http_client() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("Async HTTP client not initialized")
    return _client


async def close_http_client() -> None:
    global _client, _client_lock
    if _client_lock is None:
        _client_lock = asyncio.Lock()
    async with _client_lock:
        if _client is not None:
            await _client.aclose()
            _client = None
        _client_lock = None
