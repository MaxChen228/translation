#!/usr/bin/env python3
"""
Minimal local HTTP backend for the iOS app.

POST /correct
Body: {"zh": "...", "en": "..."}
Response schema matches the app expectation (see README).

No third‑party packages required. Intended for local development only.
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import re
import uuid
import urllib.parse


def _mk_error(span, etype, explain_zh, suggestion=None, before=None, after=None, occurrence=None):
    err = {
        "id": str(uuid.uuid4()),
        "span": span,
        "type": etype,  # morphological | syntactic | lexical | phonological | pragmatic
        "explainZh": explain_zh,
    }
    if suggestion:
        err["suggestion"] = suggestion
    hints = {k: v for k, v in {"before": before, "after": after, "occurrence": occurrence}.items() if v is not None}
    if hints:
        err["hints"] = hints
    return err


def _analyze(zh: str, en: str):
    """Return (corrected, score, errors[]) with very naive rules for demo."""
    errors = []
    corrected = en

    # Rule 1: 'go' -> 'went' (morphological)
    if re.search(r"\byesterday\b", en, flags=re.I) and re.search(r"\bgo\b", en):
        errors.append(_mk_error(
            span="go",
            etype="morphological",
            explain_zh="應使用過去式。",
            suggestion="went",
            before="I ",
            after=" to",
            occurrence=1,
        ))
        corrected = re.sub(r"\bgo\b", "went", corrected, count=1)

    # Rule 2: 'shop' -> 'store' (lexical)
    if re.search(r"\bshop\b", en, flags=re.I):
        errors.append(_mk_error(
            span="shop",
            etype="lexical",
            explain_zh="在此語境更常用 store。",
            suggestion="store",
            before="the ",
            after=" ",
        ))
        corrected = re.sub(r"\bshop\b", "store", corrected, count=1, flags=re.I)

    # Rule 3: 'fruits' -> 'fruit' (pragmatic/natural usage)
    if re.search(r"\bfruits\b", en, flags=re.I):
        errors.append(_mk_error(
            span="fruits",
            etype="pragmatic",
            explain_zh="一般泛指時常用不可數名詞 fruit。",
            suggestion="fruit",
            before="some ",
            after=None,
        ))
        corrected = re.sub(r"\bfruits\b", "fruit", corrected, count=1, flags=re.I)

    # Score: start at 100 and subtract 5 per error (floor 60)
    score = max(60, 100 - 5 * len(errors))

    return corrected, score, errors


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalCorrect/0.1"

    def _send_json(self, code: int, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # --- Cloud curated content (read-only) ---
    _CLOUD_DECKS = [
        {
            "id": "starter-phrases",
            "name": "Starter Phrases",
            "cards": [
                {"front": "Hello!", "back": "你好！"},
                {"front": "How are you?", "back": "你最近好嗎？"},
                {"front": "Thank you.", "back": "謝謝你。"},
            ],
        },
        {
            "id": "common-errors",
            "name": "Common Errors",
            "cards": [
                {
                    "front": "I look forward to hear from you.",
                    "back": "更自然：I look forward to hearing from you.",
                },
                {
                    "front": "He suggested me to go.",
                    "back": "更自然：He suggested that I go / He suggested going.",
                },
            ],
        },
    ]

    _CLOUD_BOOKS = [
        {
            "name": "Daily Conversations",
            "items": [
                {
                    "id": "conv-greet",
                    "zh": "跟陌生人打招呼",
                    "hints": [],
                    "suggestions": [],
                    "tags": ["daily"],
                    "difficulty": 1,
                },
                {
                    "id": "conv-order",
                    "zh": "點餐時的常見句型",
                    "hints": [],
                    "suggestions": [],
                    "tags": ["daily"],
                    "difficulty": 2,
                },
            ],
        },
        {
            "name": "Academic Writing",
            "items": [
                {
                    "id": "acad-intro",
                    "zh": "撰寫研究引言",
                    "hints": [],
                    "suggestions": [],
                    "tags": ["academic"],
                    "difficulty": 3,
                },
                {
                    "id": "acad-method",
                    "zh": "描述研究方法",
                    "hints": [],
                    "suggestions": [],
                    "tags": ["academic"],
                    "difficulty": 3,
                },
            ],
        },
    ]

    def _handle_cloud_get(self, path: str):
        # /cloud/decks
        if path == "/cloud/decks":
            lst = [{"id": d["id"], "name": d["name"], "count": len(d["cards"]) } for d in self._CLOUD_DECKS]
            self._send_json(200, lst)
            return True
        # /cloud/decks/<id>
        if path.startswith("/cloud/decks/"):
            deck_id = path.split("/", 3)[-1]
            deck = next((d for d in self._CLOUD_DECKS if d["id"] == deck_id), None)
            if not deck:
                self._send_json(404, {"error": "not_found"})
                return True
            # Map to app schema: {id, name, cards:[{id(UUID), front, back, frontNote?, backNote?}]}
            cards = []
            for c in deck["cards"]:
                card = {
                    "id": str(uuid.uuid4()),
                    "front": c.get("front", ""),
                    "back": c.get("back", ""),
                }
                if "frontNote" in c:
                    card["frontNote"] = c["frontNote"]
                if "backNote" in c:
                    card["backNote"] = c["backNote"]
                cards.append(card)
            self._send_json(200, {"id": deck["id"], "name": deck["name"], "cards": cards})
            return True
        # /cloud/books
        if path == "/cloud/books":
            lst = [{"name": b["name"], "count": len(b["items"]) } for b in self._CLOUD_BOOKS]
            self._send_json(200, lst)
            return True
        # /cloud/books/<name> (URL-encoded)
        if path.startswith("/cloud/books/"):
            encoded = path.split("/", 3)[-1]
            name = urllib.parse.unquote(encoded)
            book = next((b for b in self._CLOUD_BOOKS if b["name"] == name), None)
            if not book:
                self._send_json(404, {"error": "not_found"})
                return True
            self._send_json(200, {"name": book["name"], "items": book["items"]})
            return True
        return False

    def do_GET(self):  # noqa: N802
        # Route cloud library endpoints
        if self._handle_cloud_get(self.path):
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self):  # noqa: N802 (BaseHTTPRequestHandler API)
        if self.path != "/correct":
            self._send_json(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else b""
        try:
            req = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            self._send_json(400, {"error": "invalid_json"})
            return
        zh = str(req.get("zh", ""))
        en = str(req.get("en", ""))
        corrected, score, errors = _analyze(zh, en)
        resp = {"corrected": corrected, "score": score, "errors": errors}
        self._send_json(200, resp)

    def log_message(self, fmt, *args):  # quiet console
        print(f"[backend] {self.address_string()} - " + fmt % args)


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    print(f"Starting local backend on http://{host}:{port}")
    HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
