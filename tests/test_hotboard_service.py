# -*- coding: utf-8 -*-
import pytest

from hotboard.service import HotboardService
from hotboard.sources import HotboardItem
from hotboard.storage import HotboardRepository


@pytest.mark.asyncio
async def test_capture_once_records_success_and_failure(monkeypatch, tmp_path):
    async def fake_fetch_all_sources(_sources):
        return {
            "weibo": (
                "weibo-hot-search",
                [HotboardItem(1, "成功话题", "100", 100, "https://example.com/success")],
            ),
            "bili": ("bilibili-ranking", RuntimeError("blocked")),
        }

    monkeypatch.setattr("hotboard.service.fetch_all_sources", fake_fetch_all_sources)
    repo = HotboardRepository(tmp_path / "hotboard.db")
    service = HotboardService(repo)

    summary = await service.capture_once()

    assert summary["weibo"]["status"] == "ok"
    assert summary["bili"]["status"] == "error"
    latest = repo.latest_by_platform()
    assert latest["weibo"]["items"][0]["title"] == "成功话题"
    assert latest["bili"]["status"] == "error"
    assert "blocked" in latest["bili"]["error"]
