# Content Workspace

此資料夾儲存雲端題庫與課程的原始 JSON 檔，維護方式如下：

## 結構
```
content/
  books/      # 個別題庫本（原始題目）
  courses/    # 課程定義，可引用 books 或內嵌題目
  decks/      # 雲端單字卡（選用）
```

所有檔案均為 UTF-8 編碼的 JSON；建議複製既有檔案當模板再修改。

## 編輯流程
1. 在 `books/` 或 `courses/` 編輯 JSON（課程欄位請參考 [`docs/course-authoring.md`](docs/course-authoring.md)）。
2. 建議執行 `jq` 或編輯器格式化，保持縮排一致。
3. 修改完成後執行同步腳本：
   ```bash
   cd ../translation-backend
   ./scripts/sync_content.py content \
     --backend-url http://127.0.0.1:8080 \
     --token $CONTENT_ADMIN_TOKEN
   ```
   - `--backend-url` 指向後端服務。
   - `--token` 需與後端環境變數 `CONTENT_ADMIN_TOKEN` 相同；若未設定 token，可省略。
4. 腳本會自動：
   - 檢查 JSON 是否有效。
   - 將檔案複製到後端 `CONTENT_DIR`（預設 `translation-backend/data`）。
   - 呼叫 `/admin/content/reload` 讓新資料立即生效。

## 常見注意事項
- 題庫 `items[].hints[].category` 必須是 `morphological|syntactic|lexical|phonological|pragmatic` 其中之一。
- 課程若引用既有題庫，請在 `source.id` 填入對應的 book `id`。
- 若需要專屬於課程的題目，可在課程 JSON 內直接放 `items`，格式與書本一致。
- 建議同步前先備份：`rsync -a content/ backup/content-$(date +%Y%m%d%H%M)/`。
