"""Generate daily translation questions with Gemini and persist them."""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Iterable, List, Optional, Sequence

from pydantic import BaseModel, Field, ValidationError

# Ensure repository root on sys.path when executed as a script.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_TOPIC_SAMPLE = 4
DEFAULT_STRUCTURE_SAMPLE = 2
DEFAULT_TOPIC_POOL = ROOT / "prompts" / "pools" / "topics_pool.json"
DEFAULT_STRUCTURE_POOL = ROOT / "prompts" / "pools" / "structures_pool.json"

from app.core.http_client import close_http_client, init_http_client  # noqa: E402
from app.core.settings import get_settings  # noqa: E402
from app.core.tags import VALID_TAGS  # noqa: E402
from app.llm import call_gemini_json  # noqa: E402
from app.question_store import QuestionRecord, QuestionStore  # noqa: E402
from app.schemas import BankHint, BankItem  # noqa: E402
from app.services.prompt_manager import read_prompt  # noqa: E402

ALLOWED_HINT_CATEGORIES = {"morphological", "syntactic", "lexical", "phonological", "pragmatic"}


def _load_json_list(path: Path) -> List[dict]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"找不到池子檔案：{path}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"池子檔案 JSON 解析失敗：{path} -> {exc}") from exc
    if not isinstance(data, list):
        raise SystemExit(f"池子檔案必須是陣列：{path}")
    return [entry for entry in data if isinstance(entry, dict)]


def _normalize_manual_list(raw: str) -> List[str]:
    if not raw:
        return []
    return [token.strip() for token in raw.split(",") if token.strip()]


def _sample_entries(pool: Sequence[dict], count: int) -> List[dict]:
    if not pool:
        raise SystemExit("池子為空，無法抽樣題材")
    size = max(1, min(count, len(pool)))
    return random.sample(pool, size)


def _resolve_topics(args: argparse.Namespace) -> List[dict]:
    manual = _normalize_manual_list(args.topics)
    if manual:
        return [{"name": name, "tags": [], "description": None} for name in manual]
    pool_path = Path(args.topic_pool).expanduser() if args.topic_pool else DEFAULT_TOPIC_POOL
    topics_pool = _load_json_list(pool_path)
    sample_count = args.topic_count or DEFAULT_TOPIC_SAMPLE
    return _sample_entries(topics_pool, sample_count)


def _resolve_structures(args: argparse.Namespace) -> List[dict]:
    manual = _normalize_manual_list(args.structures)
    if manual:
        return [{"name": name, "pattern": "", "focus": None, "tags": []} for name in manual]
    pool_path = Path(args.structure_pool).expanduser() if args.structure_pool else DEFAULT_STRUCTURE_POOL
    structures_pool = _load_json_list(pool_path)
    sample_count = args.structure_count or DEFAULT_STRUCTURE_SAMPLE
    return _sample_entries(structures_pool, sample_count)


def _format_topics_text(entries: Sequence[dict]) -> str:
    if not entries:
        return "（請自行挑選多樣主題）"
    parts: List[str] = []
    for entry in entries:
        name = entry.get("name", "")
        tags = entry.get("tags") or []
        description = entry.get("description")
        pieces = [name]
        if tags:
            pieces.append(f"標籤：{', '.join(tags)}")
        if description:
            pieces.append(str(description))
        parts.append(" / ".join(filter(None, pieces)))
    return "； ".join(parts)


def _format_structures_text(entries: Sequence[dict]) -> str:
    if not entries:
        return "（請自行挑選多種句構）"
    parts: List[str] = []
    for entry in entries:
        name = entry.get("name", "")
        pattern = entry.get("pattern")
        focus = entry.get("focus")
        segments = [name]
        if pattern:
            segments.append(str(pattern))
        if focus:
            segments.append(str(focus))
        parts.append(" / ".join(filter(None, segments)))
    return "； ".join(parts)


def _collect_tag_suggestions(topics_detail: Sequence[dict], structures_detail: Sequence[dict]) -> List[str]:
    tags: set[str] = set()
    for entry in topics_detail:
        tags.update(entry.get("tags") or [])
    for entry in structures_detail:
        tags.update(entry.get("tags") or [])
    return sorted(tags)


