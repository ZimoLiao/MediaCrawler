# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from hotboard.sources import HotboardItem


class HotboardRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS hotboard_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    source TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    item_count INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                );

                CREATE TABLE IF NOT EXISTS hotboard_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id INTEGER NOT NULL REFERENCES hotboard_snapshots(id) ON DELETE CASCADE,
                    platform TEXT NOT NULL,
                    rank INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    heat_text TEXT NOT NULL DEFAULT '',
                    heat_value REAL,
                    url TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_hotboard_snapshots_platform_time
                ON hotboard_snapshots(platform, captured_at DESC);

                CREATE INDEX IF NOT EXISTS idx_hotboard_items_snapshot_rank
                ON hotboard_items(snapshot_id, rank);
                """
            )

    def save_snapshot(
        self,
        platform: str,
        source: str,
        captured_at: datetime,
        items: Iterable[HotboardItem],
        *,
        status: str = "ok",
        error: str | None = None,
    ) -> int:
        rows = list(items)
        captured_at_iso = _to_utc(captured_at).isoformat()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO hotboard_snapshots(platform, source, captured_at, status, item_count, error)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (platform, source, captured_at_iso, status, len(rows), error),
            )
            snapshot_id = int(cursor.lastrowid)
            conn.executemany(
                """
                INSERT INTO hotboard_items(snapshot_id, platform, rank, title, heat_text, heat_value, url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        snapshot_id,
                        platform,
                        item.rank,
                        item.title,
                        item.heat_text,
                        item.heat_value,
                        item.url,
                    )
                    for item in rows
                ],
            )
            return snapshot_id

    def count_items(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM hotboard_items").fetchone()[0])

    def latest_by_platform(self) -> dict[str, dict]:
        query = """
            SELECT *
            FROM hotboard_snapshots s
            WHERE s.id = (
                SELECT id FROM hotboard_snapshots
                WHERE platform = s.platform
                ORDER BY captured_at DESC, id DESC
                LIMIT 1
            )
            ORDER BY platform
        """
        with self._connect() as conn:
            snapshots = conn.execute(query).fetchall()
            return {row["platform"]: self._snapshot_with_items(conn, row) for row in snapshots}

    def weekly_top(
        self,
        *,
        window_days: int = 7,
        top_n: int = 20,
        now: datetime | None = None,
        limit: int = 20,
    ) -> dict[str, list[dict]]:
        now_utc = _to_utc(now or datetime.now(timezone.utc))
        since = (now_utc - timedelta(days=window_days)).isoformat()
        query = """
            SELECT i.platform, i.title, i.url, i.rank, i.heat_text, i.heat_value, s.captured_at
            FROM hotboard_items i
            JOIN hotboard_snapshots s ON s.id = i.snapshot_id
            WHERE s.captured_at >= ? AND i.rank <= ? AND s.status = 'ok'
            ORDER BY i.platform, s.captured_at DESC, i.rank ASC
        """
        grouped: dict[str, dict[str, dict]] = {}
        with self._connect() as conn:
            for row in conn.execute(query, (since, top_n)):
                platform = row["platform"]
                title = row["title"]
                platform_rows = grouped.setdefault(platform, {})
                item = platform_rows.setdefault(
                    title,
                    {
                        "title": title,
                        "url": row["url"],
                        "appearances": 0,
                        "score": 0,
                        "best_rank": row["rank"],
                        "latest_rank": row["rank"],
                        "latest_heat": row["heat_text"],
                        "latest_seen_at": row["captured_at"],
                    },
                )
                item["appearances"] += 1
                item["score"] += top_n - int(row["rank"]) + 1
                item["best_rank"] = min(item["best_rank"], int(row["rank"]))
                if row["captured_at"] >= item["latest_seen_at"]:
                    item["latest_rank"] = int(row["rank"])
                    item["latest_heat"] = row["heat_text"]
                    item["latest_seen_at"] = row["captured_at"]
                    item["url"] = row["url"]

        result: dict[str, list[dict]] = {}
        for platform, items in grouped.items():
            ordered = sorted(
                items.values(),
                key=lambda item: (-item["score"], item["best_rank"], item["title"]),
            )
            result[platform] = ordered[:limit]
        return result

    def recent_snapshots(self, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT platform, source, captured_at, status, item_count, error
                FROM hotboard_snapshots
                ORDER BY captured_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def status(self, *, now: datetime | None = None) -> dict:
        latest = self.latest_by_platform()
        now_utc = _to_utc(now or datetime.now(timezone.utc))
        return {
            "now": now_utc.isoformat(),
            "db_path": str(self.db_path),
            "snapshot_count": self._count("hotboard_snapshots"),
            "item_count": self._count("hotboard_items"),
            "platforms": {
                platform: {
                    "source": data["source"],
                    "captured_at": data["captured_at"],
                    "status": data["status"],
                    "item_count": data["item_count"],
                    "error": data["error"],
                }
                for platform, data in latest.items()
            },
        }

    def _count(self, table: str) -> int:
        with self._connect() as conn:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def _snapshot_with_items(self, conn: sqlite3.Connection, snapshot: sqlite3.Row) -> dict:
        items = conn.execute(
            """
            SELECT rank, title, heat_text, heat_value, url
            FROM hotboard_items
            WHERE snapshot_id = ?
            ORDER BY rank ASC
            """,
            (snapshot["id"],),
        ).fetchall()
        data = dict(snapshot)
        data["items"] = [dict(item) for item in items]
        return data


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

