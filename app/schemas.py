from __future__ import annotations

from datetime import datetime
import datetime as dt
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator


# ----- Correct endpoint DTOs -----

class RangeDTO(BaseModel):
    start: int
    length: int


class InputHintDTO(BaseModel):
    # morphological | syntactic | lexical | phonological | pragmatic
    category: str
    text: str


class ErrorHintsDTO(BaseModel):
    before: Optional[str] = None
    after: Optional[str] = None
    occurrence: Optional[int] = Field(default=None, ge=1)


class ErrorDTO(BaseModel):
    id: Optional[str] = None
    span: str
    # One of the five categories used in the app
    type: str  # morphological | syntactic | lexical | phonological | pragmatic
    explainZh: str
    suggestion: Optional[str] = None
    hints: Optional[ErrorHintsDTO] = None
    originalRange: Optional[RangeDTO] = None
    suggestionRange: Optional[RangeDTO] = None
    correctedRange: Optional[RangeDTO] = None


class CorrectResponse(BaseModel):
    corrected: str
    score: int
    errors: List[ErrorDTO]
    commentary: Optional[str] = None


class CorrectRequest(BaseModel):
    zh: str
    en: str
    bankItemId: Optional[str] = None
    deviceId: Optional[str] = None
    hints: Optional[List[InputHintDTO]] = None
    suggestion: Optional[str] = None
    model: Optional[str] = None


class MergeErrorsRequest(BaseModel):
    zh: str
    en: str
    corrected: str
    errors: List[ErrorDTO]
    rationale: Optional[str] = None
    deviceId: Optional[str] = None
    model: Optional[str] = None

    @field_validator("errors")
    @classmethod
    def _ensure_two_errors(cls, errors: List[ErrorDTO]):
        if len(errors) < 2:
            raise ValueError("merge_requires_at_least_two_errors")
        return errors


class MergeErrorResponse(BaseModel):
    error: ErrorDTO


# ----- Chat workflow DTOs -----

class ChatAttachment(BaseModel):
    type: Literal["image"]
    mimeType: str
    data: str  # base64 (Gemini inline_data)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    attachments: Optional[List[ChatAttachment]] = None


class ChatTurnRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None


class ChatTurnResponse(BaseModel):
    reply: str
    state: Literal["gathering", "ready", "completed"] = "gathering"
    checklist: Optional[List[str]] = None


class ChatResearchRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None


class ChatResearchCard(BaseModel):
    front: str
    back: str
    frontNote: Optional[str] = None
    backNote: Optional[str] = None


class ChatResearchResponse(BaseModel):
    deckName: str
    generatedAt: datetime
    cards: List[ChatResearchCard]


# ----- Cloud library DTOs (Decks/Books) -----

class CloudDeckSummary(BaseModel):
    id: str
    name: str
    count: int


class CloudCard(BaseModel):
    id: str
    front: str
    back: str
    frontNote: Optional[str] = None
    backNote: Optional[str] = None


class CloudDeckDetail(BaseModel):
    id: str
    name: str
    cards: List[CloudCard]


class CloudBookSummary(BaseModel):
    name: str
    count: int


class BankHint(BaseModel):
    # Strictly limited to five categories used by the app/UI
    category: Literal["morphological", "syntactic", "lexical", "phonological", "pragmatic"]
    text: str


class BankSuggestion(BaseModel):
    text: str
    category: Optional[str] = None


class BankItem(BaseModel):
    id: str
    zh: str
    hints: List[BankHint] = []
    suggestions: List[BankSuggestion] = []
    tags: List[str] = []
    difficulty: int = Field(ge=1, le=5)


class CloudBookDetail(BaseModel):
    name: str
    items: List["BankItem"]  # forward ref to BankItem


class CourseBookSummary(BaseModel):
    id: str
    title: str
    summary: Optional[str] = None
    coverImage: Optional[str] = None
    tags: List[str] = []
    difficulty: Optional[int] = Field(default=None, ge=1, le=5)
    itemCount: int


class CourseBookDetail(CourseBookSummary):
    items: List["BankItem"]


class CloudCourseSummary(BaseModel):
    id: str
    title: str
    summary: Optional[str] = None
    coverImage: Optional[str] = None
    tags: List[str] = []
    bookCount: int


class CloudCourseDetail(CloudCourseSummary):
    books: List[CourseBookDetail]


class CloudSearchCourseHit(CloudCourseSummary):
    # Inherit fields directly; kept for explicit typing.
    pass


class CloudSearchBookHit(CourseBookSummary):
    courseId: str


