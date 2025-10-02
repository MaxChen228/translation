#!/usr/bin/env python3
"""Synchronize local content folder to backend via HTTP API upload."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from typing import List, Dict, Tuple


def lint_basic(root: Path) -> None:
    """驗證 JSON 文件格式"""
    required_dirs = [root / "books", root / "courses"]
    for d in required_dirs:
        if not d.exists():
            continue
        for path in d.rglob("*.json"):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    json.load(handle)
            except Exception as exc:  # pragma: no cover - user facing
                raise SystemExit(f"Invalid JSON file: {path} ({exc})")


def collect_content_files(source: Path) -> List[Tuple[Path, str]]:
    """收集要上傳的內容文件"""
    files = []

    # 收集題庫文件
    books_dir = source / "books"
    if books_dir.exists():
        for path in books_dir.rglob("*.json"):
            files.append((path, "book"))

    # 收集課程文件
    courses_dir = source / "courses"
    if courses_dir.exists():
        for path in courses_dir.rglob("*.json"):
            files.append((path, "course"))

    return files


def upload_single_file(
    file_path: Path,
    content_type: str,
    backend_url: str,
    token: str | None
) -> Dict:
    """上傳單個文件"""
    # 讀取文件內容
    with file_path.open("r", encoding="utf-8") as f:
        content = json.load(f)

    # 準備請求數據
    request_data = {
        "filename": file_path.name,
        "content": content,
        "content_type": content_type
    }

    # 發送請求
    url = backend_url.rstrip("/") + "/admin/content/upload"
    data = json.dumps(request_data).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Content-Token", token)

    try:
        with urllib.request.urlopen(req) as resp:  # nosec - controlled target
            response_data = json.loads(resp.read().decode("utf-8"))
            return response_data
    except urllib.error.HTTPError as e:
        error_message = e.read().decode("utf-8") if e.fp else str(e)
        try:
            error_data = json.loads(error_message)
            return {"error": error_data}
        except:
            return {"error": error_message}
    except Exception as exc:
        return {"error": str(exc)}


def upload_bulk_files(
    files: List[Tuple[Path, str]],
    backend_url: str,
    token: str | None
) -> Dict:
    """批量上傳文件"""
    bulk_files = []

    for file_path, content_type in files:
        with file_path.open("r", encoding="utf-8") as f:
            content = json.load(f)

        bulk_files.append({
            "filename": file_path.name,
            "content": content,
            "content_type": content_type
        })

    # 準備請求數據
    request_data = {
        "files": bulk_files,
        "reload_after_upload": True
    }

    # 發送請求
    url = backend_url.rstrip("/") + "/admin/content/upload/bulk"
    data = json.dumps(request_data).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Content-Token", token)

    try:
        with urllib.request.urlopen(req) as resp:  # nosec - controlled target
            response_data = json.loads(resp.read().decode("utf-8"))
            return response_data
    except urllib.error.HTTPError as e:
        error_message = e.read().decode("utf-8") if e.fp else str(e)
        try:
            error_data = json.loads(error_message)
            return {"error": error_data}
        except:
            return {"error": error_message}
    except Exception as exc:
        return {"error": str(exc)}


def print_upload_results(response: Dict) -> None:
    """打印上傳結果"""
    if "error" in response:
        print(f"❌ 上傳失敗: {response['error']}")
        return

    results = response.get("results", [])
    success_count = response.get("success_count", 0)
    error_count = response.get("error_count", 0)

    print(f"📊 上傳結果: {success_count} 成功, {error_count} 失敗")

    # 打印詳細結果
    for result in results:
        filename = result.get("filename", "unknown")
        success = result.get("success", False)
        message = result.get("message", "")
        content_type = result.get("content_type", "")

        status = "✅" if success else "❌"
        print(f"  {status} {content_type}: {filename} - {message}")


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Sync content to backend via HTTP API.")
    parser.add_argument("source", nargs="?", default="content", help="Path to local content directory")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8080", help="Backend base URL")
    parser.add_argument("--token", default=os.environ.get("CONTENT_ADMIN_TOKEN"), help="Admin token")
    parser.add_argument("--single", action="store_true", help="Upload files one by one instead of bulk upload")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be uploaded without actually uploading")
    args = parser.parse_args(argv)

    source = Path(args.source).expanduser().resolve()

    if not source.exists():
        raise SystemExit(f"❌ 源目錄不存在: {source}")

    print(f"🔍 檢查內容格式 {source} …")
    lint_basic(source)

    print("📁 收集內容文件 …")
    files = collect_content_files(source)

    if not files:
        print("⚠️  沒有找到要上傳的文件")
        return

    print(f"📋 找到 {len(files)} 個文件:")
    for file_path, content_type in files:
        print(f"  • {content_type}: {file_path.name}")

    if args.dry_run:
        print("🏃 Dry run 模式 - 不會實際上傳")
        return

    if not args.token:
        print("⚠️  警告: 未設定 CONTENT_ADMIN_TOKEN，可能會被拒絕存取")

    # 上傳文件
    if args.single:
        print("📤 逐個上傳文件 …")
        success_count = 0
        for file_path, content_type in files:
            print(f"上傳 {file_path.name} …", end=" ")
            response = upload_single_file(file_path, content_type, args.backend_url, args.token)

            if "error" not in response:
                result = response.get("results", [{}])[0]
                if result.get("success", False):
                    print("✅")
                    success_count += 1
                else:
                    print(f"❌ {result.get('message', 'Unknown error')}")
            else:
                print(f"❌ {response['error']}")

        print(f"🎉 完成! 成功上傳 {success_count}/{len(files)} 個文件")
    else:
        print("📦 批量上傳文件 …")
        response = upload_bulk_files(files, args.backend_url, args.token)
        print_upload_results(response)

        if "error" not in response:
            print("🎉 同步完成!")
        else:
            sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
