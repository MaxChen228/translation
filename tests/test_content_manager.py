from pathlib import Path

import pytest

from app.services.content_manager import ContentManager


def _patch_settings(monkeypatch, base: Path) -> None:
    settings = type("S", (), {"CONTENT_DIR": str(base)})()
    monkeypatch.setattr("app.services.content_manager.get_settings", lambda: settings)


def _create_manager(monkeypatch, tmp_path: Path) -> ContentManager:
    base = tmp_path / "content"
    base.mkdir(parents=True, exist_ok=True)
    _patch_settings(monkeypatch, base)
    return ContentManager()


def test_upload_book_and_backup(tmp_path, monkeypatch):
    manager = _create_manager(monkeypatch, tmp_path)

    book_content = {
        "id": "grammar",
        "items": [
            {"zh": "example", "hints": [{"category": "lexical", "text": "hint"}], "difficulty": 2}
        ],
    }
    result = manager.upload_content("grammar.json", book_content, "book")
    assert result.success is True

    (manager.base_dir / "books" / "grammar.json").write_text("{}", encoding="utf-8")
    result2 = manager.upload_content("grammar.json", book_content, "book")
    backups = list((manager.base_dir / "books").glob("grammar.json.backup_*"))
    assert result2.success is True
    assert backups


def test_upload_invalid_book(tmp_path, monkeypatch):
    manager = _create_manager(monkeypatch, tmp_path)
    invalid = {"name": "invalid"}
    result = manager.upload_content("invalid.json", invalid, "book")
    assert result.success is False
    assert "缺少 items" in result.message


def test_upload_course_missing_book(tmp_path, monkeypatch):
    manager = _create_manager(monkeypatch, tmp_path)
    course = {"id": "course", "title": "Course", "books": [{"source": {"id": "not-exist"}}]}
    result = manager.upload_content("course.json", course, "course")
    assert result.success is False
    assert "不存在" in result.message


def test_get_target_path_validation(tmp_path, monkeypatch):
    manager = _create_manager(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        manager._get_target_path("../hack", "book")
    with pytest.raises(ValueError):
        manager._get_target_path("", "book")
    path = manager._get_target_path("file", "book")
    assert path.name == "file.json"


def test_validate_course_success(tmp_path, monkeypatch):
    manager = _create_manager(monkeypatch, tmp_path)
    book_path = manager.base_dir / "books" / "existing.json"
    manager._write_content_file(
        book_path,
        {"id": "existing", "items": [{"zh": "題目", "hints": [], "difficulty": 1}]},
    )
    course = {
        "id": "course",
        "title": "Course",
        "books": [
            {"source": {"id": "existing"}, "id": "alias", "title": "Alias"}
        ],
    }
    assert manager._validate_course_content(course) is None


def test_list_content_files(tmp_path, monkeypatch):
    manager = _create_manager(monkeypatch, tmp_path)
    (manager.base_dir / "books" / "a.json").write_text("{}", encoding="utf-8")
    assert sorted(manager.list_content_files("book")) == ["a.json"]
    assert manager.list_content_files("course") == []
