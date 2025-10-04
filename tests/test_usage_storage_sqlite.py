import time
import math

import pytest

from app.usage.models import LLMUsage
from app.usage.storage import UsageStorage


def _usage(ts: float, *, device: str, route: str, model: str = "gemini-pro", provider: str = "gemini") -> LLMUsage:
    return LLMUsage(
        timestamp=ts,
        provider=provider,
        api_kind="generateContent",
        model=model,
        api_endpoint="https://example.com",
        route=route,
        device_id=device,
        inline_parts=1,
        prompt_chars=12,
        input_tokens=20,
        output_tokens=10,
        total_tokens=30,
        latency_ms=45.0,
        status_code=200,
        cost_input=0.02,
        cost_output=0.03,
        cost_total=0.05,
        request_payload="{}",
        response_payload="{}",
    )


@pytest.fixture
def storage(tmp_path):
    db_path = tmp_path / "usage.sqlite"
    storage = UsageStorage(db_path=str(db_path), db_url=None)
    storage.reset()
    return storage


def test_query_filters_and_pagination(storage):
    base_ts = time.time()
    items = [
        _usage(base_ts - 300, device="device-A", route="/chat", model="model-a"),
        _usage(base_ts - 200, device="device-B", route="/chat", model="model-b"),
        _usage(base_ts - 100, device="device-A", route="/deck", model="model-b"),
    ]
    ids = [storage.record(item) for item in items]
    assert ids == sorted(ids)
    ordered_ids = [record.id for record in storage.query()]

    device_records = storage.query(device_id="device-A")
    assert len(device_records) == 2
    assert all(rec.device_id == "device-A" for rec in device_records)

    recent_records = storage.query(since=base_ts - 150)
    assert {rec.route for rec in recent_records} == {"/deck"}

    older_records = storage.query(until=base_ts - 200)
    assert len(older_records) == 2

    paged = storage.query(limit=1, offset=1)
    assert len(paged) == 1
    assert paged[0].id == ordered_ids[1]

    offset_without_limit = storage.query(offset=1)
    assert len(offset_without_limit) == len(ordered_ids) - 1


def test_summary_and_reset(storage):
    base_ts = time.time()
    storage.record(_usage(base_ts, device="device-1", route="/chat", model="model-a"))
    storage.record(_usage(base_ts + 10, device="device-1", route="/chat", model="model-b", provider="alt"))
    storage.record(_usage(base_ts + 20, device="device-2", route="/deck", model="model-b"))

    summary_device = storage.summarize(device_id="device-1")
    assert summary_device.count == 2
    assert summary_device.total_tokens == 60
    assert math.isclose(summary_device.total_cost_usd, 0.10, rel_tol=1e-6)

    summary_model = storage.summarize(model="model-b")
    assert summary_model.count == 2
    assert summary_model.total_input_tokens == 40

    storage.reset()
    empty_summary = storage.summarize()
    assert empty_summary.count == 0
    assert empty_summary.total_tokens == 0
