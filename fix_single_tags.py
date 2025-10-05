#!/usr/bin/env python3
"""
修復只有單個標籤的項目
"""

import glob
import json


def fix_single_tags(directory):
    """修復只有單個標籤的項目"""

    json_files = glob.glob(f"{directory}/*.json")

    for file_path in json_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        modified = False

        if 'items' in data:
            for item in data['items']:
                tags = item.get('tags', [])

                # 如果只有一個標籤，需要添加更多標籤
                if len(tags) == 1:
                    current_tag = tags[0]

                    # 基於語境添加適當的標籤
                    if current_tag == "grammar":
                        # 添加語意主題標籤
                        zh_text = item.get('zh', '').lower()
                        if any(word in zh_text for word in ['家', '父', '母', '子', '女', '妻', '夫']):
                            tags.append("family")
                        elif any(word in zh_text for word in ['學', '老師', '學生', '課']):
                            tags.append("education")
                        elif any(word in zh_text for word in ['工作', '職', '公司', '員工']):
                            tags.append("career")
                        elif any(word in zh_text for word in ['病', '醫', '健康', '治療']):
                            tags.append("health")
                        else:
                            tags.append("personal")

                    elif current_tag == "emphasis":
                        tags.append("grammar")

                    elif current_tag == "purpose":
                        tags.append("grammar")

                    elif current_tag == "too-to":
                        tags.append("grammar")

                    elif current_tag == "comparative":
                        tags.append("grammar")

                    elif current_tag == "advice":
                        tags.append("personal")

                    elif current_tag == "inversion":
                        tags.append("grammar")

                    else:
                        # 默認添加語法標籤
                        tags.append("grammar")

                    item['tags'] = tags
                    modified = True
                    print(f"Fixed {item.get('id', 'unknown')}: {current_tag} -> {tags}")

        # 保存修改後的文件
        if modified:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"Updated {file_path}")

if __name__ == "__main__":
    fix_single_tags("data/books")
