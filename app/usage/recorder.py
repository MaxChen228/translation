from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Deque, Iterable, List, Optional

from .models import LLMUsage, LLMUsageSummary


class UsageRecorder:
    def __init__(self, maxlen: int = 10000) -> None:
        self._items: Deque[LLMUsage] = deque(maxlen=maxlen)
        self._lock = Lock()

    def record(self, usage: LLMUsage) -> None:
        with self._lock:
            self._items.append(usage)

    def _snapshot(self) -> List[LLMUsage]:
        with self._lock:
            return list(self._items)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

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
        items = self._snapshot()
        filtered: List[LLMUsage] = []
        for item in items:
            if device_id and item.device_id != device_id:
                continue
            if route and item.route != route:
                continue
            if model and item.model != model:
                continue
            if provider and item.provider != provider:
                continue
            if since is not None and item.timestamp < since:
                continue
            if until is not None and item.timestamp > until:
                continue
            filtered.append(item)

        if offset:
            if offset >= len(filtered):
                return []
            filtered = filtered[offset:]

        if limit is not None and limit >= 0:
            filtered = filtered[:limit]

        return filtered


_RECORDER = UsageRecorder()


def record_usage(usage: LLMUsage) -> None:
    _RECORDER.record(usage)


def query_usage(**kwargs) -> List[LLMUsage]:
    return _RECORDER.query(**kwargs)


def summarize_usage(usages: Iterable[LLMUsage]) -> LLMUsageSummary:
    usages_list = list(usages)
    count = len(usages_list)
    if not usages_list:
        return LLMUsageSummary(
            count=0,
            total_input_tokens=0,
            total_output_tokens=0,
            total_tokens=0,
            total_prompt_chars=0,
            avg_latency_ms=0.0,
        )
    total_input = sum(u.input_tokens for u in usages_list)
    total_output = sum(u.output_tokens for u in usages_list)
    total_tokens = sum(u.total_tokens for u in usages_list)
    total_chars = sum(u.prompt_chars for u in usages_list)
    avg_latency = sum(u.latency_ms for u in usages_list) / count
    return LLMUsageSummary(
        count=count,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_tokens=total_tokens,
        total_prompt_chars=total_chars,
        avg_latency_ms=avg_latency,
    )


def reset_usage() -> None:
    _RECORDER.clear()
