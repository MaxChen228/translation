#!/usr/bin/env bash
# Convenience wrapper to generate multiple daily question batches in sequence.
# Any arguments passed to this script (e.g. --date 2025-10-06, --dry-run)
# will be forwarded to every python invocation below.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Activate virtual environment if it exists
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
fi

shared_args=("$@")

# Basic guard: avoid --count or --difficulty duplicated in shared args.
if [ ${#shared_args[@]} -gt 0 ]; then
  for arg in "${shared_args[@]}"; do
    case "$arg" in
      --count*|--difficulty*)
        echo "[run_daily_questions] 請勿在參數中帶 --count 或 --difficulty，會與預設批次衝突" >&2
        exit 1
        ;;
    esac
  done
fi

run_batch() {
  local count="$1"
  local difficulty="$2"
  shift 2 || true
  echo "[run_daily_questions] Generating count=${count}, difficulty=${difficulty}"
  if [ ${#shared_args[@]} -gt 0 ]; then
    python -m scripts.generate_daily_questions --count "$count" --difficulty "$difficulty" "${shared_args[@]}"
  else
    python -m scripts.generate_daily_questions --count "$count" --difficulty "$difficulty"
  fi
}

run_batch 6 3
run_batch 6 2

echo "[run_daily_questions] All batches completed."
