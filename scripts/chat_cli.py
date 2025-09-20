#!/usr/bin/env python3
"""簡易命令列聊天室：串接 /chat/respond 與 /chat/research。

使用方式：
    CHAT_BACKEND_URL=http://127.0.0.1:8080 \
    GEMINI_API_KEY=... \
    python scripts/chat_cli.py

指令：
    /research   觸發深入研究並顯示錯誤清單
    /reset      清空對話歷史
    /show       列出目前的對話訊息
    /exit       結束程式

程式會維持完整的 user/assistant 對話歷史並送往後端。"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from typing import List, Dict

import requests

DEFAULT_BASE = "http://127.0.0.1:8080"
BASE_URL = os.environ.get("CHAT_BACKEND_URL", DEFAULT_BASE).rstrip("/")
RESPOND_URL = f"{BASE_URL}/chat/respond"
RESEARCH_URL = f"{BASE_URL}/chat/research"

SEPARATOR = "=" * 60


def _post(url: str, payload: Dict) -> Dict:
    try:
        resp = requests.post(url, json=payload, timeout=90)
    except requests.RequestException as exc:  # pragma: no cover - runtime error
        raise SystemExit(f"\n[!] 請求失敗：{exc}") from exc
    if resp.status_code // 100 != 2:
        detail = resp.text
        try:
            detail = json.dumps(resp.json(), ensure_ascii=False, indent=2)
        except Exception:
            pass
        raise SystemExit(f"\n[!] 後端回傳非 2xx 狀態 ({resp.status_code}):\n{detail}")
    try:
        return resp.json()
    except ValueError as exc:
        raise SystemExit(f"\n[!] 後端回傳不是 JSON：{resp.text[:200]}") from exc


def _print_block(title: str, body: str) -> None:
    print(f"\n[{title}]")
    wrapped = textwrap.fill(body, width=80, replace_whitespace=False)
    print(wrapped)


def _print_checklist(items: List[str] | None) -> None:
    if not items:
        return
    print("\n[Checklist]")
    for idx, item in enumerate(items, 1):
        print(f"  {idx}. {item}")


def _print_errors(errors: List[Dict]) -> None:
    if not errors:
        print("\n[Errors] 無錯誤項目")
        return
    print("\n[Errors]")
    for idx, err in enumerate(errors, 1):
        print(f"  {idx}. span: {err.get('span')} ({err.get('type')})")
        print(f"     explain: {err.get('explainZh')}")
        suggestion = err.get("suggestion")
        if suggestion:
            print(f"     suggestion: {suggestion}")


def run_chat() -> None:
    print(SEPARATOR)
    print("簡易 Gemini 對話驗證工具")
    print(f"Backend URL: {BASE_URL}")
    print(SEPARATOR)

    conversation: List[Dict[str, str]] = []

    while True:
        try:
            text = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n結束對話。")
            break

        if not text:
            continue
        if text.lower() in {"/exit", ":q"}:
            print("結束對話。")
            break
        if text.lower() == "/reset":
            conversation.clear()
            print("[系統] 對話已清空。")
            continue
        if text.lower() == "/show":
            if not conversation:
                print("[系統] 尚未有任何訊息。")
                continue
            print("\n[對話歷史]")
            for msg in conversation:
                role = msg["role"]
                prefix = "你" if role == "user" else "Gemini"
                print(f"{prefix}: {msg['content']}")
            print(SEPARATOR)
            continue
        if text.lower() == "/research":
            if not conversation:
                print("[系統] 尚無對話內容，無法深入研究。")
                continue
            payload = {"messages": conversation}
            data = _post(RESEARCH_URL, payload)
            print(SEPARATOR)
            _print_block("Title", data.get("title", ""))
            _print_block("Summary", data.get("summary", ""))
            src = data.get("sourceZh")
            if src:
                _print_block("SourceZh", src)
            attempt = data.get("attemptEn")
            if attempt:
                _print_block("AttemptEn", attempt)
            _print_block("CorrectedEn", data.get("correctedEn", ""))
            _print_errors(data.get("errors") or [])
            print(SEPARATOR)
            continue

        # Regular chat turn
        conversation.append({"role": "user", "content": text})
        payload = {"messages": conversation}
        data = _post(RESPOND_URL, payload)
        reply = data.get("reply", "")
        state = data.get("state", "gathering")
        conversation.append({"role": "assistant", "content": reply})

        print(SEPARATOR)
        _print_block("Gemini", reply)
        print(f"[State] {state}")
        _print_checklist(data.get("checklist"))
        print(SEPARATOR)


if __name__ == "__main__":
    try:
        run_chat()
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        sys.exit(exc.code if isinstance(exc.code, int) else 1)
