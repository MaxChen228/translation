"""Generate daily translation questions with Gemini and persist them."""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import random
import sys
import uuid
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
DEFAULT_STRUCTURE_SAMPLE = 3
DEFAULT_TOPIC_POOL = ROOT / "prompts" / "pools" / "topics_pool.json"
DEFAULT_STRUCTURE_POOL = ROOT / "prompts" / "pools" / "structures_pool.json"
DEFAULT_CONTENT_POOL = ROOT / "prompts" / "pools" / "content_pool.json"
DEFAULT_CONTENT_SAMPLE = 3
DEFAULT_DIFFICULTY = 3
DEFAULT_DIFFICULTY_PROMPT_DIR = ROOT / "prompts" / "difficulty"

from app.core.http_client import close_http_client, init_http_client  # noqa: E402
from app.core.settings import get_settings  # noqa: E402
from app.core.tags import VALID_TAGS  # noqa: E402
from app.llm import call_gemini_json  # noqa: E402
from app.question_store import QuestionRecord, QuestionStore  # noqa: E402
from app.schemas import BankHint, BankItem  # noqa: E402
from app.services.prompt_manager import read_prompt  # noqa: E402

ALLOWED_HINT_CATEGORIES = {"morphological", "syntactic", "lexical", "phonological", "pragmatic"}

DIFFICULTY_GUIDES = {
    1: "- 內容貼近日常生活或校園情境，句長約 12–18 個中文字。\n- 使用常見詞彙與簡單句或並列句，盡量少用從屬子句。\n- 著重描述感受、行程或簡單指示，可包含一個時間或地點資訊。",
    2: "- 題材仍為生活或學習情境，但可加入簡單的比較、原因或目的語氣。\n- 允許 1 個從屬子句或簡短的片語補述，句長約 15–22 個中文字。\n- 適度引入常見情態動詞與形容詞子句，但避免大量專業術語。",
    3: "- 題材偏專業或計畫描述，需要使用 1–2 個從屬子句或分詞構句。\n- 句長約 18–26 個中文字，可含條件句或因果連接詞。\n- 需適度運用正式語氣與抽象名詞（如 strategy, initiative）。",
    4: "- 強調正式報告或政策文本，句長約 22–30 個中文字。\n- 至少使用一個複合句結構（名詞子句、被動或分詞構句）並包含數據或條件限定。\n- 詞彙可偏專業，但須確保語意清楚可解釋。",
    5: "- 針對高度專業的議題，句長可達 28–34 個中文字。\n- 需同時運用兩種以上的高階結構（如倒裝、虛擬語氣、複合從句）。\n- 詞彙應展示專業領域知識，並在提示中標明重點語法。",
}

