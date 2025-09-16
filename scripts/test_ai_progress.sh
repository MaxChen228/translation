#!/usr/bin/env bash

set -euo pipefail

# --- Config ---
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
BASE="http://$HOST:$PORT"
LLM_MODEL="${LLM_MODEL:-}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-2.5-flash}"
# 確保 DEVICE_ID 一定有值（允許外部覆蓋）
DEVICE_ID="${DEVICE_ID:-dev-ai-$(date +%s)-$RANDOM}"

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

LOG_DIR="backend/_test_logs"
mkdir -p "$LOG_DIR"
SERVER_LOG="$LOG_DIR/server_$(date +%Y%m%d_%H%M%S).log"

if ! command -v curl >/dev/null 2>&1; then
  echo "[ERR] 需要 curl" >&2
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "[ERR] 需要 jq（macOS 可用: brew install jq）" >&2
  exit 1
fi

if [[ -z "${GEMINI_API_KEY:-}${GOOGLE_API_KEY:-}" ]]; then
  echo "[ERR] 需要 GEMINI_API_KEY 或 GOOGLE_API_KEY（本腳本僅支援 Gemini）" >&2
  exit 1
fi
MODEL_USE="${LLM_MODEL:-$GEMINI_MODEL}"

echo "[INFO] 啟動後端 (AI 模式) on $BASE, provider=gemini, model=$MODEL_USE"
set +e
HOST=$HOST PORT=$PORT LLM_MODEL="$LLM_MODEL" GEMINI_MODEL=$GEMINI_MODEL \
  python3 backend/main.py >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!
set -e

cleanup() {
  if ps -p $SERVER_PID >/dev/null 2>&1; then
    kill $SERVER_PID >/dev/null 2>&1 || true
    wait $SERVER_PID 2>/dev/null || true
  fi
}
trap cleanup EXIT

# Wait for health
echo -n "[INFO] 等待服務啟動"
ok=""
for i in {1..60}; do
  status=$(curl -s "$BASE/healthz" | jq -r '.status // empty') || true
  if [[ "$status" == "ok" ]]; then
    ok=1; break
  fi
  echo -n "."; sleep 1
done
echo
if [[ -z "$ok" ]]; then
  echo "[ERR] 服務啟動失敗，healthz: $(curl -s "$BASE/healthz")" >&2
  echo "[LOG] 伺服器日誌（末尾 100 行）：" >&2
  tail -n 100 "$SERVER_LOG" >&2 || true
  exit 1
fi

passes=0; fails=0
step() { echo "[STEP] $*"; }
pass() { echo "[ OK ] $*"; passes=$((passes+1)); }
fail() { echo "[FAIL] $*"; fails=$((fails+1)); }

# List items for this device
step "取得題庫清單（帶 deviceId=${DEVICE_ID:-N/A}）"
ITEMS_JSON=$(curl -s "$BASE/bank/items?deviceId=$DEVICE_ID") || { fail "GET /bank/items"; exit 1; }
FIRST_ID=$(echo "$ITEMS_JSON" | jq -r '.[0].id // empty')
FIRST_ZH=$(echo "$ITEMS_JSON" | jq -r '.[0].zh // empty')
FIRST_TAG=$(echo "$ITEMS_JSON" | jq -r '.[0].tags[0] // empty')
if [[ -z "$FIRST_ID" ]]; then
  fail "題庫為空，無法測試"
  exit 1
fi
PRE_COMPLETED=$(echo "$ITEMS_JSON" | jq -r --arg id "$FIRST_ID" '.[] | select(.id==$id) | (.completed // false)')
echo "  第一題: id=$FIRST_ID, tag=${FIRST_TAG:-none}, completed=$PRE_COMPLETED"

