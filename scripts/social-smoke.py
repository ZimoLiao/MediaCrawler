#!/usr/bin/env python3
"""Run tiny Joi social-media crawl jobs using persistent login profiles."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import mimetypes
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


PLATFORM_ALIASES = {
    "weibo": "wb",
    "wb": "wb",
    "bili": "bili",
    "bilibili": "bili",
    "xhs": "xhs",
    "zhihu": "zhihu",
    "dy": "dy",
    "douyin": "dy",
    "ks": "ks",
    "kuaishou": "ks",
}


IMAGE_URL_FIELDS = (
    "image_list",
    "cover_url",
    "video_cover_url",
    "avatar",
)


def _split_image_urls(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        urls: list[str] = []
        for item in value:
            if isinstance(item, dict):
                urls.extend(_split_image_urls(item.get("url") or item.get("url_default") or item.get("url_pre")))
            else:
                urls.extend(_split_image_urls(item))
        return urls
    text = str(value)
    return [part.strip() for part in re.split(r"[\s,]+", text) if part.strip().startswith(("http://", "https://"))]


def _read_jsonl_rows(out_dir: Path, platform: str) -> list[dict[str, Any]]:
    platform_dir = {"wb": "weibo", "dy": "douyin", "bili": "bili"}.get(platform, platform)
    rows: list[dict[str, Any]] = []
    for path in sorted((out_dir / platform_dir / "jsonl").glob("*_contents_*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def _jsonl_file_summaries(out_dir: Path) -> list[dict[str, Any]]:
    return [
        {"path": str(path), "rows": sum(1 for _ in path.open(encoding="utf-8"))}
        for path in sorted(out_dir.rglob("*.jsonl"))
    ]


def _has_output_rows(out_dir: Path) -> bool:
    return any(item["rows"] for item in _jsonl_file_summaries(out_dir))


def _extension_from_response(url: str, content_type: str) -> str:
    extension = mimetypes.guess_extension(content_type.split(";")[0].strip())
    if extension:
        return extension
    suffix = Path(urllib.parse.urlparse(url).path).suffix
    if suffix and len(suffix) <= 8:
        return suffix
    return ".jpg"


def _download_images(out_dir: Path, platform: str, *, limit: int) -> list[dict[str, str]]:
    platform_dir = {"wb": "weibo", "dy": "douyin", "bili": "bili"}.get(platform, platform)
    image_dir = out_dir / platform_dir / "images" / "joi"
    manifest: list[dict[str, str]] = []
    seen: set[str] = set()

    for row in _read_jsonl_rows(out_dir, platform):
        item_id = str(row.get("note_id") or row.get("aweme_id") or row.get("video_id") or "")
        for field in IMAGE_URL_FIELDS:
            for url in _split_image_urls(row.get(field)):
                if url in seen:
                    continue
                seen.add(url)
                if len(manifest) >= limit:
                    break
                request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                try:
                    with urllib.request.urlopen(request, timeout=20) as response:
                        content = response.read()
                        content_type = response.headers.get("Content-Type", "")
                except (urllib.error.URLError, TimeoutError):
                    continue
                if not content_type.startswith("image/"):
                    continue
                image_dir.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
                path = image_dir / f"{digest}{_extension_from_response(url, content_type)}"
                path.write_bytes(content)
                manifest.append({
                    "platform": platform,
                    "item_id": item_id,
                    "field": field,
                    "url": url,
                    "path": str(path),
                    "content_type": content_type,
                    "bytes": str(len(content)),
                })
            if len(manifest) >= limit:
                break
        if len(manifest) >= limit:
            break

    manifest_dir = out_dir / platform_dir / "jsonl"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "joi_images.jsonl"
    with manifest_path.open("w", encoding="utf-8") as handle:
        for item in manifest:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    return manifest


def _normalize_target(platform: str, value: str) -> str:
    value = value.strip()
    if platform == "wb":
        match = re.search(r"/detail/(\d+)", value)
        if match:
            return match.group(1)
    return value


def _normalize_creator(platform: str, value: str) -> str:
    value = value.strip()
    if platform == "wb":
        match = re.search(r"/u/(\d+)", value)
        if match:
            return match.group(1)
        if value.isdigit():
            return value
    return value


def _write_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _run_bili_creator_card(out_dir: Path, creator: str) -> None:
    creator = _normalize_creator("bili", creator)
    match = re.search(r"space\.bilibili\.com/(\d+)", creator)
    if match:
        creator = match.group(1)
    if not creator.isdigit():
        raise ValueError(f"Bilibili creator must be a UID or space URL: {creator}")

    url = f"https://api.bilibili.com/x/web-interface/card?mid={creator}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    if payload.get("code") != 0:
        raise RuntimeError(f"Bilibili card API failed: {payload}")
    card = payload.get("data", {}).get("card", {})
    row = {
        "user_id": str(card.get("mid") or creator),
        "nickname": card.get("name", ""),
        "sex": card.get("sex", ""),
        "sign": card.get("sign", ""),
        "avatar": card.get("face", ""),
        "last_modify_ts": int(datetime.now().timestamp() * 1000),
        "total_fans": card.get("fans", 0),
        "total_liked": "",
        "user_rank": (card.get("level_info") or {}).get("current_level", ""),
        "is_official": (card.get("official_verify") or {}).get("type", ""),
    }
    date_text = datetime.now().strftime("%Y-%m-%d")
    _write_jsonl(out_dir / "bili" / "jsonl" / f"creator_creators_{date_text}.jsonl", row)


async def run(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    platform = PLATFORM_ALIASES[args.platform]
    out_dir = Path(args.output or tempfile.mkdtemp(prefix=f"joi-social-{platform}-"))
    if out_dir.exists() and args.clean:
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    import config

    if platform == "bili" and args.action == "creator":
        _run_bili_creator_card(out_dir, args.creator)
        files = _jsonl_file_summaries(out_dir)
        print(json.dumps({
            "platform": platform,
            "action": args.action,
            "profile": str(repo_root / "browser_data" / f"cdp_{platform}_user_data_dir"),
            "output": str(out_dir),
            "warning": "Used lightweight Bilibili card API fallback; recent creator videos are not included.",
            "downloaded_images": 0,
            "files": files,
        }, ensure_ascii=False, indent=2))
        return 0

    config.CDP_CONNECT_EXISTING = False
    config.CUSTOM_BROWSER_PATH = args.browser
    config.BROWSER_LAUNCH_TIMEOUT = 45
    config.AUTO_CLOSE_BROWSER = True
    config.SAVE_LOGIN_STATE = True
    config.USER_DATA_DIR = "%s_user_data_dir"
    config.CRAWLER_MAX_SLEEP_SEC = 1
    config.ENABLE_GET_MEIDAS = bool(args.download_images and platform == "wb")

    sys.argv = [
        "main.py",
        "--platform", platform,
        "--lt", "cookie",
        "--type", args.action,
        "--keywords", args.keyword,
        "--save_data_option", "jsonl",
        "--save_data_path", str(out_dir),
        "--crawler_max_notes_count", str(args.limit),
        "--max_comments_count_singlenotes", str(args.comment_limit),
        "--get_comment", "true" if args.comments else "false",
        "--get_sub_comment", "false",
        "--headless", "true",
    ]
    if args.target:
        sys.argv.extend(["--specified_id", _normalize_target(platform, args.target)])
    if args.creator:
        sys.argv.extend(["--creator_id", _normalize_creator(platform, args.creator)])

    from main import async_cleanup, main

    warning = ""
    try:
        await main()
    except Exception as exc:
        if _has_output_rows(out_dir):
            warning = f"{type(exc).__name__}: {exc}"
        else:
            raise
    finally:
        await async_cleanup()

    downloaded_images: list[dict[str, str]] = []
    if args.download_images:
        downloaded_images = _download_images(out_dir, platform, limit=max(1, args.image_limit))

    files = _jsonl_file_summaries(out_dir)
    print(json.dumps({
        "platform": platform,
        "action": args.action,
        "profile": str(repo_root / "browser_data" / f"cdp_{platform}_user_data_dir"),
        "output": str(out_dir),
        "warning": warning,
        "downloaded_images": len(downloaded_images),
        "files": files,
    }, ensure_ascii=False, indent=2))
    return 0


def main_cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("platform", choices=sorted(PLATFORM_ALIASES))
    parser.add_argument("--action", choices=["search", "detail", "creator"], default="search")
    parser.add_argument("--keyword", default="人工智能")
    parser.add_argument("--target", default="")
    parser.add_argument("--creator", default="")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--comment-limit", type=int, default=5)
    parser.add_argument("--comments", action="store_true")
    parser.add_argument("--download-images", action="store_true")
    parser.add_argument("--image-limit", type=int, default=5)
    parser.add_argument("--output", default="")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument(
        "--browser",
        default="/home/lzmo/.cache/ms-playwright/chromium-1124/chrome-linux/chrome",
    )
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main_cli())