DIFFICULTY_EXAMPLES = {
    1: """[
  {
    \"id\": \"example-d1-001\",
    \"zh\": \"請寫一段簡短介紹你在新社團第一天的感受與收穫。\",
    \"referenceEn\": \"I felt nervous at first, but the members were kind and helped me learn the routine quickly.\",
    \"hints\": [
      {\"category\": \"syntactic\", \"text\": \"以簡單句或 and, but 連接兩個想法，保持過去式一致\"},
      {\"category\": \"lexical\", \"text\": \"描述情緒時可用 basic 形容詞，如 nervous, excited, grateful\"}
    ],
    \"reviewNote\": \"觀察學生是否能用簡單過去式描述事件並補充具體細節。\",
    \"tags\": [\"daily-life\", \"past-simple\", \"opinion\"],
    \"difficulty\": 1
  }
]""",
    2: """[
  {
    \"id\": \"example-d2-001\",
    \"zh\": \"寫一封簡短的電子郵件，向外籍交換生說明校園導覽路線與集合時間。\",
    \"referenceEn\": \"Please meet us at the main gate at 9 a.m.; we will tour the library first and then visit the science labs.\",
    \"hints\": [
      {\"category\": \"syntactic\", \"text\": \"利用分號或 because 連接兩個相關句子\"},
      {\"category\": \"lexical\", \"text\": \"提醒使用禮貌祈使句，如 please remember 或 kindly note\"}
    ],
    \"reviewNote\": \"檢查是否掌握祈使句與時間副詞片語的正確位置。\",
    \"tags\": [\"education\", \"request\", \"present-simple\"],
    \"difficulty\": 2
  }
]""",
    3: """[
  {
    \"id\": \"example-d3-001\",
    \"zh\": \"撰寫一段對董事會的進度簡報，說明新產品試點的成果與下一步計畫。\",
    \"referenceEn\": \"The pilot attracted two hundred beta users within a month, so the marketing team will expand the rollout to three additional cities next quarter.\",
    \"hints\": [
      {\"category\": \"result\", \"text\": \"建議使用 so 或 therefore 描述成果與後續動作\"},
      {\"category\": \"lexical\", \"text\": \"引導學生使用數據搭配名詞化 expressions，如 expansion, adoption rate\"}
    ],
    \"reviewNote\": \"留意是否能正確呈現數據與未來計畫，必要時提醒使用未來式。\",
    \"tags\": [\"business\", \"result\", \"future-simple\"],
    \"difficulty\": 3
  }
]""",
    4: """[
  {
    \"id\": \"example-d4-001\",
    \"zh\": \"向監理機關提交的一段報告，說明公司如何確保資料匿名化並符合隱私規範。\",
    \"referenceEn\": \"To ensure compliance, all customer records are encrypted before analysis, and only staff who have completed the annual privacy training may access the dataset.\",
    \"hints\": [
      {\"category\": \"passive\", \"text\": \"使用被動語態描述既定流程或規範\"},
      {\"category\": \"necessity\", \"text\": \"善用 must, be required to 等字眼指示義務\"}
    ],
    \"reviewNote\": \"觀察學生是否能結合被動語態與情態動詞描述規範。\",
    \"tags\": [\"business\", \"necessity\", \"passive\"],
    \"difficulty\": 4
  }
]""",
    5: """[
  {
    \"id\": \"example-d5-001\",
    \"zh\": \"撰寫一段策略備忘錄，假設城市若未來三年未投資公共運輸，將對碳排與社會公平造成何種影響。\",
    \"referenceEn\": \"Should the city fail to invest in public transit over the next three years, emissions will inevitably rise, and low-income neighborhoods will be further cut off from employment opportunities.\",
    \"hints\": [
      {\"category\": \"conditional\", \"text\": \"建議使用倒裝或虛擬語氣表達假設情境\"},
      {\"category\": \"cause\", \"text\": \"引導學生描述因果與社會影響，適度使用名詞化結構\"}
    ],
    \"reviewNote\": \"確認學生是否能結合虛擬語氣、倒裝與因果銜接詞。\",
    \"tags\": [\"environment\", \"conditional\", \"result\"],
    \"difficulty\": 5
  }
]""",
}


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


def _load_prompt_for_difficulty(level: int, prompt_dir: Optional[str]) -> Template:
    base = Path(prompt_dir).expanduser() if prompt_dir else DEFAULT_DIFFICULTY_PROMPT_DIR
    path = base / f"generate_questions_d{level}.txt"
    if path.exists():
        return Template(path.read_text(encoding="utf-8"))

    if prompt_dir:
        raise SystemExit(f"找不到難度 {level} 的 prompt 檔案：{path}")

    return Template(read_prompt("generate_questions"))


def _matches_difficulty(entry: dict, level: int) -> bool:
    lower = int(entry.get("minDifficulty", 1))
    upper = int(entry.get("maxDifficulty", 5))
    if lower > upper:
        lower, upper = upper, lower
    return lower <= level <= upper


def _resolve_content_pool(level: int, pool_path: Optional[str], sample_count: int) -> List[dict]:
    path = Path(pool_path).expanduser() if pool_path else DEFAULT_CONTENT_POOL
    entries = _load_json_list(path)
    if not entries:
        return []
    filtered = [entry for entry in entries if _matches_difficulty(entry, level)]
    candidate = filtered or entries
    size = max(1, min(sample_count, len(candidate)))
    return random.sample(candidate, size)


