#!/usr/bin/env python3
"""
Simple backend API smoke test.

Covers:
  - GET /healthz
  - GET /cloud/decks and /cloud/decks/{id}
  - GET /cloud/books and /cloud/books/{name}
  - POST /correct (auto-skip if /healthz reports no_key)
  - POST /make_deck (auto-skip if /healthz reports no_key)

Usage:
  python scripts/smoke_test.py --base http://localhost:8080 [--model gemini-2.5-flash]
  python scripts/smoke_test.py --base https://translation-l9qi.onrender.com

Exit code 0 on success (including skipped LLM tests when key is missing), 1 on failure.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict, Tuple
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen


def _req(method: str, url: str, body: Dict[str, Any] | None = None, timeout: int = 30) -> Tuple[int, Dict[str, Any], float]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
    t0 = time.time()
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            status = getattr(resp, "status", 200)
    except Exception as e:
        raise RuntimeError(f"{method} {url} failed: {e}")
    dt = (time.time() - t0) * 1000.0
    try:
        obj = json.loads(raw) if raw else {}
    except Exception:
        raise RuntimeError(f"Invalid JSON from {url}: {raw[:280]}")
    return status, obj, dt


def _ok(cond: bool) -> None:
    if cond:
        print("✅", end=" ")
    else:
        print("❌", end=" ")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True, help="Backend base URL, e.g., http://localhost:8080")
    p.add_argument("--model", default=None, help="Optional model name for LLM endpoints")
    p.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds per request")
    p.add_argument("--max-decks", type=int, default=2, help="Fetch detail for up to N decks")
    p.add_argument("--max-books", type=int, default=2, help="Fetch detail for up to N books")
    args = p.parse_args()

    base = args.base.rstrip("/") + "/"
    timeout = args.timeout
    failures = 0

    # 1) /healthz
    url = urljoin(base, "healthz")
    try:
        status, obj, dt = _req("GET", url, timeout=timeout)
        _ok(status // 100 == 2 and isinstance(obj, dict))
        print(f"GET /healthz {status} ({dt:.0f} ms) -> {obj}")
        provider = obj.get("provider")
        health = obj.get("status")
        has_key = (health != "no_key")
    except Exception as e:
        _ok(False); print(str(e)); return 1

    # 2) /cloud/decks
    try:
        status, decks, dt = _req("GET", urljoin(base, "cloud/decks"), timeout=timeout)
        ok = status // 100 == 2 and isinstance(decks, list)
        _ok(ok); print(f"GET /cloud/decks {status} ({dt:.0f} ms) count={len(decks) if ok else '?'}")
        if not ok:
            failures += 1
        else:
            for d in decks[: max(0, args.max_decks)]:
                did = d.get("id")
                if not did:
                    failures += 1; print("  ❌ deck missing id"); continue
                durl = urljoin(base, f"cloud/decks/{did}")
                s2, det, t2 = _req("GET", durl, timeout=timeout)
                ok2 = s2 // 100 == 2 and isinstance(det, dict) and isinstance(det.get("cards"), list)
                _ok(ok2); print(f"  GET /cloud/decks/{did} {s2} ({t2:.0f} ms) cards={len(det.get('cards', [])) if ok2 else '?'}")
                if not ok2:
                    failures += 1
    except Exception as e:
        _ok(False); print(str(e)); return 1

    # 3) /cloud/books
    try:
        status, books, dt = _req("GET", urljoin(base, "cloud/books"), timeout=timeout)
        ok = status // 100 == 2 and isinstance(books, list)
        _ok(ok); print(f"GET /cloud/books {status} ({dt:.0f} ms) count={len(books) if ok else '?'}")
        if not ok:
            failures += 1
        else:
            for b in books[: max(0, args.max_books)]:
                name = b.get("name") or ""
                burl = urljoin(base, "cloud/books/") + quote(name, safe="")
                s2, det, t2 = _req("GET", burl, timeout=timeout)
                items = det.get("items") if isinstance(det, dict) else None
                ok2 = s2 // 100 == 2 and isinstance(items, list)
                _ok(ok2); print(f"  GET /cloud/books/{{name}} {s2} ({t2:.0f} ms) items={len(items) if ok2 else '?'} name='{name}'")
                if not ok2:
                    failures += 1
                else:
                    # Validate hints category within five allowed (when present)
                    allowed = {"morphological", "syntactic", "lexical", "phonological", "pragmatic"}
                    for it in items[:3]:
                        hints = it.get("hints") or []
                        bad = [h for h in hints if h.get("category") not in allowed]
                        if bad:
                            failures += 1
                            print(f"    ❌ invalid hint category: {bad[:2]}")
    except Exception as e:
        _ok(False); print(str(e)); return 1

    # 4) POST /correct (skip if no key)
    if provider == "gemini" and not has_key:
        print("⏭  /correct skipped (no API key)")
    else:
        body = {
            "zh": "我昨天去商店買水果。",
            "en": "I go to the shop yesterday to buy some fruits.",
            "hints": [
                {"category": "morphological", "text": "過去式"},
                {"category": "lexical", "text": "shop vs store; fruit 不可數"}
            ],
            "reviewNote": "使用過去式、常見搭配",
        }
        if args.model:
            body["model"] = args.model
        try:
            s, obj, dt = _req("POST", urljoin(base, "correct"), body=body, timeout=max(60, timeout))
            ok = s // 100 == 2 and isinstance(obj, dict) and isinstance(obj.get("errors"), list)
            _ok(ok); print(f"POST /correct {s} ({dt:.0f} ms) errors={len(obj.get('errors', [])) if ok else '?'}")
            if not ok:
                failures += 1
        except Exception as e:
            _ok(False); print(str(e)); failures += 1

    # 5) POST /make_deck (skip if no key)
    if provider == "gemini" and not has_key:
        print("⏭  /make_deck skipped (no API key)")
    else:
        deck_body = {
            "name": "Smoke Test Deck",
            "items": [
                {
                    "zh": "例：建議使用過去式",
                    "en": "I go to the shop yesterday.",
                    "corrected": "I went to the store yesterday.",
                    "span": "go",
                    "suggestion": "過去式 went",
                    "explainZh": "yesterday 應用過去式",
                    "type": "morphological",
                }
            ],
        }
        if args.model:
            deck_body["model"] = args.model
        try:
            s, obj, dt = _req("POST", urljoin(base, "make_deck"), body=deck_body, timeout=max(60, timeout))
            ok = s // 100 == 2 and isinstance(obj, dict) and isinstance(obj.get("cards"), list) and len(obj.get("cards", [])) > 0
            _ok(ok); print(f"POST /make_deck {s} ({dt:.0f} ms) cards={len(obj.get('cards', [])) if ok else '?'}")
            if not ok:
                failures += 1
        except Exception as e:
            _ok(False); print(str(e)); failures += 1

    print("\nSummary: {} failures".format(failures))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