class GeneratedQuestion(BaseModel):
    id: str
    zh: str
    referenceEn: str = Field(alias="referenceEn")
    hints: List[BankHint]
    reviewNote: Optional[str] = None
    tags: List[str]
    difficulty: int = Field(ge=1, le=5)

    model_config = {
        "extra": "allow",
        "populate_by_name": True,
    }

    def to_bank_item(self) -> BankItem:
        return BankItem(
            id=self.id,
            zh=self.zh.strip(),
            hints=self.hints,
            reviewNote=(self.reviewNote or None),
            tags=[t.strip() for t in self.tags],
            difficulty=self.difficulty,
        )


@dataclass
class GenerationOutcome:
    accepted: List[QuestionRecord]
    rejected: List[str]


async def _request_questions(
    *,
    count: int,
    question_date: dt.date,
    topics_detail: Sequence[dict],
    structures_detail: Sequence[dict],
    model: Optional[str],
) -> tuple[List[GeneratedQuestion], dict]:
    settings = get_settings()
    prompt_template = Template(read_prompt("generate_questions"))

    topic_text = _format_topics_text(topics_detail)
    structure_text = _format_structures_text(structures_detail)
    system_prompt = prompt_template.substitute(
        COUNT=count,
        DATE=question_date.isoformat(),
        TOPICS=topic_text,
        STRUCTURES=structure_text,
        VALID_TAGS=", ".join(sorted(VALID_TAGS)),
        HINT_CATEGORIES=", ".join(sorted(ALLOWED_HINT_CATEGORIES)),
    )

    payload = {
        "date": question_date.isoformat(),
        "count": count,
        "topics": [entry.get("name", "") for entry in topics_detail],
        "topicDetails": topics_detail,
        "structures": structures_detail,
        "structureNames": [entry.get("name", "") for entry in structures_detail],
        "expectedFields": [
            "id",
            "zh",
            "referenceEn",
            "hints",
            "reviewNote",
            "tags",
            "difficulty",
        ],
        "validTags": sorted(VALID_TAGS),
        "hintCategories": sorted(ALLOWED_HINT_CATEGORIES),
        "tagSuggestions": _collect_tag_suggestions(topics_detail, structures_detail),
    }
    structure_hints = [entry.get("hint") for entry in structures_detail if entry.get("hint")]
    if structure_hints:
        payload["structureHints"] = structure_hints

    await init_http_client()
    try:
        response_obj, usage = await call_gemini_json(
            system_prompt,
            json.dumps(payload, ensure_ascii=False),
            model=model or settings.GEMINI_MODEL,
        )
    finally:
        await close_http_client()

    if not isinstance(response_obj, list):
        raise RuntimeError("LLM 回應格式錯誤：根節點應為陣列")

    parsed: List[GeneratedQuestion] = []
    errors: List[str] = []
    for idx, raw in enumerate(response_obj, start=1):
        try:
            parsed.append(GeneratedQuestion.model_validate(raw))
        except ValidationError as exc:
            errors.append(f"題目 {idx} 驗證失敗：{exc}")

    return parsed, {
        "system_prompt": system_prompt,
        "usage": usage,
        "errors": errors,
    }


def _filter_questions(
    *,
    question_date: dt.date,
    model: str,
    prompt_hash: str,
    questions: Iterable[GeneratedQuestion],
    extra_errors: Iterable[str],
) -> GenerationOutcome:
    accepted: List[QuestionRecord] = []
    rejected: List[str] = list(extra_errors)

    for question in questions:
        item = question.to_bank_item()

        if not item.zh.strip():
            rejected.append(f"題目 {item.id} 中文原文為空")
            continue
        if len(item.hints) < 2:
            rejected.append(f"題目 {item.id} 提示數量不足（至少 2 個）")
            continue
        if len(item.tags) < 2:
            rejected.append(f"題目 {item.id} 標籤數量不足：{item.tags}")
            continue
        invalid_tags = [tag for tag in item.tags if tag not in VALID_TAGS]
        if invalid_tags:
            rejected.append(f"題目 {item.id} 含非法標籤：{invalid_tags}")
            continue
        if not question.referenceEn.strip():
            rejected.append(f"題目 {item.id} 缺少 referenceEn")
            continue
        item_payload = item.model_dump()
        item_payload["referenceEn"] = question.referenceEn.strip()
        record = QuestionRecord.from_payload(
            question_date=question_date,
            item=item_payload,
            reference_en=question.referenceEn.strip(),
            model=model,
            prompt_hash=prompt_hash,
        )
        accepted.append(record)

    return GenerationOutcome(accepted=accepted, rejected=rejected)


