from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def _load_social_smoke():
    script = Path(__file__).resolve().parents[1] / "scripts" / "social-smoke.py"
    spec = importlib.util.spec_from_file_location("social_smoke", script)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    def __init__(self, payload: dict | None = None, *, content: bytes | None = None, headers: dict[str, str] | None = None):
        self._payload = payload
        self._content = content
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        if self._content is not None:
            return self._content
        return json.dumps(self._payload).encode("utf-8")


def test_bili_search_fallback_writes_contents_jsonl(tmp_path, monkeypatch):
    module = _load_social_smoke()
    payload = {
        "code": 0,
        "data": {
            "result": [{
                "bvid": "BV1test",
                "arcurl": "https://www.bilibili.com/video/BV1test",
                "title": "hello <em class=\"keyword\">Joi</em>",
                "description": "desc",
                "author": "author",
                "mid": 123,
                "pubdate": 1781674995,
                "play": 9,
                "review": 2,
                "favorites": 3,
                "like": 4,
                "pic": "//i0.hdslb.com/test.png",
            }]
        },
    }
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_args, **_kwargs: _FakeResponse(payload))

    module._run_bili_search_fallback(tmp_path, "Joi", limit=1)

    rows = list((tmp_path / "bili" / "jsonl").glob("search_contents_*.jsonl"))
    assert len(rows) == 1
    row = json.loads(rows[0].read_text(encoding="utf-8").strip())
    assert row["video_id"] == "BV1test"
    assert row["title"] == "hello Joi"
    assert row["nickname"] == "author"
    assert row["source_keyword"] == "Joi"
    assert row["cover_url"] == "https://i0.hdslb.com/test.png"


def test_bili_detail_fallback_writes_contents_jsonl(tmp_path, monkeypatch):
    module = _load_social_smoke()
    payload = {
        "code": 0,
        "data": {
            "bvid": "BV1detail",
            "aid": 42,
            "title": "detail title",
            "desc": "detail desc",
            "pubdate": 1781674995,
            "pic": "https://example.com/cover.jpg",
            "owner": {"name": "author", "mid": 123},
            "stat": {"view": 9, "reply": 2, "favorite": 3, "like": 4},
        },
    }
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_args, **_kwargs: _FakeResponse(payload))

    module._run_bili_detail_fallback(tmp_path, "https://www.bilibili.com/video/BV1detail")

    rows = list((tmp_path / "bili" / "jsonl").glob("detail_contents_*.jsonl"))
    assert len(rows) == 1
    row = json.loads(rows[0].read_text(encoding="utf-8").strip())
    assert row["video_id"] == "BV1detail"
    assert row["video_url"] == "https://www.bilibili.com/video/BV1detail"
    assert row["title"] == "detail title"
    assert row["nickname"] == "author"


def test_headless_auto_uses_headed_browser_for_douyin_only():
    module = _load_social_smoke()

    assert module._resolve_headless("auto", "dy") is False
    assert module._resolve_headless("auto", "xhs") is True
    assert module._resolve_headless("true", "dy") is True
    assert module._resolve_headless("false", "xhs") is False


def test_empty_douyin_search_output_raises_verification_diagnostic(tmp_path):
    module = _load_social_smoke()

    with pytest.raises(RuntimeError, match="verify_check"):
        module._raise_if_empty_search(tmp_path, "dy", "search")


def test_bili_fallback_cover_url_can_be_downloaded(tmp_path, monkeypatch):
    module = _load_social_smoke()
    payload = {
        "code": 0,
        "data": {
            "result": [{
                "bvid": "BV1test",
                "arcurl": "https://www.bilibili.com/video/BV1test",
                "title": "hello Joi",
                "pic": "//i0.hdslb.com/test.png",
            }]
        },
    }

    def fake_urlopen(request, *_args, **_kwargs):
        url = request.full_url
        if "search/type" in url:
            return _FakeResponse(payload)
        assert url == "https://i0.hdslb.com/test.png"
        return _FakeResponse(content=b"image-bytes", headers={"Content-Type": "image/jpeg"})

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    module._run_bili_search_fallback(tmp_path, "Joi", limit=1)
    manifest = module._download_images(tmp_path, "bili", limit=1)

    assert len(manifest) == 1
    assert manifest[0]["url"] == "https://i0.hdslb.com/test.png"
    assert Path(manifest[0]["path"]).read_bytes() == b"image-bytes"
