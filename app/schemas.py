from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


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


class CorrectRequest(BaseModel):
    zh: str
    en: str
    bankItemId: Optional[str] = None
    deviceId: Optional[str] = None
    hints: Optional[List[InputHintDTO]] = None
    suggestion: Optional[str] = None
    model: Optional[str] = None


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


class ChatResearchResponse(BaseModel):
    title: str
    summary: str
    sourceZh: Optional[str] = None
    attemptEn: Optional[str] = None
    correctedEn: str
    errors: List[ErrorDTO]


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

class DeckMakeItem(BaseModel):
    zh: Optional[str] = None
    en: Optional[str] = None
    corrected: Optional[str] = None
    span: Optional[str] = None
    suggestion: Optional[str] = None
    explainZh: Optional[str] = None
    type: Optional[str] = None


class DeckMakeRequest(BaseModel):
    name: Optional[str] = "未命名"
    items: List[DeckMakeItem]
    model: Optional[str] = None


class DeckCard(BaseModel):
    front: str
    frontNote: Optional[str] = None
    back: str
    backNote: Optional[str] = None


class DeckMakeResponse(BaseModel):
    name: str
    cards: List[DeckCard]


# Resolve forward refs now that BankItem is defined
try:
    CloudBookDetail.model_rebuild()
except Exception:
    pass