def _format_content_briefs(entries: Sequence[dict]) -> str:
    if not entries:
        return "（題材由你自由發揮，但需保持語境完整、結構多樣）"

    lines: List[str] = []
    for entry in entries:
        name = entry.get("name", "題材")
        tags = entry.get("tags") or []
        description = entry.get("description")
        focus = entry.get("focus")
        example = entry.get("exampleZh")
        hint = entry.get("hint")
        min_level = entry.get("minDifficulty", 1)
        max_level = entry.get("maxDifficulty", 5)
        difficulty_text = f"{min_level}-{max_level}" if min_level != max_level else str(min_level)

        bullet = f"- {name}（建議難度 {difficulty_text}；標籤：{', '.join(tags) if tags else '未指定'}）"
        if description:
            bullet += f"：{description}"
        lines.append(bullet)

        if focus:
            lines.append(f"  · 焦點：{focus}")
        if example:
            lines.append(f"  · 中文例句：{example}")
        if hint:
            lines.append(f"  · 提示：{hint}")

    return "\n".join(lines)


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
    content_detail: Sequence[dict],
    prompt_template: Template,
    target_difficulty: int,
    model: Optional[str],
) -> tuple[List[GeneratedQuestion], dict]:
    settings = get_settings()

    topic_text = _format_topics_text(topics_detail)
    structure_text = _format_structures_text(structures_detail)
    content_text = _format_content_briefs(content_detail)
    difficulty_guide = DIFFICULTY_GUIDES.get(target_difficulty, "")
    difficulty_example = DIFFICULTY_EXAMPLES.get(target_difficulty, "[]")

    system_prompt = prompt_template.substitute(
        COUNT=count,
        DATE=question_date.isoformat(),
        TOPICS=topic_text,
        STRUCTURES=structure_text,
        CONTENT_BRIEFS=content_text,
        VALID_TAGS=", ".join(sorted(VALID_TAGS)),
        HINT_CATEGORIES=", ".join(sorted(ALLOWED_HINT_CATEGORIES)),
        TARGET_DIFFICULTY=target_difficulty,
        DIFFICULTY_GUIDE=difficulty_guide,
        DIFFICULTY_EXAMPLE=difficulty_example,
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
        "targetDifficulty": target_difficulty,
        "difficultyGuide": difficulty_guide,
        "contentPool": list(content_detail),
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
    target_difficulty: int,
) -> GenerationOutcome:
    accepted: List[QuestionRecord] = []
    rejected: List[str] = list(extra_errors)
    sequence = 0
    generated_ids: set[str] = set()

    for question in questions:
        if question.difficulty != target_difficulty:
            rejected.append(
                f"題目 {question.id} 難度為 {question.difficulty}，不符合指定 {target_difficulty}"
            )
            continue

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
        sequence += 1
        base_id = f"daily-{question_date.isoformat()}-d{target_difficulty}-{sequence:03d}"
        suffix = f"-{prompt_hash[:4]}" if prompt_hash else ""
        candidate_id = f"{base_id}{suffix}"
        while candidate_id in generated_ids:
            candidate_id = f"{base_id}-{uuid.uuid4().hex[:4]}"
        generated_ids.add(candidate_id)
        item.id = candidate_id

        item_payload = item.model_dump()
        item_payload["id"] = candidate_id
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
    parser.add_argument("--difficulty", type=int, default=DEFAULT_DIFFICULTY, help="指定題目難度（1-5）")
    parser.add_argument("--difficulty-prompt-dir", help="自訂難度專用 prompt 目錄，預設 prompts/difficulty", default=None)
    parser.add_argument("--content-pool", help="題材靈感池 JSON 路徑，預設 prompts/pools/content_pool.json", default=None)
    parser.add_argument("--content-count", type=int, default=None, help="每次抽樣的題材筆數")
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
    args.content_count = _validate_positive(args.content_count, DEFAULT_CONTENT_SAMPLE)

    count = max(1, args.count)
    question_date = _parse_date(args.date)
    target_difficulty = max(1, min(5, args.difficulty or DEFAULT_DIFFICULTY))

    topics_detail = _resolve_topics(args)
    structures_detail = _resolve_structures(args)
    content_detail = _resolve_content_pool(target_difficulty, args.content_pool, args.content_count)
    prompt_template = _load_prompt_for_difficulty(target_difficulty, args.difficulty_prompt_dir)

    try:
        questions, meta = asyncio.run(
            _request_questions(
                count=count,
                question_date=question_date,
                topics_detail=topics_detail,
                structures_detail=structures_detail,
                content_detail=content_detail,
                prompt_template=prompt_template,
                target_difficulty=target_difficulty,
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
        target_difficulty=target_difficulty,
    )

    inserted, duplicates = _persist(outcome.accepted, dry_run=args.dry_run)

    topic_names = [entry.get("name", "") for entry in topics_detail]
    structure_names = [entry.get("name", "") for entry in structures_detail]
    content_names = [entry.get("name", "") for entry in content_detail]

    print(f"生成日期: {question_date.isoformat()}")
    print(f"指定難度: {target_difficulty}")
    print(f"主題取樣: {', '.join(topic_names) if topic_names else '（未指定）'}")
    print(f"句構焦點: {', '.join(structure_names) if structure_names else '（未指定）'}")
    if content_names:
        print(f"題材靈感: {', '.join(content_names)}")
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
