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
from typing import Any, Dict, List, Tuple, cast
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

JsonDict = Dict[str, Any]


def _req(method: str, url: str, body: Dict[str, Any] | None = None, timeout: int = 30) -> Tuple[int, Any, float]:
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
    except Exception as exc:
        raise RuntimeError(f"{method} {url} failed: {exc}") from exc
    dt = (time.time() - t0) * 1000.0
    try:
        obj = json.loads(raw) if raw else {}
    except Exception as exc:
        raise RuntimeError(f"Invalid JSON from {url}: {raw[:280]}") from exc
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
    except Exception as exc:
        _ok(False)
        print(str(exc))
        return 1

    # 2) /cloud/decks
    try:
        status, decks_raw, dt = _req("GET", urljoin(base, "cloud/decks"), timeout=timeout)
        decks_list: List[JsonDict] = []
        if isinstance(decks_raw, list):
            decks_list = [cast(JsonDict, deck) for deck in decks_raw if isinstance(deck, dict)]
        ok = status // 100 == 2 and bool(decks_list)
        _ok(ok)
        deck_count = len(decks_list) if ok else "?"
        print(f"GET /cloud/decks {status} ({dt:.0f} ms) count={deck_count}")
        if not ok:
            failures += 1
        else:
            for d in decks_list[: max(0, args.max_decks)]:
                did = str(d.get("id") or "")
                if not did:
                    failures += 1
                    print("  ❌ deck missing id")
                    continue
                durl = urljoin(base, f"cloud/decks/{did}")
                s2, det_raw, t2 = _req("GET", durl, timeout=timeout)
                cards: List[JsonDict] = []
                if isinstance(det_raw, dict):
                    cards_value = det_raw.get("cards")
                    if isinstance(cards_value, list):
                        cards = [
                            cast(JsonDict, card)
                            for card in cards_value
                            if isinstance(card, dict)
                        ]
                ok2 = s2 // 100 == 2 and bool(cards)
                _ok(ok2)
                cards_count = len(cards) if ok2 else "?"
                print(f"  GET /cloud/decks/{did} {s2} ({t2:.0f} ms) cards={cards_count}")
                if not ok2:
                    failures += 1
    except Exception as exc:
        _ok(False)
        print(str(exc))
        return 1

    # 3) /cloud/books
    try:
        status, books_raw, dt = _req("GET", urljoin(base, "cloud/books"), timeout=timeout)
        books_list: List[JsonDict] = []
        if isinstance(books_raw, list):
            books_list = [cast(JsonDict, book) for book in books_raw if isinstance(book, dict)]
        ok = status // 100 == 2 and bool(books_list)
        _ok(ok)
        book_count = len(books_list) if ok else "?"
        print(f"GET /cloud/books {status} ({dt:.0f} ms) count={book_count}")
        if not ok:
            failures += 1
        else:
            for b in books_list[: max(0, args.max_books)]:
                name = str(b.get("name") or "")
                burl = urljoin(base, "cloud/books/") + quote(name, safe="")
                s2, det_raw, t2 = _req("GET", burl, timeout=timeout)
                items_list: List[JsonDict] = []
                if isinstance(det_raw, dict):
                    items_value = det_raw.get("items")
                    if isinstance(items_value, list):
                        items_list = [
                            cast(JsonDict, item)
                            for item in items_value
                            if isinstance(item, dict)
                        ]
                ok2 = s2 // 100 == 2 and bool(items_list)
                _ok(ok2)
                item_count = len(items_list) if ok2 else "?"
                print(f"  GET /cloud/books/{{name}} {s2} ({t2:.0f} ms) items={item_count} name='{name}'")
                if not ok2:
                    failures += 1
                else:
                    # Validate hints category within five allowed (when present)
                    allowed = {"morphological", "syntactic", "lexical", "phonological", "pragmatic"}
                    for it in items_list[:3]:
                        hints = it.get("hints") or []
                        bad = [h for h in hints if h.get("category") not in allowed]
                        if bad:
                            failures += 1
                            print(f"    ❌ invalid hint category: {bad[:2]}")
    except Exception as exc:
        _ok(False)
        print(str(exc))
        return 1

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
            s, obj_raw, dt = _req("POST", urljoin(base, "correct"), body=body, timeout=max(60, timeout))
            errors_list: List[JsonDict] = []
            if isinstance(obj_raw, dict):
                errors_value = obj_raw.get("errors")
                if isinstance(errors_value, list):
                    errors_list = [
                        cast(JsonDict, err)
                        for err in errors_value
                        if isinstance(err, dict)
                    ]
            ok = s // 100 == 2 and bool(errors_list)
            _ok(ok)
            error_count = len(errors_list) if ok else "?"
            print(f"POST /correct {s} ({dt:.0f} ms) errors={error_count}")
            if not ok:
                failures += 1
        except Exception as exc:
            _ok(False)
            print(str(exc))
            failures += 1

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
            s, obj_raw, dt = _req("POST", urljoin(base, "make_deck"), body=deck_body, timeout=max(60, timeout))
            cards_list: List[JsonDict] = []
            if isinstance(obj_raw, dict):
                cards_value = obj_raw.get("cards")
                if isinstance(cards_value, list):
                    cards_list = [
                        cast(JsonDict, card)
                        for card in cards_value
                        if isinstance(card, dict)
                    ]
            ok = s // 100 == 2 and bool(cards_list)
            _ok(ok)
            card_count = len(cards_list) if ok else "?"
            print(f"POST /make_deck {s} ({dt:.0f} ms) cards={card_count}")
            if not ok:
                failures += 1
        except Exception as exc:
            _ok(False)
            print(str(exc))
            failures += 1

    print("\nSummary: {} failures".format(failures))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
