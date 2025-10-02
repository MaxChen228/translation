import json
import os
from pathlib import Path
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from app.app import create_app
from app.core.settings import get_settings
from app import content_store as content_store_module
from app.llm import reload_prompts, load_system_prompt


@pytest.fixture(autouse=True)
def reset_settings():
    get_settings.cache_clear()
    reload_prompts()
    yield
    get_settings.cache_clear()
    reload_prompts()

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


def build_book_payload(book_id: str = "uploaded-book") -> dict:
    return {
        "id": book_id,
        "name": f"Book {book_id}",
        "summary": "上傳測試題庫",
        "items": [
            {
                "id": f"{book_id}-item-1",
                "zh": "This is a sample sentence.",
                "hints": [
                    {"category": "lexical", "text": "sample"}
                ],
                "suggestions": [],
                "tags": ["grammar"],
                "difficulty": 2,
            }
        ],
    }


def create_client(tmp_path: Path, token: Optional[str]) -> TestClient:
    os.environ["CONTENT_DIR"] = str(tmp_path)
    if token is not None:
        os.environ["CONTENT_ADMIN_TOKEN"] = token
    else:
        os.environ.pop("CONTENT_ADMIN_TOKEN", None)

    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_files = {
        "PROMPT_FILE": "prompt.txt",
        "DECK_PROMPT_FILE": "prompt_deck.txt",
        "CHAT_TURN_PROMPT_FILE": "prompt_chat_turn.txt",
        "CHAT_RESEARCH_PROMPT_FILE": "prompt_chat_research.txt",
        "MERGE_PROMPT_FILE": "prompt_merge.txt",
        "FLASHCARD_COMPLETION_PROMPT_FILE": "prompt_flashcard_completion.txt",
    }
    for env_key, filename in prompt_files.items():
        path = prompt_dir / filename
        os.environ[env_key] = str(path)
        if not path.exists():
            path.write_text(f"{env_key} placeholder", encoding="utf-8")

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


def test_upload_rejects_path_traversal(tmp_path):
    write_sample_content(tmp_path)
    client = create_client(tmp_path, token="secret")

    payload = {
        "filename": "../evil-book",
        "content": build_book_payload(),
        "content_type": "book",
    }

    resp = client.post(
        "/admin/content/upload",
        headers={"X-Content-Token": "secret"},
        json=payload,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["success"] is False
    assert "檔名" in data["results"][0]["message"]
    assert not (tmp_path / "books" / "evil-book.json").exists()


def test_upload_succeeds_and_reloads(tmp_path):
    write_sample_content(tmp_path, book_count=1)
    client = create_client(tmp_path, token="secret")

    stats_before = client.get(
        "/admin/content/stats",
        headers={"X-Content-Token": "secret"},
    )
    assert stats_before.status_code == 200
    assert stats_before.json()["file_system"]["books"] == 1

    payload = {
        "filename": "new-uploaded-book.json",
        "content": build_book_payload("new-uploaded-book"),
        "content_type": "book",
    }

    resp = client.post(
        "/admin/content/upload",
        headers={"X-Content-Token": "secret"},
        json=payload,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success_count"] == 1
    assert data["results"][0]["success"] is True

    stored_file = tmp_path / "books" / "new-uploaded-book.json"
    assert stored_file.exists()

    stats_after = client.get(
        "/admin/content/stats",
        headers={"X-Content-Token": "secret"},
    )
    assert stats_after.status_code == 200
    payload_after = stats_after.json()
    assert payload_after["file_system"]["books"] == 2
    assert payload_after["loaded_in_memory"]["books"] == 2


def test_upload_course_rejects_inline_items(tmp_path):
    write_sample_content(tmp_path)
    client = create_client(tmp_path, token="secret")

    course_payload = {
        "filename": "inline-course",
        "content_type": "course",
        "content": {
            "id": "inline-course",
            "title": "Inline Course",
            "books": [
                {
                    "id": "inline-book",
                    "source": {"id": "book-0"},
                    "items": [
                        {
                            "id": "inline-1",
                            "zh": "內嵌題目",
                            "hints": [],
                            "suggestions": [],
                        }
                    ],
                }
            ],
        },
    }

    resp = client.post(
        "/admin/content/upload",
        headers={"X-Content-Token": "secret"},
        json=course_payload,
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["success"] is False
    assert "不可直接內嵌題目" in result["message"]


def test_prompt_list_and_upload(tmp_path):
    client = create_client(tmp_path, token="secret")
    headers = {"X-Content-Token": "secret"}

    # Prime cache with existing prompt content
    first_read = load_system_prompt()
    assert "PROMPT_FILE" in first_read

    list_resp = client.get("/admin/prompts", headers=headers)
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert any(item["promptId"] == "system" for item in listed["prompts"])

    new_content = "Updated system prompt"
    upload_resp = client.post(
        "/admin/prompts/upload",
        headers=headers,
        json={"promptId": "system", "content": new_content},
    )
    assert upload_resp.status_code == 200
    payload = upload_resp.json()["result"]
    assert payload["promptId"] == "system"
    assert payload["bytesWritten"] == len((new_content + "\n").encode("utf-8"))
    assert payload["backupPath"] is not None

    written_path = Path(payload["path"])
    assert written_path.exists()
    assert written_path.read_text(encoding="utf-8") == new_content + "\n"

    # Cache should have been cleared; new read returns updated content
    updated = load_system_prompt()
    assert updated == new_content


def test_prompt_upload_rejects_unknown_id(tmp_path):
    client = create_client(tmp_path, token="secret")
    headers = {"X-Content-Token": "secret"}

    resp = client.post(
        "/admin/prompts/upload",
        headers=headers,
        json={"promptId": "unknown", "content": "bad"},
    )
    assert resp.status_code == 422


def test_prompt_upload_requires_token(tmp_path):
    client = create_client(tmp_path, token="secret")

    resp = client.post(
        "/admin/prompts/upload",
        json={"promptId": "system", "content": "new"},
    )
    assert resp.status_code == 401


def test_reload_endpoint_refreshes_prompt_cache(tmp_path, monkeypatch):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    prompt_file = prompt_dir / "prompt.txt"
    prompt_file.write_text("first version", encoding="utf-8")

    monkeypatch.setenv("PROMPT_FILE", str(prompt_file))
    get_settings.cache_clear()
    reload_prompts()

    from app.llm import load_system_prompt

    initial = load_system_prompt()
    assert initial == "first version"

    prompt_file.write_text("second version", encoding="utf-8")

    # Cached value should still be the first version before reload endpoint is called
    assert load_system_prompt() == "first version"

    content_root = tmp_path
    write_sample_content(content_root)
    client = create_client(content_root, token=None)

    resp = client.post("/admin/content/reload")
    assert resp.status_code == 200

    assert load_system_prompt() == "second version"
