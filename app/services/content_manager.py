from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from app.core.settings import get_settings
from app.core.logging import logger
from app.schemas import BankHint, BankItem, BankSuggestion, ContentUploadResult


# 標準標籤列表 - 與 TAG_VALIDATION_SCRIPT.py 保持一致
VALID_TAGS = {
    # 語法結構類 (Grammar Structures)
    "subjunctive", "conditional", "cleft", "inversion", "emphasis",
    "comparative", "superlative", "passive", "modal", "infinitive",
    "gerund", "participle", "relative-clause", "noun-clause",
    "adverb-clause", "as-clause", "complex-sentence", "grammar",

    # 特定語法結構類 (Specific Structures)
    "as-adjective-as", "as-soon-as", "as-long-as", "as-far-as",
    "the-more-the-more", "would-rather", "had-better", "used-to",
    "be-used-to", "too-to", "so-that", "such-that", "not-only-but-also",
    "either-or", "neither-nor",

    # 語法功能類 (Functions)
    "advice", "warning", "request", "permission", "prohibition",
    "suggestion", "offer", "invitation", "complaint", "apology",
    "opinion", "preference", "regret", "possibility", "necessity",
    "ability", "purpose", "result", "cause",

    # 語意主題類 (Semantic Themes)
    "family", "education", "career", "health", "money", "relationship",
    "travel", "food", "sports", "entertainment", "technology",
    "environment", "culture", "business", "academic", "personal",
    "social", "daily-life",

    # 時態語態類 (Tenses)
    "present-simple", "present-continuous", "present-perfect",
    "past-simple", "past-continuous", "past-perfect",
    "future-simple", "future-perfect"
}


