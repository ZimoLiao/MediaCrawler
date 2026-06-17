# -*- coding: utf-8 -*-
import pytest

import config
from cmd_arg import parse_cmd
from tools.cdp_browser import CDPBrowserManager


class DummyResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class RecordingAsyncClient:
    instances = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.requested_urls = []
        RecordingAsyncClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, timeout):
        self.requested_urls.append((url, timeout))
        return DummyResponse(
            200,
            {"webSocketDebuggerUrl": "ws://192.0.2.10:9444/devtools/browser/id"},
        )


class NotFoundAsyncClient(RecordingAsyncClient):
    async def get(self, url, timeout):
        self.requested_urls.append((url, timeout))
        return DummyResponse(404, text="")


class DummyBrowserContext:
    pages = []

    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class DummyBrowser:
    def __init__(self):
        self.closed = False

    def is_connected(self):
        return True

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_get_browser_websocket_url_uses_configured_host_and_ignores_proxy_env(
    monkeypatch,
):
    monkeypatch.setattr(config, "CDP_HOST", "192.0.2.10", raising=False)
    monkeypatch.setattr("tools.cdp_browser.httpx.AsyncClient", RecordingAsyncClient)
    RecordingAsyncClient.instances = []

    ws_url = await CDPBrowserManager()._get_browser_websocket_url(9444)

    assert ws_url == "ws://192.0.2.10:9444/devtools/browser/id"
    client = RecordingAsyncClient.instances[0]
    assert client.kwargs["trust_env"] is False
    assert client.requested_urls == [
        ("http://192.0.2.10:9444/json/version", 10)
    ]


@pytest.mark.asyncio
async def test_get_browser_websocket_url_falls_back_to_direct_browser_endpoint(
    monkeypatch,
):
    monkeypatch.setattr(config, "CDP_HOST", "127.0.0.1", raising=False)
    monkeypatch.setattr("tools.cdp_browser.httpx.AsyncClient", NotFoundAsyncClient)

    ws_url = await CDPBrowserManager()._get_browser_websocket_url(9222)

    assert ws_url == "ws://127.0.0.1:9222/devtools/browser"


@pytest.mark.asyncio
async def test_parse_cmd_overrides_cdp_host_and_port(monkeypatch):
    monkeypatch.setattr(config, "CDP_HOST", "localhost", raising=False)
    monkeypatch.setattr(config, "CDP_DEBUG_PORT", 9222)

    args = await parse_cmd(
        [
            "--platform",
            "xhs",
            "--cdp_host",
            "172.24.16.1",
            "--cdp_debug_port",
            "9224",
        ]
    )

    assert config.CDP_HOST == "172.24.16.1"
    assert config.CDP_DEBUG_PORT == 9224
    assert args.cdp_host == "172.24.16.1"
    assert args.cdp_debug_port == 9224


@pytest.mark.asyncio
async def test_cleanup_preserves_existing_browser_context(monkeypatch):
    monkeypatch.setattr(config, "CDP_CONNECT_EXISTING", True)
    context = DummyBrowserContext()
    browser = DummyBrowser()
    manager = CDPBrowserManager()
    manager.browser_context = context
    manager.browser = browser
    manager._using_existing_context = True

    await manager.cleanup()

    assert context.closed is False
    assert browser.closed is True
