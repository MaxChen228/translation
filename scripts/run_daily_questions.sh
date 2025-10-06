#!/usr/bin/env bash
# Convenience wrapper to generate multiple daily question batches in sequence.
# Any arguments passed to this script (e.g. --date 2025-10-06, --dry-run)
# will be forwarded to every python invocation below.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

shared_args=("$@")

# Basic guard: avoid --count or --difficulty duplicated in shared args.
for arg in "${shared_args[@]}"; do
  case "$arg" in
    --count*|--difficulty*)
      echo "[run_daily_questions] 請勿在參數中帶 --count 或 --difficulty，會與預設批次衝突" >&2
      exit 1
      ;;
  esac
done

run_batch() {
  local count="$1"
  local difficulty="$2"
  shift 2 || true
  echo "[run_daily_questions] Generating count=${count}, difficulty=${difficulty}"
  python -m scripts.generate_daily_questions --count "$count" --difficulty "$difficulty" "${shared_args[@]}"
}

run_batch 6 3
run_batch 6 2

echo "[run_daily_questions] All batches completed."
