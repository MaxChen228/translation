from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.content_store import get_content_store
from app.schemas import (
    BankItem,
    CloudCard,
    CloudCourseDetail,
    CloudCourseSummary,
    CloudDeckDetail,
    CloudDeckSummary,
    CloudSearchBookHit,
    CloudSearchCourseHit,
    CloudSearchResponse,
    CourseBookDetail,
)

router = APIRouter()
_CONTENT = get_content_store()


@router.get("/cloud/decks", response_model=list[CloudDeckSummary])
def cloud_decks():
    decks = _CONTENT.list_decks()
    return [CloudDeckSummary(id=d["id"], name=d["name"], count=len(d.get("cards", []))) for d in decks]


@router.get("/cloud/decks/{deck_id}", response_model=CloudDeckDetail)
def cloud_deck_detail(deck_id: str):
    deck = _CONTENT.get_deck(deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="not_found")
    cards = [CloudCard.model_validate(c) for c in deck.get("cards", [])]
    return CloudDeckDetail(id=deck["id"], name=deck["name"], cards=cards)


@router.get("/cloud/courses", response_model=list[CloudCourseSummary])
def cloud_courses():
    courses = _CONTENT.list_course_summaries()
    return [CloudCourseSummary.model_validate(c) for c in courses]


@router.get("/cloud/courses/{course_id}", response_model=CloudCourseDetail)
def cloud_course_detail(course_id: str):
    course = _CONTENT.get_course(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="not_found")
    books: list[CourseBookDetail] = []
    for book in course.get("books", []):
        items = [BankItem.model_validate(it) for it in book.get("items", [])]
        books.append(
            CourseBookDetail(
                id=book["id"],
                title=book["title"],
                summary=book.get("summary"),
                coverImage=book.get("coverImage"),
                tags=book.get("tags", []),
                difficulty=book.get("difficulty"),
                itemCount=book.get("itemCount") or len(items),
                items=items,
            )
        )
    return CloudCourseDetail(
        id=course["id"],
        title=course["title"],
        summary=course.get("summary"),
        coverImage=course.get("coverImage"),
        tags=course.get("tags", []),
        bookCount=len(books),
        books=books,
    )


@router.get("/cloud/courses/{course_id}/books/{book_id}", response_model=CourseBookDetail)
def cloud_course_book_detail(course_id: str, book_id: str):
    book = _CONTENT.get_course_book(course_id, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="not_found")
    items = [BankItem.model_validate(it) for it in book.get("items", [])]
    return CourseBookDetail(
        id=book["id"],
        title=book["title"],
        summary=book.get("summary"),
        coverImage=book.get("coverImage"),
        tags=book.get("tags", []),
        difficulty=book.get("difficulty"),
        itemCount=book.get("itemCount") or len(items),
        items=items,
    )


@router.get("/cloud/search", response_model=CloudSearchResponse)
def cloud_search(q: str):
    result = _CONTENT.search(q)
    courses = [CloudSearchCourseHit.model_validate(c) for c in result["courses"]]
    books = [CloudSearchBookHit.model_validate(b) for b in result["books"]]
    return CloudSearchResponse(query=q, courses=courses, books=books)
