# -*- coding: utf-8 -*-
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from hotboard.app import create_app
from hotboard.sources import HotboardItem
from hotboard.storage import HotboardRepository


def test_dashboard_and_api_are_read_only(tmp_path):
    repo = HotboardRepository(tmp_path / "hotboard.db")
    repo.save_snapshot(
        "weibo",
        "weibo-api",
        datetime(2026, 6, 17, 8, tzinfo=timezone.utc),
        [HotboardItem(1, "姆巴佩梅开二度", "2482643", 2482643, "https://example.com")],
    )
    client = TestClient(create_app(repo))

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "Hotboard Monitor" in dashboard.text
    assert "姆巴佩梅开二度" in dashboard.text

    latest = client.get("/api/latest")
    assert latest.status_code == 200
    assert latest.json()["weibo"]["items"][0]["title"] == "姆巴佩梅开二度"

    assert client.post("/api/latest").status_code == 405
