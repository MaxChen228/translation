import os
import tempfile
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.app import create_app
from app.core.settings import get_settings
from app.question_store import QuestionRecord, QuestionStore


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "questions.sqlite")
        monkeypatch.setenv("QUESTION_DB_PATH", db_path)
        monkeypatch.delenv("QUESTION_DB_URL", raising=False)
        get_settings.cache_clear()
        yield


def _create_question(question_date: date) -> QuestionRecord:
    payload: dict[str, object] = {
        "id": "daily-test-001",
        "zh": "這是一個每日推送測試題目。",
        "hints": [
            {"category": "lexical", "text": "使用 present perfect"},
        ],
        "reviewNote": "強調現在完成式的使用情境",
        "tags": ["daily-life", "grammar"],
        "difficulty": 2,
        "referenceEn": "This is a test daily push question."
    }
    reference_en = str(payload.get("referenceEn", ""))
    return QuestionRecord.from_payload(
        question_date=question_date,
        item=payload,
        reference_en=reference_en,
        model="gemini-2.5-flash",
        prompt_hash="hash",
    )


def test_daily_push_pull_creates_delivery(monkeypatch):
    today = date.today()
    store = QuestionStore(db_url=None, db_path=os.environ["QUESTION_DB_PATH"])
    try:
        store.save_many([_create_question(today)])
    finally:
        store.close()

    client = TestClient(create_app())
    resp = client.post(
        "/daily_push/pull",
        json={"deviceId": "device-1", "date": today.isoformat(), "count": 10},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["delivered"] == 1
    assert data["remaining"] == 0
    assert data["questions"][0]["id"] == "daily-test-001"

    # Second call should yield zero questions for same device
    resp2 = client.post(
        "/daily_push/pull",
        json={"deviceId": "device-1", "date": today.isoformat(), "count": 10},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["delivered"] == 0
    assert data2["remaining"] == 0

    # Different device should still receive the question (new entry)
    resp3 = client.post(
        "/daily_push/pull",
        json={"deviceId": "device-2", "date": today.isoformat(), "count": 10},
    )
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["delivered"] == 1


def test_daily_push_requires_non_empty_device():
    client = TestClient(create_app())
    today = date.today().isoformat()
    resp = client.post(
        "/daily_push/pull",
        json={"deviceId": "   ", "date": today, "count": 1},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "deviceId_required"