def _persist(accepted: List[QuestionRecord], *, dry_run: bool) -> tuple[int, int]:
    if dry_run or not accepted:
        return 0, 0

    settings = get_settings()
    store = QuestionStore(
        db_url=settings.QUESTION_DB_URL,
        db_path=settings.QUESTION_DB_PATH,
    )
    try:
        summary = store.save_many(accepted)
    finally:
        store.close()
    return summary.inserted, summary.duplicates


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Generate daily translation questions")
    parser.add_argument("--date", help="目標日期 (YYYY-MM-DD)", default=dt.date.today().isoformat())
    parser.add_argument("--count", type=int, default=settings.GENERATOR_DEFAULT_COUNT, help="生成題目數量")
    parser.add_argument("--model", help="覆寫預設 Gemini 模型", default=None)
    parser.add_argument("--topics", help="逗號分隔的主題提示，留空改由池子隨機", default="")
    parser.add_argument("--structures", help="逗號分隔的句構提示，留空改由池子隨機", default="")
    parser.add_argument("--topic-pool", help="主題池 JSON 路徑，預設 prompts/pools/topics_pool.json", default=None)
    parser.add_argument("--structure-pool", help="句構池 JSON 路徑，預設 prompts/pools/structures_pool.json", default=None)
    parser.add_argument("--topic-count", type=int, default=None, help="隨機抽樣主題數量")
    parser.add_argument("--structure-count", type=int, default=None, help="隨機抽樣句構數量")
    parser.add_argument("--dry-run", action="store_true", help="僅輸出結果，不寫入資料庫")
    return parser.parse_args()


def _validate_positive(value: int, fallback: int) -> int:
    return fallback if value is None or value <= 0 else value


def _parse_date(raw: str) -> dt.date:
    try:
        return dt.date.fromisoformat(raw)
    except ValueError as exc:
        raise SystemExit(f"--date 解析失敗: {exc}") from exc


def main() -> None:
    args = parse_args()
    args.topic_count = _validate_positive(args.topic_count, DEFAULT_TOPIC_SAMPLE)
    args.structure_count = _validate_positive(args.structure_count, DEFAULT_STRUCTURE_SAMPLE)

    count = max(1, args.count)
    question_date = _parse_date(args.date)

    topics_detail = _resolve_topics(args)
    structures_detail = _resolve_structures(args)

    try:
        questions, meta = asyncio.run(
            _request_questions(
                count=count,
                question_date=question_date,
                topics_detail=topics_detail,
                structures_detail=structures_detail,
                model=args.model,
            )
        )
    except Exception as exc:
        raise SystemExit(f"呼叫 LLM 失敗: {exc}") from exc

    usage = meta["usage"]
    system_prompt = meta["system_prompt"]
    prompt_hash = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()
    outcome = _filter_questions(
        question_date=question_date,
        model=usage.model,
        prompt_hash=prompt_hash,
        questions=questions,
        extra_errors=meta["errors"],
    )

    inserted, duplicates = _persist(outcome.accepted, dry_run=args.dry_run)

    topic_names = [entry.get("name", "") for entry in topics_detail]
    structure_names = [entry.get("name", "") for entry in structures_detail]

    print(f"生成日期: {question_date.isoformat()}")
    print(f"主題取樣: {', '.join(topic_names) if topic_names else '（未指定）'}")
    print(f"句構焦點: {', '.join(structure_names) if structure_names else '（未指定）'}")
    print(f"LLM 模型: {usage.model}")
    print(f"輸入 tokens: {usage.input_tokens} / 輸出 tokens: {usage.output_tokens}")
    print(f"成功解析題目: {len(outcome.accepted)}")
    print(f"跳過題目: {len(outcome.rejected)}")
    if args.dry_run:
        print("[Dry run] 未寫入資料庫")
    else:
        print(f"寫入資料庫: 新增 {inserted} 題，忽略 {duplicates} 題 (重複)")

    if outcome.rejected:
        print("\n以下題目未採用:")
        for msg in outcome.rejected:
            print(f" - {msg}")

    if args.dry_run and outcome.accepted:
        sample = outcome.accepted[0]
        print("\n預覽第一題:")
        print(json.dumps(sample.raw, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
