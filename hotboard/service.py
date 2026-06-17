# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from hotboard.sources import HOTBOARD_SOURCES, HotboardSource, fetch_all_sources
from hotboard.storage import HotboardRepository


class HotboardService:
    def __init__(
        self,
        repo: HotboardRepository,
        *,
        interval_seconds: float = 6 * 60 * 60,
        sources: tuple[HotboardSource, ...] = HOTBOARD_SOURCES,
    ):
        self.repo = repo
        self.interval_seconds = interval_seconds
        self.sources = sources
        self._stop_event = asyncio.Event()

    async def capture_once(self) -> dict[str, dict]:
        captured_at = datetime.now(timezone.utc)
        results = await fetch_all_sources(self.sources)
        summary: dict[str, dict] = {}
        for platform, (source_name, result) in results.items():
            if isinstance(result, Exception):
                self.repo.save_snapshot(
                    platform,
                    source_name,
                    captured_at,
                    [],
                    status="error",
                    error=f"{type(result).__name__}: {result}",
                )
                summary[platform] = {"status": "error", "item_count": 0, "error": str(result)}
            else:
                self.repo.save_snapshot(platform, source_name, captured_at, result)
                summary[platform] = {"status": "ok", "item_count": len(result), "error": None}
        return summary

    async def run_loop(self, *, initial_capture: bool = True) -> None:
        if initial_capture:
            await self.capture_once()
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                await self.capture_once()

    def stop(self) -> None:
        self._stop_event.set()