class ContentManager:
    """管理內容文件的上傳、驗證和儲存"""

    def __init__(self):
        settings = get_settings()
        if os.path.isabs(settings.CONTENT_DIR):
            self.base_dir = Path(settings.CONTENT_DIR)
        else:
            here = Path(__file__).resolve().parent
            backend_dir = here.parent.parent
            self.base_dir = (backend_dir / settings.CONTENT_DIR).resolve()

        # 確保目錄存在
        (self.base_dir / "books").mkdir(parents=True, exist_ok=True)
        (self.base_dir / "courses").mkdir(parents=True, exist_ok=True)
        (self.base_dir / "decks").mkdir(parents=True, exist_ok=True)

    def upload_content(self, filename: str, content: dict, content_type: str) -> ContentUploadResult:
        """上傳單個內容文件"""
        try:
            # 驗證內容格式
            validation_error = self._validate_content(content, content_type, filename)
            if validation_error:
                return ContentUploadResult(
                    filename=filename,
                    success=False,
                    message=f"驗證失敗: {validation_error}",
                    content_type=content_type
                )

            # 備份現有文件（如果存在）
            target_path = self._get_target_path(filename, content_type)
            backup_path = None
            if target_path.exists():
                backup_path = self._create_backup(target_path)

            try:
                # 寫入新內容
                self._write_content_file(target_path, content)

                logger.info("content_uploaded", extra={
                    "upload_filename": filename,
                    "content_type": content_type,
                    "target_path": str(target_path)
                })

                return ContentUploadResult(
                    filename=filename,
                    success=True,
                    message="上傳成功",
                    content_type=content_type
                )

            except Exception as e:
                # 如果寫入失敗，恢復備份
                if backup_path and backup_path.exists():
                    shutil.move(str(backup_path), str(target_path))
                raise e

        except Exception as e:
            logger.error("content_upload_error", extra={
                "upload_filename": filename,
                "content_type": content_type,
                "error": str(e)
            })
            return ContentUploadResult(
                filename=filename,
                success=False,
                message=f"上傳失敗: {str(e)}",
                content_type=content_type
            )

    def _validate_content(self, content: dict, content_type: str, filename: str) -> Optional[str]:
        """驗證內容格式和標籤"""
        try:
            if content_type == "book":
                return self._validate_book_content(content)
            elif content_type == "course":
                return self._validate_course_content(content)
            else:
                return f"不支援的內容類型: {content_type}"
        except Exception as e:
            return f"驗證過程發生錯誤: {str(e)}"

    def _validate_book_content(self, content: dict) -> Optional[str]:
        """驗證題庫本內容"""
        # 檢查必要字段
        if "items" not in content:
            return "缺少 items 字段"

        items = content.get("items", [])
        if not isinstance(items, list):
            return "items 必須是列表"

        # 驗證每個題目項目
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                return f"項目 {i} 必須是物件"

            # 檢查必要字段
            if "zh" not in item:
                return f"項目 {i} 缺少 zh 字段"

            # 驗證 hints
            hints = item.get("hints", [])
            if hints:
                for j, hint in enumerate(hints):
                    if "category" not in hint:
                        return f"項目 {i} 的提示 {j} 缺少 category 字段"
                    if hint["category"] not in ["morphological", "syntactic", "lexical", "phonological", "pragmatic"]:
                        return f"項目 {i} 的提示 {j} category 值無效: {hint['category']}"

            # 驗證標籤
            tags = item.get("tags", [])
            if tags:
                invalid_tags = [tag for tag in tags if tag not in VALID_TAGS]
                if invalid_tags:
                    return f"項目 {i} 包含無效標籤: {', '.join(invalid_tags)}"

            # 驗證 difficulty
            difficulty = item.get("difficulty", 1)
            if not isinstance(difficulty, int) or difficulty < 1 or difficulty > 5:
                return f"項目 {i} 的 difficulty 必須是 1-5 之間的整數"

            # 嘗試創建 BankItem 來驗證格式
            try:
                hint_objs = [BankHint(**hint) for hint in hints]
                sugg_objs = [BankSuggestion(**sugg) for sugg in item.get("suggestions", [])]
                BankItem(
                    id=item.get("id") or str(uuid.uuid4()),
                    zh=item.get("zh", ""),
                    hints=hint_objs,
                    suggestions=sugg_objs,
                    tags=tags,
                    difficulty=difficulty,
                )
            except Exception as e:
                return f"項目 {i} 格式驗證失敗: {str(e)}"

        return None

    def _validate_course_content(self, content: dict) -> Optional[str]:
        """驗證課程內容"""
        # 檢查必要字段
        required_fields = ["id", "title"]
        for field in required_fields:
            if field not in content:
                return f"缺少必要字段: {field}"

        # 驗證 books 字段
        books = content.get("books", [])
        if not isinstance(books, list):
            return "books 必須是列表"

        for i, book in enumerate(books):
            if not isinstance(book, dict):
                return f"書籍 {i} 必須是物件"

            # 檢查必要字段
            required_book_fields = ["id", "title"]
            for field in required_book_fields:
                if field not in book:
                    return f"書籍 {i} 缺少必要字段: {field}"

            # 如果有 source 字段，檢查格式
            if "source" in book:
                source = book["source"]
                if not isinstance(source, dict) or "id" not in source:
                    return f"書籍 {i} 的 source 格式無效"

        return None

    def _get_target_path(self, filename: str, content_type: str) -> Path:
        """獲取目標文件路徑，並確保不會跳出指定目錄"""
        if not filename or not filename.strip():
            raise ValueError("檔名不可為空")

        clean_name = filename.strip()
        separators = [os.path.sep]
        if os.path.altsep:
            separators.append(os.path.altsep)
        if any(sep in clean_name for sep in separators):
            raise ValueError("檔名不可包含路徑")

        if clean_name in {".", ".."}:
            raise ValueError("檔名不可為保留字")

        if not clean_name.endswith(".json"):
            clean_name += ".json"

        target_dir = {
            "book": self.base_dir / "books",
            "course": self.base_dir / "courses",
        }.get(content_type)

        if target_dir is None:
            raise ValueError(f"不支援的內容類型: {content_type}")

        target_dir.mkdir(parents=True, exist_ok=True)

        target_path = (target_dir / clean_name).resolve()
        if target_dir.resolve() not in target_path.parents:
            raise ValueError("檔名解析結果不合法")

        return target_path

    def _create_backup(self, file_path: Path) -> Path:
        """創建文件備份"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = file_path.with_suffix(file_path.suffix + f".backup_{timestamp}")
        shutil.copy2(str(file_path), str(backup_path))
        return backup_path

    def _write_content_file(self, file_path: Path, content: dict) -> None:
        """寫入內容文件"""
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # 寫入文件
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)

    def list_content_files(self, content_type: str) -> List[str]:
        """列出指定類型的內容文件"""
        if content_type == "book":
            subdir = self.base_dir / "books"
        elif content_type == "course":
            subdir = self.base_dir / "courses"
        else:
            return []

        if not subdir.exists():
            return []

        return [f.name for f in subdir.iterdir() if f.suffix == ".json"]

    def get_content_stats(self) -> Dict[str, int]:
        """獲取內容統計信息"""
        return {
            "books": len(self.list_content_files("book")),
            "courses": len(self.list_content_files("course")),
        }


def get_content_manager() -> ContentManager:
    """獲取內容管理器實例"""
    return ContentManager()
