# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import uvicorn

from hotboard.app import create_app
from hotboard.service import HotboardService
from hotboard.storage import HotboardRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the MediaCrawler hotboard monitor")
    parser.add_argument("--db", default="data/hotboard/hotboard.db", help="SQLite database path")
    parser.add_argument("--host", default="0.0.0.0", help="Dashboard bind host")
    parser.add_argument("--port", default=8765, type=int, help="Dashboard bind port")
    parser.add_argument("--interval-hours", default=6.0, type=float, help="Capture interval in hours")
    parser.add_argument("--once", action="store_true", help="Run one capture and exit")
    parser.add_argument("--no-initial-capture", action="store_true", help="Serve existing data first and wait for the next interval")
    return parser


async def run_once(repo: HotboardRepository, interval_hours: float) -> None:
    service = HotboardService(repo, interval_seconds=interval_hours * 60 * 60)
    summary = await service.capture_once()
    for platform, result in summary.items():
        print(f"{platform}: {result['status']} ({result['item_count']} rows)")


def main() -> None:
    args = build_parser().parse_args()
    repo = HotboardRepository(Path(args.db))
    if args.once:
        asyncio.run(run_once(repo, args.interval_hours))
        return

    service = HotboardService(repo, interval_seconds=args.interval_hours * 60 * 60)
    app = create_app(repo, service, initial_capture=not args.no_initial_capture)

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
