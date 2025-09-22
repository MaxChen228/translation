#!/usr/bin/env python3
"""Synchronize local content folder to backend data directory and trigger reload."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import urllib.request

from pathlib import Path


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            copy_tree(item, target)
        else:
            shutil.copy2(item, target)


def lint_basic(root: Path) -> None:
    required_dirs = [root / "books", root / "courses"]
    for d in required_dirs:
        if not d.exists():
            continue
        for path in d.rglob("*.json"):
            try:
                import json

                with path.open("r", encoding="utf-8") as handle:
                    json.load(handle)
            except Exception as exc:  # pragma: no cover - user facing
                raise SystemExit(f"Invalid JSON file: {path} ({exc})")


def trigger_reload(base_url: str, token: str | None) -> None:
    url = base_url.rstrip("/") + "/admin/content/reload"
    req = urllib.request.Request(url, method="POST")
    if token:
        req.add_header("X-Content-Token", token)
    try:
        with urllib.request.urlopen(req) as resp:  # nosec - controlled target
            data = resp.read().decode("utf-8", errors="ignore")
            print(data)
    except Exception as exc:  # pragma: no cover - user facing
        raise SystemExit(f"Failed to reload content: {exc}")


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Sync content to backend and reload.")
    parser.add_argument("source", nargs="?", default="../content", help="Path to local content directory")
    parser.add_argument("--target", default="data", help="Backend data directory")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8080", help="Backend base URL")
    parser.add_argument("--token", default=os.environ.get("CONTENT_ADMIN_TOKEN"), help="Admin token")
    args = parser.parse_args(argv)

    source = Path(args.source).expanduser().resolve()
    target = Path(args.target).expanduser().resolve()

    if not source.exists():
        raise SystemExit(f"Source directory not found: {source}")

    print(f"Linting content in {source} …")
    lint_basic(source)

    print(f"Syncing content to {target} …")
    copy_tree(source, target)

    print("Triggering backend reload …")
    trigger_reload(args.backend_url, args.token)
    print("Done.")


if __name__ == "__main__":
    main(sys.argv[1:])