class CloudSearchResponse(BaseModel):
    query: str
    courses: List[CloudSearchCourseHit]
    books: List[CloudSearchBookHit]


# ----- Content Upload DTOs -----

class ContentUploadRequest(BaseModel):
    filename: str
    content: dict  # JSON content of the book or course
    content_type: Literal["book", "course"]


class ContentUploadResult(BaseModel):
    filename: str
    success: bool
    message: str
    content_type: str


class ContentUploadResponse(BaseModel):
    results: List[ContentUploadResult]
    success_count: int
    error_count: int


class BulkUploadFile(BaseModel):
    filename: str
    content: dict
    content_type: Literal["book", "course"]


class BulkUploadRequest(BaseModel):
    files: List[BulkUploadFile]
    reload_after_upload: bool = True


# ----- Prompt management -----

PromptId = Literal[
    "system",
    "deck",
    "chat_turn",
    "chat_research",
    "merge",
    "flashcard_completion",
    "generate_questions",
]


class PromptUploadRequest(BaseModel):
    promptId: PromptId
    content: str


class PromptUploadResult(BaseModel):
    promptId: PromptId
    path: str
    backupPath: Optional[str] = None
    bytesWritten: int


class PromptUploadResponse(BaseModel):
    result: PromptUploadResult


class PromptInfo(BaseModel):
    promptId: PromptId
    path: str


class PromptListResponse(BaseModel):
    prompts: List[PromptInfo]


# ----- Daily push -----

class DailyPushQuestion(BaseModel):
    id: str
    zh: str
    hints: List[BankHint]
    suggestions: List[BankSuggestion] = []
    suggestion: Optional[str] = None
    tags: List[str] = []
    difficulty: int
    referenceEn: str


class DailyPushPullRequest(BaseModel):
    deviceId: str
    date: dt.date
    count: int = Field(ge=1, le=50)


class DailyPushPullResponse(BaseModel):
    requested: int
    delivered: int
    remaining: int
    questions: List[DailyPushQuestion]


# ----- Progress (legacy/minimal) -----

class ProgressRecord(BaseModel):
    completed: bool = False
    attempts: int = 0
    lastScore: Optional[int] = None
    updatedAt: float = Field(default_factory=lambda: __import__("time").time())


class ProgressMarkRequest(BaseModel):
    itemId: str
    deviceId: Optional[str] = None
    score: Optional[int] = None
    completed: bool = True


class ProgressRecordOut(ProgressRecord):
    itemId: str


class ProgressSummary(BaseModel):
    deviceId: str
    completedIds: List[str]
    records: List[ProgressRecordOut]


# ----- Import text (legacy tooling) -----

class ImportRequest(BaseModel):
    text: str
    defaultTag: Optional[str] = None
    replace: bool = False


class ImportResponse(BaseModel):
    imported: int
    errors: List[str] = []


# ----- Deck (flashcards) -----

class DeckKnowledgeItem(BaseModel):
    i: Optional[int] = Field(default=None, description="1-based index of the knowledge point")
    concept: str = Field(..., description="Primary concept (usually Chinese)")
    zh: Optional[str] = Field(default=None, description="Chinese explanation or rationale")
    en: Optional[str] = Field(default=None, description="Representative English sentence or phrase")
    note: Optional[str] = Field(default=None, description="Additional usage note")
    source: Optional[str] = Field(default=None, description="Data source tag, e.g. error/hint")


class DeckMakeRequest(BaseModel):
    name: Optional[str] = "未命名"
    concepts: List[DeckKnowledgeItem]
    model: Optional[str] = None


class DeckCard(BaseModel):
    front: str
    frontNote: Optional[str] = None
    back: str
    backNote: Optional[str] = None


class DeckMakeResponse(BaseModel):
    name: str
    cards: List[DeckCard]


class FlashcardCompletionCard(BaseModel):
    front: str
    frontNote: Optional[str] = None
    back: str
    backNote: Optional[str] = None


class FlashcardCompletionRequest(BaseModel):
    card: FlashcardCompletionCard
    instruction: Optional[str] = None
    deckName: Optional[str] = None
    model: Optional[str] = None


class FlashcardCompletionResponse(BaseModel):
    front: str
    frontNote: Optional[str] = None
    back: str
    backNote: Optional[str] = None


# Resolve forward refs now that BankItem is defined
try:
    CloudBookDetail.model_rebuild()
    CourseBookDetail.model_rebuild()
    CloudCourseDetail.model_rebuild()
except Exception:
    pass
