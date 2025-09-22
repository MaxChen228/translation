import json

import pytest
from fastapi.testclient import TestClient

from app.app import create_app
from app.content_store import ContentStore
from app.core.settings import get_settings
import app.routers.cloud as cloud_router


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    content_dir = tmp_path / "content"
    books_dir = content_dir / "books"
    courses_dir = content_dir / "courses"
    books_dir.mkdir(parents=True)
    courses_dir.mkdir()

    # Build a sample book file
    book_payload = {
        "id": "test-book",
        "name": "Test Book",
        "summary": "簡單句型練習",
        "coverImage": "https://example.com/book.png",
        "items": [
            {
                "id": "item-1",
                "zh": "這是一句測試句子。",
                "hints": [{"category": "lexical", "text": "注意字彙搭配"}],
                "suggestions": [{"text": "可加入更多細節", "category": "style"}],
                "tags": ["lexical"],
                "difficulty": 2,
            }
        ],
    }
    (books_dir / "test-book.json").write_text(json.dumps(book_payload, ensure_ascii=False), encoding="utf-8")

    # Course referencing the book and an inline book definition
    course_payload = {
        "id": "test-course",
        "title": "Test Course",
        "summary": "示範課程，包含引用題本與內嵌題本，用於測試流程。",
        "coverImage": "https://example.com/course.png",
        "tags": ["demo", "lexical"],
        "books": [
            {
                "id": "test-book",
                "title": "Test Book",
                "summary": "引用既有題本。",
                "coverImage": "https://example.com/book.png",
                "tags": ["lexical"],
                "difficulty": 2,
                "source": {"id": "test-book"},
            },
            {
                "id": "inline-book",
                "title": "Inline Book",
                "summary": "直接在課程內定義題目。",
                "coverImage": "https://example.com/inline.png",
                "tags": ["syntactic"],
                "difficulty": 3,
                "items": [
                    {
                        "id": "inline-1",
                        "zh": "內嵌題目測試。",
                        "hints": [{"category": "syntactic", "text": "倒裝句"}],
                        "suggestions": [],
                        "tags": ["syntactic"],
                        "difficulty": 3,
                    }
                ],
            },
        ],
    }
    (courses_dir / "test-course.json").write_text(json.dumps(course_payload, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setenv("CONTENT_DIR", str(content_dir))
    get_settings.cache_clear()
    cloud_router._CONTENT = ContentStore()
    app = create_app()
    return TestClient(app)


def test_list_courses(client: TestClient):
    resp = client.get("/cloud/courses")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    course = data[0]
    assert course["id"] == "test-course"
    assert course["bookCount"] == 2
    assert "coverImage" in course


def test_course_detail_and_book_detail(client: TestClient):
    detail = client.get("/cloud/courses/test-course")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["id"] == "test-course"
    assert payload["bookCount"] == 2
    books = payload["books"]
    assert {b["id"] for b in books} == {"test-book", "inline-book"}
    # Ensure items were hydrated
    referenced = next(b for b in books if b["id"] == "test-book")
    assert referenced["itemCount"] == 1
    assert referenced["items"][0]["zh"].startswith("這是一句")

    book_detail = client.get("/cloud/courses/test-course/books/inline-book")
    assert book_detail.status_code == 200
    book_payload = book_detail.json()
    assert book_payload["id"] == "inline-book"
    assert book_payload["itemCount"] == 1
    assert book_payload["items"][0]["hints"][0]["category"] == "syntactic"


def test_course_not_found(client: TestClient):
    resp = client.get("/cloud/courses/unknown")
    assert resp.status_code == 404


def test_search_endpoint(client: TestClient):
    resp = client.get("/cloud/search", params={"q": "測試"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["query"] == "測試"
    assert payload["courses"][0]["id"] == "test-course"
    # Books should include both referenced and inline definitions
    book_ids = {hit["id"] for hit in payload["books"]}
    assert book_ids == {"test-book", "inline-book"}
