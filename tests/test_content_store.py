import json

import pytest

from app.content_store import CLOUD_DECKS_SEED, ContentStore


@pytest.fixture
def content_dir(tmp_path):
    decks = tmp_path / "decks"
    books = tmp_path / "books"
    courses = tmp_path / "courses"
    decks.mkdir()
    books.mkdir()
    courses.mkdir()

    deck_payload = {
        "id": "deck-json",
        "name": "JSON Deck",
        "cards": [
            {"front": "F", "back": "B"},
        ],
    }
    (decks / "deck-json.json").write_text(json.dumps(deck_payload), encoding="utf-8")

    book_payload = {
        "id": "book-json",
        "name": "JSON Book",
        "items": [
            {
                "id": "item-1",
                "zh": "題目一",
                "hints": [{"category": "lexical", "text": "hint"}],
                "difficulty": 2,
            }
        ],
    }
    (books / "book-json.json").write_text(json.dumps(book_payload), encoding="utf-8")

    course_payload = {
        "id": "course-json",
        "title": "JSON Course",
        "books": [
            {
                "id": "course-book-1",
                "source": {"id": "book-json"},
                "difficulty": 1,
            }
        ],
    }
    (courses / "course-json.json").write_text(json.dumps(course_payload), encoding="utf-8")

    return tmp_path


def test_loads_json_files(content_dir):
    store = ContentStore(base_path=str(content_dir))
    stats = store.stats()
    assert stats == {"decks": 1, "books": 1, "courses": 1}

    deck = store.get_deck("deck-json")
    assert deck["cards"][0]["id"]

    course = store.get_course("course-json")
    assert course["books"][0]["id"] == "course-book-1"


def test_fallback_seeds_when_missing(tmp_path):
    store = ContentStore(base_path=str(tmp_path))
    stats = store.stats()
    assert stats["decks"] == len(CLOUD_DECKS_SEED)
    assert stats["books"] >= 1
    assert stats["courses"] >= 1


def test_search_and_reload(content_dir):
    store = ContentStore(base_path=str(content_dir))
    store.load()
    hits = store.search("json")
    assert hits["books"]
    assert hits["courses"]

    stats_before = store.stats()
    (content_dir / "decks" / "deck-json.json").unlink()
    store.reload()
    stats_after = store.stats()
    assert stats_after["decks"] == stats_before["decks"] - 1 or stats_after["decks"] == len(CLOUD_DECKS_SEED)


def test_get_course_book(content_dir):
    store = ContentStore(base_path=str(content_dir))
    course_book = store.get_course_book("course-json", "course-book-1")
    assert course_book["items"]
    assert course_book["itemCount"] == len(course_book["items"])


def test_book_to_course_entry_copies_items(content_dir):
    store = ContentStore(base_path=str(content_dir))
    store.load()
    book = store._books_by_id["book-json"]
    transformed = store._book_to_course_entry(book, {"id": "override"})
    transformed["items"].append({"id": "new"})
    assert len(book["items"]) == 1  # original unaffected
