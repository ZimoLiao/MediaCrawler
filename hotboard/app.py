# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import html
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from hotboard.service import HotboardService
from hotboard.storage import HotboardRepository


PLATFORM_LABELS = {
    "weibo": "微博",
    "douyin": "抖音",
    "bili": "B站",
    "tieba": "贴吧",
    "zhihu": "知乎",
    "kuaishou": "快手",
    "xhs": "小红书",
}


def create_app(
    repo: HotboardRepository,
    service: HotboardService | None = None,
    *,
    initial_capture: bool = True,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        task: asyncio.Task | None = None
        if service is not None:
            task = asyncio.create_task(service.run_loop(initial_capture=initial_capture))
        try:
            yield
        finally:
            if service is not None:
                service.stop()
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    app = FastAPI(title="Hotboard Monitor", version="1.0.0", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> str:
        return render_dashboard(repo)

    @app.get("/api/status")
    async def api_status() -> dict:
        return repo.status()

    @app.get("/api/latest")
    async def api_latest() -> dict:
        return repo.latest_by_platform()

    @app.get("/api/weekly")
    async def api_weekly(window_days: int = 7, top_n: int = 20) -> dict:
        return repo.weekly_top(window_days=window_days, top_n=top_n)

    @app.get("/api/snapshots")
    async def api_snapshots(limit: int = 50) -> list[dict]:
        return repo.recent_snapshots(limit=limit)

    return app


def render_dashboard(repo: HotboardRepository) -> str:
    status = repo.status()
    latest = repo.latest_by_platform()
    weekly = repo.weekly_top(window_days=7, top_n=20, limit=3)
    cards = "\n".join(_render_platform_card(platform, latest.get(platform), weekly.get(platform, [])) for platform in PLATFORM_LABELS)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="300">
  <title>Hotboard Monitor</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f6f7f9; color: #1f2933; }}
    header {{ padding: 20px 28px; background: #111827; color: white; }}
    h1 {{ margin: 0 0 6px; font-size: 24px; }}
    main {{ padding: 20px 28px 40px; }}
    .meta {{ color: #cbd5e1; font-size: 13px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }}
    .card {{ background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; }}
    .card h2 {{ margin: 0 0 8px; font-size: 18px; }}
    .status {{ font-size: 13px; color: #64748b; margin-bottom: 12px; }}
    ol {{ margin: 0; padding-left: 22px; }}
    li {{ margin: 7px 0; line-height: 1.35; }}
    a {{ color: #0f766e; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .section-title {{ font-weight: 650; margin: 12px 0 6px; font-size: 13px; color: #334155; }}
    .error {{ color: #b42318; }}
    .empty {{ color: #94a3b8; }}
  </style>
</head>
<body>
  <header>
    <h1>Hotboard Monitor</h1>
    <div class="meta">SQLite: {html.escape(status["db_path"])} · snapshots: {status["snapshot_count"]} · items: {status["item_count"]} · refreshed: {html.escape(status["now"])}</div>
  </header>
  <main>
    <div class="grid">{cards}</div>
  </main>
</body>
</html>"""


def _render_platform_card(platform: str, latest: dict | None, weekly_items: list[dict]) -> str:
    label = PLATFORM_LABELS.get(platform, platform)
    if not latest:
        return f'<section class="card"><h2>{html.escape(label)}</h2><p class="empty">No captures yet.</p></section>'
    status_class = "error" if latest.get("status") != "ok" else ""
    latest_list = _render_items(latest.get("items", [])[:3], title_key="title")
    weekly_list = _render_items(weekly_items, title_key="title", weekly=True)
    error = f' · <span class="error">{html.escape(str(latest.get("error") or ""))}</span>' if latest.get("error") else ""
    return f"""
    <section class="card">
      <h2>{html.escape(label)}</h2>
      <div class="status {status_class}">{html.escape(latest.get("captured_at", ""))} · {html.escape(latest.get("source", ""))} · {html.escape(latest.get("status", ""))} · {latest.get("item_count", 0)} rows{error}</div>
      <div class="section-title">Latest Top 3</div>
      {latest_list}
      <div class="section-title">7-day Summary Top 3 (rank <= 20)</div>
      {weekly_list}
    </section>
    """


def _render_items(items: list[dict], *, title_key: str, weekly: bool = False) -> str:
    if not items:
        return '<p class="empty">No data.</p>'
    rows = []
    for item in items:
        title = html.escape(str(item.get(title_key, "")))
        url = html.escape(str(item.get("url", "")))
        suffix = ""
        if weekly:
            suffix = f' <span class="status">score {item.get("score", 0)} · seen {item.get("appearances", 0)}x</span>'
        elif item.get("heat_text"):
            suffix = f' <span class="status">{html.escape(str(item.get("heat_text")))}</span>'
        link = f'<a href="{url}" target="_blank" rel="noreferrer">{title}</a>' if url else title
        rows.append(f"<li>{link}{suffix}</li>")
    return "<ol>" + "".join(rows) + "</ol>"