# Correct with bankItemId + deviceId
step "呼叫 /correct（AI 模式）並自動標記完成"
REQ_EN_BAD="I go to the shop yesterday to buy some fruits."
PAYLOAD=$(jq -n --arg zh "$FIRST_ZH" --arg en "$REQ_EN_BAD" --arg id "$FIRST_ID" --arg dev "$DEVICE_ID" '{zh:$zh,en:$en,bankItemId:$id,deviceId:$dev}')
CORR_JSON=$(curl -s -H 'Content-Type: application/json' -d "$PAYLOAD" "$BASE/correct") || { fail "POST /correct"; exit 1; }
SCORE=$(echo "$CORR_JSON" | jq -r '.score // empty')
if [[ -z "$SCORE" || "$SCORE" == "null" ]]; then
  echo "$CORR_JSON" | jq . || true
  fail "/correct 回傳缺少 score（可能 AI 模型/金鑰設定有誤）"
  exit 1
fi
pass "/correct 成功，score=$SCORE"

# Check completion
step "驗證題目已標記完成"
AFTER_JSON=$(curl -s "$BASE/bank/items?deviceId=$DEVICE_ID")
AFTER_COMPLETED=$(echo "$AFTER_JSON" | jq -r --arg id "$FIRST_ID" '.[] | select(.id==$id) | (.completed // false)')
if [[ "$AFTER_COMPLETED" == "true" ]]; then
  pass "completed=true"
else
  fail "completed=false"
fi

# Random skipCompleted test (if tag is present)
if [[ -n "${FIRST_TAG:-}" ]]; then
  step "測試 /bank/random skipCompleted 與 tag=$FIRST_TAG"
  ITEMS_ALL=$(curl -s "$BASE/bank/items?deviceId=$DEVICE_ID")
  COUNT_IN_TAG=$(echo "$ITEMS_ALL" | jq --arg t "$FIRST_TAG" '[.[] | select(.tags | index($t))] | length')
  HTTP_CODE=$(curl -s -o "$LOG_DIR/_random_resp.json" -w '%{http_code}' "$BASE/bank/random?deviceId=$DEVICE_ID&skipCompleted=1&tag=$FIRST_TAG")
  if [[ "$COUNT_IN_TAG" -eq 1 ]]; then
    if [[ "$HTTP_CODE" -eq 404 ]]; then
      pass "/bank/random 對單一且已完成的 tag 正確回 404"
    else
      echo "resp:"; cat "$LOG_DIR/_random_resp.json"; echo
      fail "/bank/random 應為 404，實際 $HTTP_CODE"
    fi
  else
    if [[ "$HTTP_CODE" -eq 200 ]]; then
      RID=$(jq -r '.id' "$LOG_DIR/_random_resp.json")
      if [[ "$RID" != "$FIRST_ID" ]]; then
        pass "/bank/random 未回傳已完成題目"
      else
        fail "/bank/random 回傳了已完成題目"
      fi
    else
      echo "resp:"; cat "$LOG_DIR/_random_resp.json"; echo
      fail "/bank/random HTTP $HTTP_CODE"
    fi
  fi
else
  step "題目無 tag，略過 skipCompleted 測試"
fi

# Progress endpoint
step "檢查 /bank/progress"
PROG_JSON=$(curl -s "$BASE/bank/progress?deviceId=$DEVICE_ID")
IN_COMPLETED=$(echo "$PROG_JSON" | jq -r --arg id "$FIRST_ID" '(.completedIds | index($id)) != null')
if [[ "$IN_COMPLETED" == "true" ]]; then
  pass "progress.completedIds 含該題"
else
  echo "$PROG_JSON" | jq . || true
  fail "progress.completedIds 缺少該題"
fi

echo
echo "===== 測試摘要 ====="
echo "Server: $BASE"
echo "Device: $DEVICE_ID"
echo "Item:   $FIRST_ID (tag=${FIRST_TAG:-none})"
echo "Score:  $SCORE"
echo "Passes: $passes  Fails: $fails"
echo "Log:    $SERVER_LOG"
echo "====================="

if [[ "$fails" -gt 0 ]]; then
  exit 1
fi
