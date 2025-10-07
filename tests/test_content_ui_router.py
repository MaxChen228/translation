from __future__ import annotations

from typing import Callable, Dict, List, Optional

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from app.routers import content_ui
from app.schemas import ContentUploadResult


class FakeContentStore:
    def __init__(self, books: Optional[List[Dict]] = None, courses: Optional[List[Dict]] = None) -> None:
        self._books = [dict(b) for b in (books or [])]
        self._courses = [dict(c) for c in (courses or [])]
        self.load_calls = 0
        self.reload_calls = 0

    def list_books(self) -> List[Dict]:
        return [dict(b) for b in self._books]

    def list_course_summaries(self) -> List[Dict]:
        return [dict(c) for c in self._courses]

    def load(self) -> None:
        self.load_calls += 1

    def reload(self) -> None:
        self.reload_calls += 1


class FakeContentManager:
    def __init__(self, result: ContentUploadResult) -> None:
        self._result = result
        self.calls: List[Dict] = []

    def upload_content(self, *, filename: str, content: dict, content_type: str) -> ContentUploadResult:
        self.calls.append({
            "filename": filename,
            "content": content,
            "content_type": content_type,
        })
        return self._result


@pytest.fixture
def setup_content_ui(monkeypatch):
    def _factory(
        *,
        books: Optional[List[Dict]] = None,
        courses: Optional[List[Dict]] = None,
        manager_result: Optional[ContentUploadResult] = None,
    ) -> tuple[TestClient, FakeContentStore, FakeContentManager, Dict[str, object], List[str]]:
        store = FakeContentStore(books=books, courses=courses)
        result = manager_result or ContentUploadResult(
            filename="course-1.json",
            success=True,
            message="ok",
            content_type="course",
        )
        manager = FakeContentManager(result)

        reload_calls: List[str] = []

        def fake_reload_prompts() -> None:
            reload_calls.append("called")

        capture: Dict[str, object] = {}

        def fake_template_response(name: str, context: dict) -> Response:
            capture["name"] = name
            capture["context"] = context
            return Response("rendered", media_type="text/plain")

        monkeypatch.setattr(content_ui, "get_content_store", lambda: store)
        monkeypatch.setattr(content_ui, "_CONTENT", store)
        monkeypatch.setattr(content_ui, "get_content_manager", lambda: manager)
        monkeypatch.setattr(content_ui, "reload_prompts", fake_reload_prompts)
        monkeypatch.setattr(content_ui._TEMPLATES, "TemplateResponse", fake_template_response)

        app = FastAPI()
        app.dependency_overrides[content_ui._verify_content_token] = lambda: None
        app.include_router(content_ui.router)
        client = TestClient(app)

        return client, store, manager, capture, reload_calls

    return _factory


def test_render_ui_uses_store_counts(setup_content_ui):
    books = [{"id": "book-1", "title": "Book"}]
    courses = [{"id": "course-1", "title": "Course"}]
    client, store, _, captured, _ = setup_content_ui(books=books, courses=courses)

    response = client.get("/admin/content/ui")
    assert response.status_code == 200
    assert captured["name"] == "admin/content_ui.html"

    context = captured["context"]
    assert context["books"] == books
    assert context["courses"] == courses
    assert context["books_count"] == 1
    assert context["courses_count"] == 1


def test_fetch_content_data_returns_store_lists(setup_content_ui):
    books = [{"id": "book-1"}, {"id": "book-2"}]
    courses = [{"id": "course-1"}]
    client, _, _, _, _ = setup_content_ui(books=books, courses=courses)

    response = client.get("/admin/content/ui/data")
    assert response.status_code == 200
    assert response.json() == {"books": books, "courses": courses}


def test_create_or_update_course_success(setup_content_ui):
    books = [{"id": "book-1", "title": "Book"}]
    manager_result = ContentUploadResult(
        filename="course-new.json",
        success=True,
        message="uploaded",
        content_type="course",
    )
    client, store, manager, _, reload_calls = setup_content_ui(books=books, manager_result=manager_result)

    payload = {
        "courseId": "course-new",
        "title": "Daily Course",
        "summary": "desc",
        "coverImage": "img",
        "tags": ["grammar"],
        "books": [
            {
                "bookId": "book-1",
                "aliasId": "alias-1",
                "title": "Custom Title",
                "summary": "custom",
                "coverImage": "cover",
                "tags": ["tag"],
                "difficulty": 3,
            }
        ],
    }

    response = client.post("/admin/content/ui/course", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["courseId"] == "course-new"
    assert data["upload"]["success"] is True

    assert store.load_calls == 1
    assert store.reload_calls == 1
    assert reload_calls == ["called"]

    assert len(manager.calls) == 1
    call = manager.calls[0]
    assert call["filename"] == "course-new.json"
    assert call["content_type"] == "course"

    course_books = call["content"]["books"]
    assert course_books[0]["id"] == "alias-1"
    assert course_books[0]["source"] == {"id": "book-1"}


def test_create_or_update_course_missing_book(setup_content_ui):
    client, store, manager, _, _ = setup_content_ui(books=[])

    payload = {
        "courseId": "course-new",
        "title": "Daily Course",
        "books": [{"bookId": "unknown", "aliasId": "alias"}],
    }

    response = client.post("/admin/content/ui/course", json=payload)
    assert response.status_code == 400
    assert "題庫本不存在" in response.json()["detail"]
    assert store.load_calls == 1
    assert manager.calls == []


def test_create_or_update_course_duplicate_alias(setup_content_ui):
    books = [{"id": "book-1"}, {"id": "book-2"}]
    client, _, manager, _, _ = setup_content_ui(books=books)

    payload = {
        "courseId": "dup-course",
        "title": "Course",
        "books": [
            {"bookId": "book-1", "aliasId": "dup"},
            {"bookId": "book-2", "aliasId": "dup"},
        ],
    }

    response = client.post("/admin/content/ui/course", json=payload)
    assert response.status_code == 400
    assert "課程書籍 id 重複" in response.json()["detail"]
    assert manager.calls == []


def test_create_or_update_course_upload_failure(setup_content_ui):
    books = [{"id": "book-1"}]
    manager_result = ContentUploadResult(
        filename="course-new.json",
        success=False,
        message="驗證失敗",
        content_type="course",
    )
    client, _, manager, _, _ = setup_content_ui(books=books, manager_result=manager_result)

    payload = {
        "courseId": "course-new",
        "title": "Course",
        "books": [{"bookId": "book-1", "aliasId": "alias"}],
    }

    response = client.post("/admin/content/ui/course", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "驗證失敗"
    assert len(manager.calls) == 1
