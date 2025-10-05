#!/usr/bin/env python3
"""
標籤驗證腳本 - 檢查題目是否符合標準化標籤體系
"""

import glob
import json
import sys
from pathlib import Path
from typing import Dict, List

# 確保可以匯入 app 套件（腳本通常位於 repo 根目錄）
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.tags import FORBIDDEN_TAGS, VALID_TAGS


class TagValidator:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def validate_file(self, file_path: str) -> Dict:
        """驗證單個文件的標籤"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        file_errors = []
        file_warnings = []

        if 'items' in data:
            for item in data['items']:
                item_id = item.get('id', 'unknown')
                tags = item.get('tags', [])

                # 檢查標籤數量
                if len(tags) < 2:
                    file_errors.append(f"{item_id}: 標籤數量過少 ({len(tags)})，至少需要2個")
                elif len(tags) > 4:
                    file_warnings.append(f"{item_id}: 標籤數量過多 ({len(tags)})，建議不超過4個")

                # 檢查非法標籤
                invalid_tags = []
                forbidden_found = []

                for tag in tags:
                    if tag in FORBIDDEN_TAGS:
                        forbidden_found.append(tag)
                    elif tag not in VALID_TAGS:
                        invalid_tags.append(tag)

                if forbidden_found:
                    file_errors.append(f"{item_id}: 使用禁用標籤 {forbidden_found}")

                if invalid_tags:
                    file_errors.append(f"{item_id}: 使用非標準標籤 {invalid_tags}")

                # 檢查標籤組合邏輯
                self._check_tag_combination_logic(item_id, tags, file_warnings)

        return {
            'file': file_path,
            'errors': file_errors,
            'warnings': file_warnings,
            'total_items': len(data.get('items', []))
        }

    def _check_tag_combination_logic(self, item_id: str, tags: List[str], warnings: List[str]):
        """檢查標籤組合的邏輯性"""

        # 檢查是否有語法結構標籤
        grammar_tags = {tag for tag in tags if tag in {
            "subjunctive", "conditional", "cleft", "inversion", "emphasis",
            "comparative", "superlative", "passive", "modal", "infinitive",
            "gerund", "participle", "relative-clause", "noun-clause",
            "adverb-clause", "as-clause", "complex-sentence", "grammar"
        }}

        if not grammar_tags and len(tags) > 0:
            warnings.append(f"{item_id}: 建議包含至少一個語法結構標籤")

        # 檢查時態標籤重複
        tense_tags = {tag for tag in tags if tag.endswith(('-simple', '-continuous', '-perfect'))}
        if len(tense_tags) > 2:
            warnings.append(f"{item_id}: 時態標籤過多 {list(tense_tags)}")

        # 檢查主題標籤過多
        topic_tags = {tag for tag in tags if tag in {
            "family", "education", "career", "health", "money", "relationship",
            "travel", "food", "sports", "entertainment", "technology",
            "environment", "culture", "business", "academic", "personal",
            "social", "daily-life"
        }}

        if len(topic_tags) > 2:
            warnings.append(f"{item_id}: 主題標籤過多 {list(topic_tags)}，建議不超過2個")

    def validate_directory(self, directory: str) -> Dict:
        """驗證整個目錄的標籤"""
        json_files = glob.glob(f"{directory}/*.json")

        all_results = []
        total_errors = 0
        total_warnings = 0
        total_items = 0

        for file_path in json_files:
            result = self.validate_file(file_path)
            all_results.append(result)
            total_errors += len(result['errors'])
            total_warnings += len(result['warnings'])
            total_items += result['total_items']

        return {
            'results': all_results,
            'summary': {
                'total_files': len(json_files),
                'total_items': total_items,
                'total_errors': total_errors,
                'total_warnings': total_warnings,
                'validation_passed': total_errors == 0
            }
        }

    def generate_report(self, validation_result: Dict) -> str:
        """生成驗證報告"""
        report = ["=" * 60]
        report.append("標籤驗證報告")
        report.append("=" * 60)

        summary = validation_result['summary']
        report.append(f"文件總數: {summary['total_files']}")
        report.append(f"題目總數: {summary['total_items']}")
        report.append(f"錯誤總數: {summary['total_errors']}")
        report.append(f"警告總數: {summary['total_warnings']}")
        report.append(f"驗證結果: {'✅ 通過' if summary['validation_passed'] else '❌ 失敗'}")
        report.append("")

        # 詳細報告
        for result in validation_result['results']:
            if result['errors'] or result['warnings']:
                report.append(f"📁 {result['file']}")

                if result['errors']:
                    report.append("  ❌ 錯誤:")
                    for error in result['errors']:
                        report.append(f"    - {error}")

                if result['warnings']:
                    report.append("  ⚠️  警告:")
                    for warning in result['warnings']:
                        report.append(f"    - {warning}")

                report.append("")

        # 使用統計
        all_tags = set()
        for result in validation_result['results']:
            file_path = result['file']
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for item in data.get('items', []):
                    all_tags.update(item.get('tags', []))
            except:
                continue

        report.append("📊 標籤使用統計:")
        report.append(f"使用中的標籤總數: {len(all_tags)}")

        invalid_in_use = all_tags - VALID_TAGS
        if invalid_in_use:
            report.append(f"❌ 使用中的非標準標籤: {sorted(invalid_in_use)}")

        forbidden_in_use = all_tags & FORBIDDEN_TAGS
        if forbidden_in_use:
            report.append(f"❌ 使用中的禁用標籤: {sorted(forbidden_in_use)}")

        return "\n".join(report)

def main():
    if len(sys.argv) != 2:
        print("用法: python TAG_VALIDATION_SCRIPT.py <books_directory>")
        print("例如: python TAG_VALIDATION_SCRIPT.py data/books")
        sys.exit(1)

    directory = sys.argv[1]
    validator = TagValidator()

    print("🔍 開始驗證標籤體系合規性...")
    result = validator.validate_directory(directory)

    # 生成並顯示報告
    report = validator.generate_report(result)
    print(report)

    # 退出代碼
    sys.exit(0 if result['summary']['validation_passed'] else 1)

if __name__ == "__main__":
    main()
