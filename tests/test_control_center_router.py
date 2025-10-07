from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from app.routers import control_center


class DummyUsageSummary:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self._payload = payload

    def model_dump(self, mode: str = "json") -> Dict[str, Any]:
        return self._payload


class FakeContentStore:
    def __init__(self, stats_payload: Dict[str, Any]) -> None:
        self._stats = stats_payload
        self.reload_called = 0

    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    def reload(self) -> None:
        self.reload_called += 1


class FakeContentManager:
    def __init__(self, stats_payload: Dict[str, Any]) -> None:
        self._stats = stats_payload

    def get_content_stats(self) -> Dict[str, Any]:
        return dict(self._stats)


@pytest.fixture
def setup_control_center(monkeypatch):
    def _factory(
        *,
        summary: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        summary_data = summary or [
            {
                "question_date": dt.date(2025, 10, 5),
                "question_count": 4,
                "delivered_devices": 2,
            },
            {
                "question_date": dt.date(2025, 10, 4),
                "question_count": 2,
                "delivered_devices": 1,
            },
        ]

        store = FakeContentStore({"books": 12, "courses": 3})
        manager = FakeContentManager({"books": 20, "courses": 8})

        settings = SimpleNamespace(QUESTION_DB_URL=None, QUESTION_DB_PATH="data/questions.sqlite")

        usage_payloads = {
            "last24": DummyUsageSummary({"requests": 15, "tokens": 1200}),
            "all": DummyUsageSummary({"requests": 120, "tokens": 9800}),
        }

        def fake_summarize_usage(*, since: Optional[float] = None):
            return usage_payloads["last24" if since is not None else "all"]

        load_calls: List[int] = []

        def fake_load_daily_summary(limit: int, settings_obj=None, **_kwargs):
            if settings_obj is not None:
                assert settings_obj is settings
            load_calls.append(limit)
            return summary_data

        reload_calls: List[str] = []

        def fake_reload_prompts() -> None:
            reload_calls.append("called")

        template_capture: Dict[str, Any] = {}

        def fake_template_response(name: str, context: Dict[str, Any]) -> Response:
            template_capture["name"] = name
            template_capture["context"] = context
            return Response("rendered", media_type="text/plain")

        prompts_metadata = {
            "system": {"path": "/tmp/prompts/system.txt", "cache_key": "sys"},
            "deck": {"path": "/tmp/prompts/deck.txt", "cache_key": "deck"},
        }

        prompt_storage = {"system": "system-content", "deck": "deck-content"}
        write_error: Dict[str, Optional[Exception]] = {"error": None}
        write_calls: List[Dict[str, Any]] = []

        def fake_list_prompts():
            return prompts_metadata

        def fake_write_prompt(prompt_id: str, content: str):
            if write_error["error"] is not None:
                raise write_error["error"]
            write_calls.append({"prompt_id": prompt_id, "content": content})
            prompt_storage[prompt_id] = content
            return {
                "path": f"/tmp/prompts/{prompt_id}.txt",
                "backup_path": f"/tmp/prompts/{prompt_id}.bak",
            }

        def fake_read_prompt(prompt_id: str) -> str:
            if prompt_id not in prompt_storage:
                raise ValueError("not found")
            return prompt_storage[prompt_id]

        monkeypatch.setattr(control_center, "get_content_store", lambda: store)
        monkeypatch.setattr(control_center, "get_content_manager", lambda: manager)
        monkeypatch.setattr(control_center, "get_settings", lambda: settings)
        monkeypatch.setattr(control_center, "summarize_usage", fake_summarize_usage)
        monkeypatch.setattr(control_center, "_load_daily_summary", fake_load_daily_summary)
        monkeypatch.setattr(control_center, "reload_prompts", fake_reload_prompts)
        monkeypatch.setattr(control_center, "list_prompts", fake_list_prompts)
        monkeypatch.setattr(control_center, "write_prompt", fake_write_prompt)
        monkeypatch.setattr(control_center, "read_prompt", fake_read_prompt)
        monkeypatch.setattr(control_center, "sys_health_check", lambda: {"status": "ok"})
        monkeypatch.setattr(control_center, "os", SimpleNamespace(path=SimpleNamespace(getmtime=lambda _: 123.0)))
        monkeypatch.setattr(control_center._templates, "TemplateResponse", fake_template_response)

        app = FastAPI()
        app.dependency_overrides[control_center._verify_content_token] = lambda: None
        app.include_router(control_center.router)
        client = TestClient(app)

        return {
            "client": client,
            "store": store,
            "manager": manager,
            "capture": template_capture,
            "reload_calls": reload_calls,
            "load_calls": load_calls,
            "write_calls": write_calls,
            "write_error": write_error,
            "prompt_storage": prompt_storage,
            "summary_data": summary_data,
        }

    return _factory


def test_render_control_center_template(setup_control_center):
    fixture = setup_control_center()
    response = fixture["client"].get("/admin/control-center")
    assert response.status_code == 200
    assert fixture["capture"]["name"] == "admin/control_center.html"


def test_control_center_overview_payload(setup_control_center):
    fixture = setup_control_center()
    response = fixture["client"].get("/admin/control-center/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["health"] == {"status": "ok"}
    assert data["content"]["loaded"] == {"books": 12, "courses": 3}
    assert data["content"]["files"] == {"books": 20, "courses": 8}
    assert data["environment"]["hasQuestionDbPath"] is True
    assert data["generated"]["latestDate"] == fixture["summary_data"][0]["question_date"].isoformat()
    assert data["generated"]["recent"][0]["deliveredDevices"] == 2
    assert data["usage"]["last24h"] == {"requests": 15, "tokens": 1200}
    assert data["usage"]["allTime"] == {"requests": 120, "tokens": 9800}
    assert fixture["load_calls"] == [7]


def test_control_center_daily_summary_limits_and_recent(setup_control_center):
    fixture = setup_control_center()
    response = fixture["client"].get("/admin/control-center/daily-summary", params={"limit": 3})
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 3
    assert data["latest"]["date"] == fixture["summary_data"][0]["question_date"].isoformat()
    assert len(data["recent"]) == len(fixture["summary_data"])
    assert fixture["load_calls"][-1] == 3


def test_control_center_content_stats(setup_control_center):
    fixture = setup_control_center()
    response = fixture["client"].get("/admin/control-center/content/stats")
    assert response.status_code == 200
    assert response.json() == {
        "loaded": {"books": 12, "courses": 3},
        "files": {"books": 20, "courses": 8},
    }


def test_control_center_content_reload_triggers_store_and_prompts(setup_control_center):
    fixture = setup_control_center()
    response = fixture["client"].post("/admin/control-center/content/reload")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert fixture["store"].reload_called == 1
    assert fixture["reload_calls"] == ["called"]


def test_control_center_daily_generate_returns_manual_command(setup_control_center):
    fixture = setup_control_center()
    response = fixture["client"].post("/admin/control-center/daily/generate")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "manual"
    assert "python -m scripts.generate_daily_questions" in payload["command"]


def test_control_center_list_prompts_sorted(setup_control_center):
    fixture = setup_control_center()
    response = fixture["client"].get("/admin/control-center/prompts")
    assert response.status_code == 200
    data = response.json()
    prompt_ids = [item["promptId"] for item in data["prompts"]]
    assert prompt_ids == sorted(prompt_ids)
    assert data["prompts"][0]["lastModified"] == 123.0


def test_control_center_update_prompt_success(setup_control_center):
    fixture = setup_control_center()
    response = fixture["client"].post(
        "/admin/control-center/prompts",
        json={"promptId": "system", "content": "new content"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["result"]["bytesWritten"] == len("new content\n".encode("utf-8"))
    assert fixture["write_calls"] == [{"prompt_id": "system", "content": "new content"}]
    assert fixture["prompt_storage"]["system"] == "new content"
    assert fixture["reload_calls"][-1] == "called"


def test_control_center_update_prompt_invalid_returns_422(setup_control_center):
    fixture = setup_control_center()
    fixture["write_error"]["error"] = ValueError("invalid prompt")
    response = fixture["client"].post(
        "/admin/control-center/prompts",
        json={"promptId": "system", "content": "bad"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid prompt"


def test_control_center_reload_prompts_endpoint(setup_control_center):
    fixture = setup_control_center()
    response = fixture["client"].post("/admin/control-center/prompts/reload")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert fixture["reload_calls"][-1] == "called"


def test_control_center_prompt_detail_success(setup_control_center):
    fixture = setup_control_center()
    response = fixture["client"].get("/admin/control-center/prompts/system")
    assert response.status_code == 200
    assert response.json() == {"promptId": "system", "content": "system-content"}


def test_control_center_prompt_detail_not_found(setup_control_center):
    fixture = setup_control_center()
    fixture["prompt_storage"].pop("system", None)
    response = fixture["client"].get("/admin/control-center/prompts/system")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_load_daily_summary_clamps_and_closes(monkeypatch):
    captured: Dict[str, Any] = {}

    class FakeQuestionStore:
        def __init__(self, *, db_url, db_path):
            captured["db_url"] = db_url
            captured["db_path"] = db_path
            self.closed = False

        def recent_summary(self, limit: int):
            captured["limit"] = limit
            return [
                {
                    "question_date": dt.date(2025, 10, 5),
                    "question_count": 5,
                    "delivered_devices": 3,
                }
            ]

        def close(self):
            captured["closed"] = True

    settings = SimpleNamespace(QUESTION_DB_URL="postgres://", QUESTION_DB_PATH="data.db")
    monkeypatch.setattr(control_center, "QuestionStore", FakeQuestionStore)

    summary = control_center._load_daily_summary(limit=50, settings=settings)
    assert summary[0]["question_count"] == 5
    assert captured["limit"] == 30  # clamped
    assert captured["db_url"] == "postgres://"
    assert captured["db_path"] == "data.db"
    assert captured["closed"] is True
