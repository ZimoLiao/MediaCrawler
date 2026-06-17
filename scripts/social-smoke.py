#!/usr/bin/env python3
"""Run a tiny MediaCrawler search using the persistent social-login profile."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path


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


async def run(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    platform = PLATFORM_ALIASES[args.platform]
    out_dir = Path(args.output or tempfile.mkdtemp(prefix=f"joi-social-{platform}-"))
    if out_dir.exists() and args.clean:
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    import config

    config.CDP_CONNECT_EXISTING = False
    config.CUSTOM_BROWSER_PATH = args.browser
    config.BROWSER_LAUNCH_TIMEOUT = 45
    config.AUTO_CLOSE_BROWSER = True
    config.SAVE_LOGIN_STATE = True
    config.USER_DATA_DIR = "%s_user_data_dir"

    sys.argv = [
        "main.py",
        "--platform", platform,
        "--lt", "cookie",
        "--type", "search",
        "--keywords", args.keyword,
        "--save_data_option", "jsonl",
        "--save_data_path", str(out_dir),
        "--crawler_max_notes_count", str(args.limit),
        "--max_comments_count_singlenotes", str(args.comment_limit),
        "--get_comment", "true" if args.comments else "false",
        "--get_sub_comment", "false",
        "--headless", "true",
    ]

    from main import async_cleanup, main

    try:
        await main()
    finally:
        await async_cleanup()

    files = sorted(out_dir.rglob("*.jsonl"))
    print(json.dumps({
        "platform": platform,
        "profile": str(repo_root / "browser_data" / f"cdp_{platform}_user_data_dir"),
        "output": str(out_dir),
        "files": [
            {"path": str(path), "rows": sum(1 for _ in path.open(encoding="utf-8"))}
            for path in files
        ],
    }, ensure_ascii=False, indent=2))
    return 0


def main_cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("platform", choices=sorted(PLATFORM_ALIASES))
    parser.add_argument("--keyword", default="人工智能")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--comment-limit", type=int, default=5)
    parser.add_argument("--comments", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument(
        "--browser",
        default="/home/lzmo/.cache/ms-playwright/chromium-1124/chrome-linux/chrome",
    )
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main_cli())
