#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

import requests


def _ensure_project_root() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_project_root()

from app.core.settings import get_settings  # noqa: E402
from app.llm import GEMINI_BASE  # noqa: E402


def main() -> int:
    settings = get_settings()
    api_key = settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY
    if not api_key:
        print("API key missing: set GEMINI_API_KEY or GOOGLE_API_KEY")
        return 1

    url = f"{GEMINI_BASE}/models?key={api_key}"
    try:
        response = requests.get(url, timeout=10)
    except requests.RequestException as exc:
        print(f"Request failed: {exc}")
        return 1

    if response.status_code != 200:
        body = response.text.replace("\n", " ")[:200]
        print(f"API key rejected (status {response.status_code}): {body}")
        return 1

    data = response.json()
    models: List[str] = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    preview = ", ".join(models[:3]) if models else "no models returned"
    print(f"API key looks valid. Sample models: {preview}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
