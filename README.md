# translation-backend

FastAPI 後端，為 iOS App 提供中英翻譯批改、雲端題庫/卡片瀏覽、單字卡產生與聊天研究等 API。

Repo（GitHub）：https://github.com/MaxChen228/translation

## 功能總覽
- 批改（`POST /correct`）：回傳修正版、分數與錯誤清單（使用 Gemini）。
- 雲端資料（唯讀）：`/cloud/books*`、`/cloud/decks*`、`/cloud/courses*` 與 `/cloud/search` 從 `data/` 提供精選題庫、卡片集、課程與全文檢索。
- 錯誤合併（`POST /correct/merge`）：將多個錯誤合併為單一卡片，對應 iOS 捏合手勢流程。
- 單字卡產生（`POST /make_deck`）：由 Saved JSON 彙整卡片，支援變體括號語法輸出。
- 深入研究 chat 流程：`POST /chat/respond` 進行多輪確認、`POST /chat/research` 產出研究詞彙列表（term/explanation/context/type）。
- 健康檢查（`GET /healthz`）。

## 環境需求
- Python 3.11+

## 快速開始（本機）
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 本機啟動（預設 0.0.0.0:8080）
export HOST=0.0.0.0
export PORT=8080
uvicorn main:app --reload --host "$HOST" --port "$PORT" --limit-max-request-size 5242880

