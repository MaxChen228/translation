from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.content_store import get_content_store
from app.core.settings import get_settings
from app.llm import reload_prompts
from app.routers.admin import _verify_content_token
from app.services.content_manager import get_content_manager

router = APIRouter(prefix="/admin/content/ui", tags=["admin-content-ui"])
_CONTENT = get_content_store()
_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


class CourseBookSelection(BaseModel):
    bookId: str = Field(min_length=1)
    aliasId: Optional[str] = Field(default=None)
    title: Optional[str] = None
    summary: Optional[str] = None
    coverImage: Optional[str] = None
    tags: Optional[List[str]] = None
    difficulty: Optional[int] = Field(default=None, ge=1, le=5)


class CourseDraftPayload(BaseModel):
    courseId: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: Optional[str] = None
    coverImage: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    books: List[CourseBookSelection]

    def course_filename(self) -> str:
        return f"{self.courseId}.json"


@router.get("", response_class=HTMLResponse)
def render_ui(request: Request, _: None = Depends(_verify_content_token)):
    store = get_content_store()
    books = store.list_books()
    courses = store.list_course_summaries()
    context = {
        "request": request,
        "books": books,
        "courses": courses,
        "books_count": len(books),
        "courses_count": len(courses),
        "has_token": get_settings().CONTENT_ADMIN_TOKEN is not None,
    }
    return _TEMPLATES.TemplateResponse("admin/content_ui.html", context)


@router.get("/data")
def fetch_content_data(_: None = Depends(_verify_content_token)) -> dict:
    store = get_content_store()
    return {
        "books": store.list_books(),
        "courses": store.list_course_summaries(),
    }


@router.post("/course")
def create_or_update_course(payload: CourseDraftPayload, _: None = Depends(_verify_content_token)):
    store = get_content_store()
    store.load()
    available = {book["id"]: book for book in store.list_books()}

    course_books = []
    seen_aliases: set[str] = set()
    for entry in payload.books:
        book_id = entry.bookId.strip()
        if book_id not in available:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"題庫本不存在: {book_id}")
        alias = (entry.aliasId or book_id).strip()
        if not alias:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="課程書籍 id 不可為空")
        if alias in seen_aliases:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"課程書籍 id 重複: {alias}")
        seen_aliases.add(alias)
        overrides: Dict[str, object] = {}
        if entry.title:
            overrides["title"] = entry.title
        if entry.summary:
            overrides["summary"] = entry.summary
        if entry.coverImage:
            overrides["coverImage"] = entry.coverImage
        if entry.tags is not None:
            overrides["tags"] = entry.tags
        if entry.difficulty is not None:
            overrides["difficulty"] = entry.difficulty
        overrides["id"] = alias
        overrides["source"] = {"id": book_id}
        course_books.append(overrides)

    course_content = {
        "id": payload.courseId,
        "title": payload.title,
        "summary": payload.summary,
        "coverImage": payload.coverImage,
        "tags": payload.tags,
        "books": course_books,
    }

    manager = get_content_manager()
    result = manager.upload_content(
        filename=payload.course_filename(),
        content=course_content,
        content_type="course",
    )

    if not result.success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.message)

    _CONTENT.reload()
    reload_prompts()
    return {
        "status": "ok",
        "courseId": payload.courseId,
        "upload": result.model_dump(),
    }
