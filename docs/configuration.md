# Environment Configuration Guide

以下整理 translation-backend 服務會讀取的環境變數，協助快速建立 `.env`。

| 變數 | 型別/格式 | 預設值 | 需求性 | 說明 |
| ---- | --------- | ------ | ------ | ---- |
| `GEMINI_API_KEY` | string | — | 必填 (與 `GOOGLE_API_KEY` 擇一) | Gemini API 金鑰；批改、聊天、卡片生成皆依賴。 |
| `GOOGLE_API_KEY` | string | — | 選填 | Gemini API 替代金鑰；若已提供 `GEMINI_API_KEY` 可忽略。 |
| `GEMINI_MODEL` | string | `gemini-2.5-flash-preview-09-2025` | 選填 | 預設模型；可改為 `gemini-flash-latest` 等別名。 |
| `ALLOWED_MODELS` | comma-separated string | 內建白名單 | 選填 | 限制可選模型；留空則採預設集合。 |
| `LLM_TEMPERATURE` | float | `0.1` | 選填 | LLM 溫度；保留預設即可。 |
| `LLM_TOP_P` | float | `0.1` | 選填 | nucleus sampling 參數。 |
| `LLM_TOP_K` | int | `1` | 選填 | top-k 取樣。 |
| `LLM_MAX_OUTPUT_TOKENS` | int | — | 選填 | 限制回傳 token 數；留空由供應商決定。 |
| `CONTENT_DIR` | path | `data` | 選填 | 雲端題庫/課程/卡片來源資料夾。 |
| `USAGE_DB_PATH` | path | `data/usage.db` | 選填 | LLM 用量紀錄 SQLite 路徑。 |
| `USAGE_DB_URL` | database URL | — | 選填 | 若使用 Postgres 紀錄用量則填寫。 |
| `QUESTION_DB_PATH` | path | `data/questions.sqlite` | 選填 | 每日題庫 SQLite。 |
| `QUESTION_DB_URL` | database URL | — | 選填 | Postgres 版本的每日題庫儲存。 |
| `CONTENT_ADMIN_TOKEN` | string | — | 建議 | `/admin/content/*` 管理介面所需 Token。 |
| `PROMPT_FILE` | path | `prompts/prompt.txt` | 選填 | 批改系統提示檔。 |
| `PROMPT_LENIENT_FILE` | path | `prompts/prompt_lenient.txt` | 選填 | 寬鬆批改模式使用的提示檔。 |
| `DECK_PROMPT_FILE` | path | `prompts/prompt_deck.txt` | 選填 | 單字卡生成提示檔。 |
| `CHAT_TURN_PROMPT_FILE` | path | `prompts/prompt_chat_turn.txt` | 選填 | 聊天回合提示檔。 |
| `CHAT_RESEARCH_PROMPT_FILE` | path | `prompts/prompt_chat_research.txt` | 選填 | 聊天研究提示檔。 |
| `MERGE_PROMPT_FILE` | path | `prompts/prompt_merge.txt` | 選填 | 錯誤合併提示檔。 |
| `FLASHCARD_COMPLETION_PROMPT_FILE` | path | `prompts/prompt_flashcard_completion.txt` | 選填 | Deck 完成確認提示檔。 |
| `QUESTION_PROMPT_FILE` | path | `prompts/prompt_generate_questions.txt` | 選填 | 每日題庫生成提示。 |
| `DECK_DEBUG_LOG` | bool-like string | `1` | 選填 | `1/true/on` 啟用 deck 呼叫摘要。 |
| `LOG_LEVEL` | string | `INFO` | 選填 | 應用程式 log 等級。 |
| `LLM_LOG_MODE` | `off\|input\|output\|both` | `both` | 選填 | 控制 LLM 請求/回應輸出。 |
| `LLM_LOG_PRETTY` | bool | `True` | 選填 | 是否輸出縮排 JSON。 |
| `GENERATOR_DEFAULT_COUNT` | int | `8` | 選填 | 每日題目生成預設題數。 |
| `HOST` | string | `0.0.0.0` | 選填 | 伺服器綁定位址。 |
| `PORT` | int | `8080` | 選填 | 伺服器連接埠。 |

> 註：`ALLOWED_MODELS` 若包含未列於內建表的名稱，會在啟動時被忽略並回退至已知集合，避免因拼字或淘汰版本造成整體失效。

## 建議設定步驟
1. 複製 `.env.example` 為 `.env`，填入 API 金鑰與 `CONTENT_ADMIN_TOKEN`。
2. 依需求改寫內容儲存路徑或資料庫連線（例如導入 Postgres）。
3. 若要減少日誌量，可將 `LLM_LOG_MODE` 調整為 `off` 或 `input`。
4. 執行 `uvicorn main:app --reload ...` 前，確認 `CONTENT_DIR` 與 `USAGE_DB_PATH` 指向存在的路徑。

> 註：服務啟動時會優先載入 repo 根目錄與 `translation-backend/.env` 兩份檔案（`main.py`）。
