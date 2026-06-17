---
title: Hotboard Monitor Service
type: feat
date: 2026-06-17
execution: code
---

# Hotboard Monitor Service

## Summary

Add a long-running hotboard monitor that captures all available items from supported public hotboard sources every six hours, stores the raw snapshots in SQLite, and serves a read-only dashboard over HTTP for Tailscale access.

## Problem Frame

The crawler can collect platform content by keyword, but it does not retain hotboard snapshots. Without periodic storage, "last week" rankings cannot be reconstructed after the fact.

## Requirements

- R1. The service captures the full available hotboard list for Weibo, Douyin, Bilibili, Tieba, Zhihu, Kuaishou, and Xiaohongshu on each scheduled run.
- R2. The service persists every captured item with platform, rank, title, heat, URL, source, and capture time in a local SQLite database.
- R3. Weekly summaries use only each platform's top 20 rows per snapshot while still retaining the full raw snapshot.
- R4. The dashboard is read-only and shows service status, latest per-platform captures, and seven-day top items.
- R5. The server binds to a configurable host and port, defaulting to `0.0.0.0:8765` so it is reachable through Tailscale.
- R6. The implementation must tolerate per-platform fetch failures without stopping the scheduler.

## Key Technical Decisions

- **Independent subsystem:** Place the monitor under `hotboard/` instead of extending `main.py` crawler modes, because this service is schedule-driven, public-source based, and does not need browser login state.
- **SQLite storage:** Use `sqlite3` from the standard library for a small local durable store, avoiding new runtime dependencies.
- **Rank-first scoring:** Aggregate seven-day summaries by appearances and rank score across only top-20 rows, because heat units differ by platform and are not directly comparable.
- **Read-only dashboard:** Expose only GET endpoints and static HTML. Manual triggering is intentionally excluded from the first version.

## Implementation Units

### U1. Hotboard source fetchers and parsers

- **Goal:** Implement source-specific fetch and parse functions for the seven target platforms.
- **Files:** Create `hotboard/sources.py`; test in `tests/test_hotboard_sources.py`.
- **Patterns:** Use `httpx.AsyncClient(trust_env=False)` like the CDP fix, because local proxy variables can break direct public requests.
- **Test scenarios:** Parse representative JSON and HTML fixtures; preserve all returned rows; normalize numeric heat text when possible; report failed fetches as platform errors.
- **Verification:** Unit tests pass without network access.

### U2. SQLite repository and aggregation

- **Goal:** Store snapshots and compute latest and seven-day summaries from persisted data.
- **Files:** Create `hotboard/storage.py`; test in `tests/test_hotboard_storage.py`.
- **Patterns:** Keep schema creation idempotent and use plain dictionaries for dashboard-facing records.
- **Test scenarios:** Insert mixed platform snapshots; latest returns newest snapshot per platform; weekly aggregation ignores rank > 20; raw rows remain stored.
- **Verification:** Unit tests pass against a temporary SQLite database.

### U3. Scheduler service and dashboard app

- **Goal:** Run periodic capture and serve a read-only FastAPI dashboard.
- **Files:** Create `hotboard/service.py`, `hotboard/app.py`, `hotboard/__main__.py`; test in `tests/test_hotboard_app.py`.
- **Patterns:** Follow the existing FastAPI style in `api/main.py`, but keep this app standalone.
- **Test scenarios:** Status endpoint reflects repository data; dashboard HTML renders without frontend build tooling; scheduler records success and failure snapshots.
- **Verification:** FastAPI TestClient tests pass.

### U4. Operational docs

- **Goal:** Document how to start the service and view it through Tailscale.
- **Files:** Create `docs/hotboard_monitor.md`.
- **Test scenarios:** Commands include default run, one-shot capture, custom host/port, and Tailscale URL shape.
- **Verification:** Commands map to actual CLI flags.

## Scope Boundaries

- The service does not backfill historical hotboards unless an upstream source exposes history.
- The dashboard does not authenticate users; Tailscale is the intended access boundary.
- The service does not use MediaCrawler browser login or CDP sessions.

## Risks & Dependencies

- Public hotboard endpoints may change or block requests. Each source failure is captured as a failed snapshot so the dashboard can show partial health.
- Some sources are public aggregation pages rather than platform-owned APIs. The source field records that provenance.
