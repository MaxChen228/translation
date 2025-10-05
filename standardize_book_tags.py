#!/usr/bin/env python3
"""
批量標準化書籍標籤
"""

import glob
import json
import os

from tag_mapping import standardize_tags


def standardize_book_tags(input_dir, output_dir=None):
    """標準化指定目錄下所有書籍文件的標籤"""

    if output_dir is None:
        output_dir = input_dir

    # 確保輸出目錄存在
    os.makedirs(output_dir, exist_ok=True)

    # 處理所有 JSON 文件
    json_files = glob.glob(os.path.join(input_dir, "*.json"))

    total_files = len(json_files)
    processed_files = 0
    total_items = 0
    total_tags_before = 0
    total_tags_after = 0

    print(f"找到 {total_files} 個 JSON 文件需要處理...")

    for file_path in json_files:
        try:
            # 讀取原始文件
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            file_items = 0
            file_tags_before = 0
            file_tags_after = 0

            # 處理每個項目的標籤
            if 'items' in data:
                for item in data['items']:
                    if 'tags' in item:
                        old_tags = item['tags']
                        new_tags = standardize_tags(old_tags)

                        # 更新標籤
                        item['tags'] = new_tags

                        # 統計
                        file_items += 1
                        file_tags_before += len(old_tags)
                        file_tags_after += len(new_tags)

                        # 顯示變更
                        if old_tags != new_tags:
                            print(f"  {item.get('id', 'unknown')}: {old_tags} -> {new_tags}")

            # 生成輸出文件路徑
            filename = os.path.basename(file_path)
            output_file = os.path.join(output_dir, filename)

            # 寫入更新後的文件
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            processed_files += 1
            total_items += file_items
            total_tags_before += file_tags_before
            total_tags_after += file_tags_after

            print(f"✓ 處理完成: {filename} ({file_items} 項目, {file_tags_before}->{file_tags_after} 標籤)")

        except Exception as e:
            print(f"✗ 處理失敗: {file_path} - {str(e)}")

    print(f"\n=== 處理摘要 ===")
    print(f"處理文件: {processed_files}/{total_files}")
    print(f"處理項目: {total_items}")
    print(f"標籤數量: {total_tags_before} -> {total_tags_after}")
    print(f"標籤減少: {total_tags_before - total_tags_after} ({(total_tags_before - total_tags_after)/total_tags_before*100:.1f}%)")

def analyze_tag_changes(input_dir):
    """分析標籤變更統計"""
    json_files = glob.glob(os.path.join(input_dir, "*.json"))

    old_tag_count = {}
    new_tag_count = {}

    for file_path in json_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if 'items' in data:
            for item in data['items']:
                if 'tags' in item:
                    old_tags = item['tags']
                    new_tags = standardize_tags(old_tags)

                    for tag in old_tags:
                        old_tag_count[tag] = old_tag_count.get(tag, 0) + 1

                    for tag in new_tags:
                        new_tag_count[tag] = new_tag_count.get(tag, 0) + 1

    print(f"\n=== 標籤變更分析 ===")
    print(f"原始標籤種類: {len(old_tag_count)}")
    print(f"標準化後標籤種類: {len(new_tag_count)}")
    print(f"標籤種類減少: {len(old_tag_count) - len(new_tag_count)} ({(len(old_tag_count) - len(new_tag_count))/len(old_tag_count)*100:.1f}%)")

    print(f"\n最常用的標準化標籤 (前20):")
    sorted_tags = sorted(new_tag_count.items(), key=lambda x: x[1], reverse=True)
    for tag, count in sorted_tags[:20]:
        print(f"  {tag}: {count}")

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python standardize_book_tags.py <books_directory> [output_directory]")
        print("例如: python standardize_book_tags.py data/books data/books_standardized")
        sys.exit(1)

    input_dir = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    print("=== 分析現有標籤 ===")
    analyze_tag_changes(input_dir)

    print(f"\n=== 開始標準化處理 ===")
    standardize_book_tags(input_dir, output_dir)