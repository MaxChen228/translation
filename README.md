# translation-backend

FastAPI 後端，為 iOS App 提供中英翻譯批改、雲端題庫/卡片瀏覽、與單字卡產生等 API。

Repo（GitHub）：https://github.com/MaxChen228/translation

## 功能總覽
- 批改（`POST /correct`）：回傳修正版、分數與錯誤清單（使用 Gemini）。
- 雲端資料（唯讀）：`/cloud/books*`、`/cloud/decks*` 從 `data/` 提供精選題庫/卡片集。
- 單字卡產生（`POST /make_deck`）：由 Saved JSON 彙整卡片，支援變體括號語法輸出。
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
uvicorn main:app --reload --host "$HOST" --port "$PORT"

# 健康檢查
curl -s http://127.0.0.1:8080/healthz | jq .
```

預設情況下，若未設定 API Key，`/healthz` 會顯示 `{"status": "no_key"}`。

## 環境變數
- `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`：Gemini API 金鑰（必要）。
- `GEMINI_MODEL`：模型名稱（預設 `gemini-2.5-flash`）。
- `CONTENT_DIR`：雲端瀏覽內容根目錄（預設 `./data`）。
- `DECK_DEBUG_LOG`：`1/true` 時在 `_test_logs` 留下 `/make_deck` 呼叫摘要以利除錯。
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

### GET /cloud/books、GET /cloud/books/{name}
- 從 `data/books/*.json` 提供唯讀題庫本清單與內容。
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
    { "zh": "…", "en": "…", "corrected": "…", "span": "…", "suggestion": "…", "explainZh": "…", "type": "lexical" }
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

### GET /healthz
- 若設好金鑰且可存取模型，回傳 `{ status: "ok", provider: "gemini", model: "…" }`。

## 部署（Render Blueprint）
- 在 GitHub 建立 repo 並推送（本倉已對應 https://github.com/MaxChen228/translation）。
- Render → New Blueprint → 選擇本 repo；使用以下設定（也可使用倉庫內的 `render.yaml`）：
  - Build Command：`pip install -r requirements.txt`
  - Start Command：`uvicorn main:app --host 0.0.0.0 --port $PORT`
  - Health Check：`/healthz`
  - Env Vars：設定 `GEMINI_API_KEY`（必要）、`GEMINI_MODEL`（可選）

部署完成後取得 `https://<service>.onrender.com`，在 iOS App 的 Info 或 Build Settings 設定 `BACKEND_URL` 使用。

## 開發說明
- 架構：FastAPI + Pydantic v2；LLM 供應商為 Gemini（以 `requests` 直呼 API）。
- 內容來源：`data/` 下 JSON；可透過 `CONTENT_DIR` 指向自定資料夾。
- 除錯：`DECK_DEBUG_LOG=1` 會在 `_test_logs/` 輸出 `/make_deck` 呼叫摘要（不含金鑰）。
  

## 安全
- 請勿提交任何金鑰或私密資訊到版本控制。
- 建議使用 `.env`（本地）與 Render/雲端平台的環境變數管理機制（雲端）。
