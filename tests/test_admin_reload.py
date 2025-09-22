import json
import os
from pathlib import Path
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from app.app import create_app
from app.core.settings import get_settings
from app import content_store as content_store_module


@pytest.fixture(autouse=True)
def reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

def write_sample_content(root: Path, book_count: int = 1, alt: bool = False):
    books_dir = root / "books"
    courses_dir = root / "courses"
    books_dir.mkdir(parents=True, exist_ok=True)
    courses_dir.mkdir(parents=True, exist_ok=True)

    items = [
        {
            "id": "item-1",
            "zh": "示範句子",
            "hints": [{"category": "lexical", "text": "詞彙提示"}],
            "suggestions": [],
            "tags": ["lexical"],
            "difficulty": 2,
        }
    ]

    for idx in range(book_count):
        book = {
            "id": f"book-{idx}",
            "name": f"Book {idx}",
            "summary": "示範題庫",
            "items": items,
        }
        (books_dir / f"book-{idx}.json").write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")

    course = {
        "id": "demo-course",
        "title": "Demo Course" if not alt else "Changed Title",
        "books": [
            {
                "id": "book-0",
                "title": "Book 0",
                "source": {"id": "book-0"},
            }
        ],
    }
    (courses_dir / "demo-course.json").write_text(json.dumps(course, ensure_ascii=False), encoding="utf-8")


def create_client(tmp_path: Path, token: Optional[str]) -> TestClient:
    os.environ["CONTENT_DIR"] = str(tmp_path)
    if token is not None:
        os.environ["CONTENT_ADMIN_TOKEN"] = token
    else:
        os.environ.pop("CONTENT_ADMIN_TOKEN", None)

    get_settings.cache_clear()
    content_store_module._GLOBAL_STORE = content_store_module.ContentStore(base_path=str(tmp_path))
    store = content_store_module.get_content_store()
    from app.routers import cloud, admin
    cloud._CONTENT = store
    admin._CONTENT = store
    return TestClient(create_app())


def test_reload_endpoint_with_token(tmp_path):
    write_sample_content(tmp_path, book_count=1)
    client = create_client(tmp_path, token="secret")

    resp = client.get("/cloud/courses")
    assert resp.status_code == 200
    assert resp.json()[0]["title"] == "Demo Course"

    write_sample_content(tmp_path, book_count=2, alt=True)

    resp = client.post("/admin/content/reload", headers={"X-Content-Token": "secret"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["stats"]["books"] == 2

    resp = client.get("/cloud/courses/demo-course")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["title"] == "Changed Title"
    assert payload["bookCount"] == 1


def test_reload_endpoint_rejects_invalid_token(tmp_path):
    write_sample_content(tmp_path)
    client = create_client(tmp_path, token="expected")

    resp = client.post("/admin/content/reload", headers={"X-Content-Token": "bad"})
    assert resp.status_code == 401


def test_reload_endpoint_allows_when_token_unset(tmp_path):
    write_sample_content(tmp_path)
    client = create_client(tmp_path, token=None)

    resp = client.post("/admin/content/reload")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
