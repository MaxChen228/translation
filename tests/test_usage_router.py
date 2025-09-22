import os
import tempfile
import time

os.environ.setdefault("USAGE_DB_PATH", os.path.join(tempfile.gettempdir(), "usage_test.sqlite"))

from fastapi.testclient import TestClient

from app.app import create_app
from app.usage import LLMUsage, record_usage, reset_usage


def test_usage_endpoint_returns_records():
    reset_usage()
    usage = LLMUsage(
        timestamp=time.time(),
        provider="gemini",
        api_kind="generateContent",
        model="gemini-2.5-flash",
        api_endpoint="https://example.com",
        route="/chat/respond",
        device_id="device-123",
        inline_parts=1,
        prompt_chars=120,
        input_tokens=50,
        output_tokens=25,
        total_tokens=75,
        latency_ms=88.2,
        status_code=200,
    )
    saved = record_usage(usage, route=usage.route, device_id=usage.device_id)

    client = TestClient(create_app())
    resp = client.get("/usage/llm")
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["count"] == 1
    assert data["summary"]["total_tokens"] == 75
    assert data["summary"]["total_cost_usd"] > 0
    assert data["items"][0]["device_id"] == "device-123"
    detail = client.get(f"/usage/llm/{saved.id}/view")
    assert detail.status_code == 200
    assert "Request Payload" in detail.text


def test_usage_endpoint_filters():
    reset_usage()
    base_usage = LLMUsage(
        timestamp=time.time(),
        provider="gemini",
        api_kind="generateContent",
        model="gemini-2.5-flash",
        api_endpoint="https://example.com",
        route="/chat/respond",
        device_id="device-A",
        inline_parts=0,
        prompt_chars=10,
        input_tokens=5,
        output_tokens=5,
        total_tokens=10,
        latency_ms=10.0,
        status_code=200,
    )
    record_usage(base_usage, route=base_usage.route, device_id=base_usage.device_id)
    usage_b = base_usage.model_copy(update={"device_id": "device-B", "route": "/make_deck"})
    record_usage(usage_b, route=usage_b.route, device_id=usage_b.device_id)

    client = TestClient(create_app())
    resp = client.get("/usage/llm", params={"device_id": "device-A"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["count"] == 1
    assert data["items"][0]["device_id"] == "device-A"


def test_usage_view_page_renders_html():
    client = TestClient(create_app())
    resp = client.get("/usage/llm/view")
    assert resp.status_code == 200
    assert "LLM Usage Dashboard" in resp.text
    assert "<table" in resp.text
