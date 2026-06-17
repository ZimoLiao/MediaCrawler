# -*- coding: utf-8 -*-
from datetime import datetime, timedelta, timezone

from hotboard.sources import HotboardItem
from hotboard.storage import HotboardRepository


def test_repository_keeps_raw_rows_but_weekly_summary_uses_top_20(tmp_path):
    repo = HotboardRepository(tmp_path / "hotboard.db")
    captured_at = datetime(2026, 6, 17, 8, tzinfo=timezone.utc)
    rows = [
        HotboardItem(rank=1, title="冠军", heat_text="100", heat_value=100, url="https://example.com/1"),
        HotboardItem(rank=20, title="第二十", heat_text="20", heat_value=20, url="https://example.com/20"),
        HotboardItem(rank=21, title="第二十一", heat_text="19", heat_value=19, url="https://example.com/21"),
    ]

    repo.save_snapshot("weibo", "weibo-api", captured_at, rows, status="ok")

    assert repo.count_items() == 3
    weekly = repo.weekly_top(window_days=7, top_n=20, now=captured_at + timedelta(hours=1))
    titles = [row["title"] for row in weekly["weibo"]]
    assert titles == ["冠军", "第二十"]


def test_latest_returns_newest_snapshot_per_platform(tmp_path):
    repo = HotboardRepository(tmp_path / "hotboard.db")
    first = datetime(2026, 6, 17, 0, tzinfo=timezone.utc)
    second = datetime(2026, 6, 17, 6, tzinfo=timezone.utc)

    repo.save_snapshot("weibo", "weibo-api", first, [HotboardItem(1, "旧", "1", 1, "u1")])
    repo.save_snapshot("weibo", "weibo-api", second, [HotboardItem(1, "新", "2", 2, "u2")])
    repo.save_snapshot("douyin", "douyin-api", first, [HotboardItem(1, "抖音", "3", 3, "u3")])

    latest = repo.latest_by_platform()

    assert latest["weibo"]["captured_at"] == second.isoformat()
    assert latest["weibo"]["items"][0]["title"] == "新"
    assert latest["douyin"]["items"][0]["title"] == "抖音"


def test_failed_snapshot_is_recorded_without_items(tmp_path):
    repo = HotboardRepository(tmp_path / "hotboard.db")
    captured_at = datetime(2026, 6, 17, 8, tzinfo=timezone.utc)

    repo.save_snapshot("bili", "bili-ranking", captured_at, [], status="error", error="blocked")

    status = repo.status(now=captured_at)
    assert status["platforms"]["bili"]["status"] == "error"
    assert status["platforms"]["bili"]["error"] == "blocked"
    assert status["platforms"]["bili"]["item_count"] == 0