# 健康檢查
curl -s http://127.0.0.1:8080/healthz | jq .
```

預設情況下，若未設定 API Key，`/healthz` 會顯示 `{"status": "no_key"}`。

## 環境變數
- `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`：Gemini API 金鑰（必要，擇一即可）。
- `GEMINI_MODEL`：預設模型名稱（預設 `gemini-2.5-flash`）。
- `ALLOWED_MODELS`：允許的模型白名單（逗號分隔，預設為 `gemini-2.5-pro, gemini-2.5-flash, gemini-2.5-flash-lite`）。
- `CONTENT_DIR`：雲端瀏覽內容根目錄（預設 `./data`）。
- `USAGE_DB_PATH`：LLM 用量統計的 SQLite 檔案路徑（預設 `data/usage.db`）。
- `PROMPT_FILE`：批改系統提示檔路徑（預設 `prompts/prompt.txt`）。
- `DECK_PROMPT_FILE`：單字卡生成提示檔路徑（預設 `prompts/prompt_deck.txt`）。
- `CHAT_TURN_PROMPT_FILE`：聊天回合提示檔路徑（預設 `prompts/prompt_chat_turn.txt`）。
- `CHAT_RESEARCH_PROMPT_FILE`：聊天研究提示檔路徑（預設 `prompts/prompt_chat_research.txt`）。
- `MERGE_PROMPT_FILE`：錯誤合併提示檔路徑（預設 `prompts/prompt_merge.txt`）。
- `DECK_DEBUG_LOG`：控制是否輸出 `/make_deck` 呼叫摘要，預設 `1`（啟用）；設為 `0`/`false` 可停用。
- `LLM_TEMPERATURE`、`LLM_TOP_P`、`LLM_TOP_K`、`LLM_MAX_OUTPUT_TOKENS`：生成參數（預設 0.1 / 0.1 / 1 / 8192）。
- `LLM_LOG_MODE`：控制是否輸出 LLM 請求/回應（`off`｜`input`｜`output`｜`both`，預設 `both`）。
- `LLM_LOG_PRETTY`：是否以縮排行輸出 LLM JSON 日誌（預設 `true`）。
- `LOG_LEVEL`：一般日誌層級（預設 `INFO`）。
- `HOST`、`PORT`：本機啟動位址與連接埠（`uvicorn` 參數也可覆蓋）。

將範例複製為 `.env`（可選）：
```bash
cp .env.example .env
```

## API 介面

### POST /correct
請求（JSON）：
```json
{
  "zh": "中文原文",
  "en": "我的英文",
  "bankItemId": "可選",
  "deviceId": "可選",
  "hints": [ { "category": "morphological", "text": "過去式" } ],
  "suggestion": "（教師建議/期待寫法，供批改者參考）",
  "model": "gemini-2.5-pro | gemini-2.5-flash"  // 可選，覆蓋預設模型
}
```
回應（JSON）：
```json
{
  "corrected": "修正版英文",
  "score": 92,
  "errors": [
    {
      "id": "uuid",
      "span": "go",
      "type": "morphological",
      "explainZh": "應使用過去式。",
      "suggestion": "went",
      "hints": { "before": "I ", "after": " to", "occurrence": 1 }
    }
  ]
}
```

### GET /cloud/courses、GET /cloud/courses/{id}
- 從 `data/courses/*.json` 提供課程清單與詳情，每個課程可包含多個題庫本。
- 課程中的題庫可引用 `data/books/*.json` 或內嵌題目，回傳時會包含完整 `items` 以供預覽/下載。

### POST /admin/content/reload
- 重新載入 `CONTENT_DIR` 下的資料，讓課程/題庫更新即時生效。
- 同步清空 LLM 提示快取，更新 `prompts/` 檔案後無需重啟即可套用。
- 需在 `X-Content-Token` header 帶入 `CONTENT_ADMIN_TOKEN`，未設定 token 時表示允許任意呼叫（僅建議在本機開發）。

### GET /cloud/books、GET /cloud/books/{name}
- 從 `data/books/*.json` 提供唯讀題庫本清單與內容（仍保留給舊版 App 使用）。
- 注意：`items[].hints[].category` 僅允許五種值（morphological | syntactic | lexical | phonological | pragmatic）。
  若檔案中存在其他分類值，後端會拒絕載入該內容（於啟動時記錄錯誤並略過該書）。

### GET /cloud/decks、GET /cloud/decks/{id}
- 從 `data/decks/*.json` 提供唯讀卡片集清單與內容。

### POST /make_deck
請求（JSON）：
```json
{
  "name": "未命名",
  "items": [
    {
      "en": "I went to school yesterday.",
      "suggestion": "went",
      "explainZh": "過去式需使用 went。",
      "note": "lexical"
    }
  ],
  "model": "gemini-2.5-pro | gemini-2.5-flash"  // 可選，覆蓋預設模型
}
```
回應（JSON）：
```json
{
  "name": "測試卡集",
  "cards": [ { "front": "中文短語", "back": "(A | B) …", "frontNote": "可選", "backNote": "可選" } ]
}
```

### POST /chat/respond
- 輸入：`{ messages: [{ role: "user"|"assistant", content: "...", attachments?: [{ type: "image", mimeType: "image/png", data: "base64" }] }], model?: string }`
- 附件：僅支援 `type="image"`，`data` 需為 base64 字串，後端會轉換為 Gemini `inline_data`。
- 回應：`{ reply: string, state: "gathering"|"ready"|"completed", checklist?: string[] }`
- 補充：`reply` 會自動補齊 `## 回覆摘要` 與 `## 詳細說明` 區塊以利前端呈現。
- 用途：多輪確認需求，當 `state` 變為 `ready` 代表可以進入深入研究。

### POST /chat/research
- 輸入：`{ messages: [...] , model?: string }`（建議送上 `state=ready` 後的整段對話）。
- 回應：
  ```json
  {
    "deckName": "Academic phrases",
    "generatedAt": "2025-09-24T11:30:00Z",
    "cards": [
      {
        "front": "片語",
        "back": "研究重點說明",
        "frontNote": "(optional)",
        "backNote": "(optional example)"
      }
    ]
  }
  ```
- `cards[].front`/`back` 為必填欄位，`frontNote`、`backNote` 為選填；`ChatResearchResponse` 會維持 ISO8601 `generatedAt` 以利前端顯示。
- 若 LLM 回傳空陣列或缺乏 deckName，後端會以 500 提醒需要補充更多上下文。

### GET /healthz
- 若設好金鑰且可存取模型，回傳 `{ status: "ok", provider: "gemini", model: "…" }`。

- ### POST /correct/merge
- 請求：
  ```json
  {
    "zh": "中文原句",
    "en": "原本英文",
    "corrected": "修正版英文",
    "errors": [
      {
        "span": "yell and jump",
        "type": "morphological",
        "explainZh": "動詞應為現在分詞形式",
        "suggestion": "shouting and jumping"
      },
      {
        "span": "joyfully",
        "type": "lexical",
        "explainZh": "更自然的搭配是 with joy",
        "suggestion": "with joy"
      }
    ],
    "rationale": "使用者捏合這兩個錯誤，希望合併成慣用語",
    "model": "gemini-2.5-flash"
  }
  ```
- 回應：
  ```json
  {
    "error": {
      "id": "uuid",
      "span": "yell and jump joyfully",
      "type": "lexical",
      "explainZh": "將兩個動作與情緒整合為片語 shouting and jumping with joy，更符合習慣用法。",
      "suggestion": "shouting and jumping with joy"
    }
  }
  ```
- 用途：當使用者在 iOS App 中以捏合手勢選擇兩張錯誤卡片時，呼叫此端點產生合併後的提示卡。成功呼叫會被 `/usage/llm/view` 紀錄，路徑顯示為 `/correct/merge`。

### LLM Usage 監控
- 所有 LLM 呼叫都會記錄在 SQLite（`USAGE_DB_PATH`，預設 `data/usage.db`），包含 tokens、延遲、成本與清洗後的 request/response JSON（圖片 `inline_data` 會以 `<inline_data omitted>` 取代，以避免儲存大量 base64 資料）。
- `GET /usage/llm` 回傳 `{ summary, items[] }`，支援 `device_id`、`route`、`model`、`provider`、`since`、`until`、`limit`、`offset` 篩選。
- `GET /usage/llm/view` 提供內建儀表板；表格中的「查看」連結會開啟 `/usage/llm/{id}/view` 顯示該筆完整 metadata 與 JSON。
- 若要跨伺服器共享紀錄，請將 `USAGE_DB_PATH` 指向持久化磁碟或網路儲存位置，資料表會於啟動時自動建立。

## 部署（Render Blueprint）
- 在 GitHub 建立 repo 並推送（本倉已對應 https://github.com/MaxChen228/translation）。
- Render → New Blueprint → 選擇本 repo；使用以下設定（也可使用倉庫內的 `render.yaml`）：
  - Build Command：`pip install -r requirements.txt`
  - Start Command：`uvicorn main:app --host 0.0.0.0 --port $PORT --limit-max-request-size 5242880`
  - Health Check：`/healthz`
  - Env Vars：設定 `GEMINI_API_KEY`（必要）、`GEMINI_MODEL`（可選）

部署完成後取得 `https://<service>.onrender.com`，在 iOS App 的 Info 或 Build Settings 設定 `BACKEND_URL` 使用。

## 開發說明
- 架構：FastAPI + Pydantic v2；LLM 供應商為 Gemini（以 `requests` 直呼 API）。
- 內容來源：`data/` 下 JSON；可透過 `CONTENT_DIR` 指向自定資料夾。
- 除錯：`DECK_DEBUG_LOG` 預設為啟用（`1`），會在 `_test_logs/` 輸出 `/make_deck` 呼叫摘要（不含金鑰）；若希望停用請設定 `0`/`false`。
- 設定集中：所有設定集中於 `app/core/settings.py`，程式以 `get_settings()` 取得；請避免在其他模組直接讀取環境變數。
- LLM 請求監控：設定 `LLM_LOG_MODE=input`（或 `output`/`both`）即可在日誌中看到縮排後的請求/回應 JSON，若需關閉縮排可將 `LLM_LOG_PRETTY` 設為 `false`。

## 工具腳本
- `scripts/smoke_test.py`：快速呼叫 `/healthz`、`/correct`（可依需求擴充以覆蓋 `/correct/merge`）。
- `scripts/test_gemini_key.py`：檢查環境金鑰是否有效，可在部署前先行測試。

## 安全
- 請勿提交任何金鑰或私密資訊到版本控制。
- 建議使用 `.env`（本地）與 Render/雲端平台的環境變數管理機制（雲端）。


## 內容同步（本機 → 後端）
本 repo 提供 `scripts/sync_content.py`，可將本機 `content/` 目錄的課程/題庫同步到後端並立即 reload：

```bash
# 假設在 translation-backend 目錄下
./scripts/sync_content.py ../content --backend-url http://127.0.0.1:8080 --token $CONTENT_ADMIN_TOKEN
```

流程會：
1. 檢查 `books/`、`courses/` 中的 JSON 是否為有效格式。
2. 將檔案複製到後端的 `data/` 目錄（預設 `CONTENT_DIR`）。
3. 呼叫 `/admin/content/reload` 讓更新即時生效。

可依需求調整 `--source`、`--target`、`--backend-url` 等參數。請記得先設定 `CONTENT_ADMIN_TOKEN`，避免管理端點被濫用。
