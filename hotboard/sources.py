# -*- coding: utf-8 -*-
from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote

import httpx


@dataclass(frozen=True)
class HotboardItem:
    rank: int
    title: str
    heat_text: str
    heat_value: float | None
    url: str


class SourceParseError(ValueError):
    """Raised when a source response is successful HTTP but unusable."""


@dataclass(frozen=True)
class HotboardSource:
    platform: str
    source: str
    url: str
    parser: Callable[[object], list[HotboardItem]]
    response_type: str = "json"
    referer: str = ""


def parse_heat_value(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    multiplier = 1.0
    if text.endswith("w") or text.endswith("万"):
        multiplier = 10000.0
        text = text[:-1]
    elif text.endswith("亿"):
        multiplier = 100000000.0
        text = text[:-1]
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group(0)) * multiplier


def _clean_text(value: object) -> str:
    text = html_lib.unescape(str(value or ""))
    text = re.sub(r"<.*?>", " ", text, flags=re.S)
    return " ".join(text.split())


def parse_weibo_hot_search(payload: object) -> list[HotboardItem]:
    data = payload if isinstance(payload, dict) else {}
    rows = data.get("data", {}).get("realtime", [])
    items: list[HotboardItem] = []
    for index, row in enumerate(rows, start=1):
        title = _clean_text(row.get("word") or row.get("note") or row.get("word_scheme"))
        if not title:
            continue
        heat = row.get("num", "")
        items.append(
            HotboardItem(
                rank=index,
                title=title,
                heat_text=str(heat),
                heat_value=parse_heat_value(heat),
                url=f"https://s.weibo.com/weibo?q={quote(title)}",
            )
        )
    return items


def parse_douyin_hot_search(payload: object) -> list[HotboardItem]:
    data = payload if isinstance(payload, dict) else {}
    rows = data.get("word_list", [])
    items: list[HotboardItem] = []
    for index, row in enumerate(rows, start=1):
        title = _clean_text(row.get("word"))
        if not title:
            continue
        heat = row.get("hot_value", "")
        items.append(
            HotboardItem(
                rank=index,
                title=title,
                heat_text=str(heat),
                heat_value=parse_heat_value(heat),
                url=f"https://www.douyin.com/search/{quote(title)}",
            )
        )
    return items


def parse_bilibili_ranking(payload: object) -> list[HotboardItem]:
    data = payload if isinstance(payload, dict) else {}
    if data.get("code") not in (None, 0):
        raise SourceParseError(f"bilibili business error: {data.get('code')} {data.get('message')}")
    rows = data.get("data", {}).get("list", [])
    items: list[HotboardItem] = []
    for index, row in enumerate(rows, start=1):
        title = _clean_text(row.get("title"))
        aid = row.get("aid")
        if not title or not aid:
            continue
        heat = row.get("stat", {}).get("view", "")
        items.append(
            HotboardItem(
                rank=index,
                title=title,
                heat_text=str(heat),
                heat_value=parse_heat_value(heat),
                url=f"https://www.bilibili.com/video/av{aid}",
            )
        )
    return items


def parse_tieba_topics(payload: object) -> list[HotboardItem]:
    data = payload if isinstance(payload, dict) else {}
    rows = data.get("data", {}).get("bang_topic", {}).get("topic_list", [])
    items: list[HotboardItem] = []
    for index, row in enumerate(rows, start=1):
        title = _clean_text(row.get("topic_name"))
        if not title:
            continue
        heat = row.get("discuss_num") or row.get("heat") or ""
        topic_id = row.get("topic_id", "")
        items.append(
            HotboardItem(
                rank=index,
                title=title,
                heat_text=str(heat),
                heat_value=parse_heat_value(heat),
                url=f"https://tieba.baidu.com/hottopic/browse/topicList?topic_id={topic_id}",
            )
        )
    return items


def parse_kuaishou_rebang(page_html: object) -> list[HotboardItem]:
    text = str(page_html or "")
    items: list[HotboardItem] = []
    pattern = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
    for match in pattern.finditer(text):
        body = _clean_text(match.group(2))
        parsed = re.match(r"^(\d+)\s+(.+?)\s+热度：([\d.万亿w,]+)", body)
        if not parsed:
            continue
        heat_text = parsed.group(3)
        items.append(
            HotboardItem(
                rank=int(parsed.group(1)),
                title=parsed.group(2).strip(),
                heat_text=heat_text,
                heat_value=parse_heat_value(heat_text),
                url=html_lib.unescape(match.group(1)),
            )
        )
    return items


def parse_zhihu_rebang(page_html: object) -> list[HotboardItem]:
    text = str(page_html or "")
    items: list[HotboardItem] = []
    pattern = re.compile(r'<a[^>]+href="([^"]*zhihu\.com/question/[^"]+)"[^>]*>(.*?)</a>', re.S)
    for match in pattern.finditer(text):
        body = _clean_text(match.group(2))
        parsed = re.match(r"^(\d+)\s+(.+?(?:？|\?))", body)
        if not parsed:
            continue
        items.append(
            HotboardItem(
                rank=int(parsed.group(1)),
                title=parsed.group(2).strip(),
                heat_text="",
                heat_value=None,
                url=html_lib.unescape(match.group(1)),
            )
        )
    return items


def parse_tophub_table(page_html: object) -> list[HotboardItem]:
    text = str(page_html or "")
    table_match = re.search(r'<div class="jc rank-all-item">(.*?)</table>', text, re.S)
    block = table_match.group(1) if table_match else text
    items: list[HotboardItem] = []
    for row in re.findall(r"<tr>(.*?)</tr>", block, re.S):
        rank_match = re.search(r'<td[^>]*align="center"[^>]*>\s*(\d+)\.', row)
        item_match = re.search(
            r'<td><a[^>]+href="([^"]+)"[^>]*>(.*?)</a></td>\s*<td class="ws">(.*?)</td>',
            row,
            re.S,
        )
        if not rank_match or not item_match:
            continue
        title = _clean_text(item_match.group(2))
        heat_text = _clean_text(item_match.group(3))
        if not title:
            continue
        items.append(
            HotboardItem(
                rank=int(rank_match.group(1)),
                title=title,
                heat_text=heat_text,
                heat_value=parse_heat_value(heat_text),
                url=html_lib.unescape(item_match.group(1)),
            )
        )
    return items


def parse_tophub_media_table(page_html: object) -> list[HotboardItem]:
    text = str(page_html or "")
    table_match = re.search(r'<div class="jc rank-all-item">(.*?)</table>', text, re.S)
    block = table_match.group(1) if table_match else text
    items: list[HotboardItem] = []
    for row in re.findall(r"<tr>(.*?)</tr>", block, re.S):
        rank_match = re.search(r'<td[^>]*align="center"[^>]*>\s*(\d+)\.', row)
        item_match = re.search(
            r'<td class="al">\s*<div><a[^>]+href="([^"]+)"[^>]*>(.*?)</a></div>\s*<div class="item-desc">(.*?)</div>',
            row,
            re.S,
        )
        if not rank_match or not item_match:
            continue
        title = _clean_text(item_match.group(2))
        heat_text = _clean_text(item_match.group(3))
        if not title:
            continue
        items.append(
            HotboardItem(
                rank=int(rank_match.group(1)),
                title=title,
                heat_text=heat_text,
                heat_value=parse_heat_value(heat_text),
                url=html_lib.unescape(item_match.group(1)),
            )
        )
    return items


HOTBOARD_SOURCES: tuple[HotboardSource, ...] = (
    HotboardSource(
        platform="weibo",
        source="weibo-hot-search",
        url="https://weibo.com/ajax/side/hotSearch",
        parser=parse_weibo_hot_search,
        referer="https://weibo.com/hot/search",
    ),
    HotboardSource(
        platform="douyin",
        source="douyin-hot-search",
        url="https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/",
        parser=parse_douyin_hot_search,
        referer="https://www.douyin.com/hot",
    ),
    HotboardSource(
        platform="bili",
        source="tophub-bilibili-ranking",
        url="https://tophub.today/n/74KvxwokxM",
        parser=parse_tophub_media_table,
        response_type="html",
        referer="https://tophub.today/",
    ),
    HotboardSource(
        platform="tieba",
        source="tieba-hot-topic",
        url="https://tieba.baidu.com/hottopic/browse/topicList",
        parser=parse_tieba_topics,
        referer="https://tieba.baidu.com/",
    ),
    HotboardSource(
        platform="zhihu",
        source="rebang-zhihu-hot-search",
        url="https://www.rebang.vip/zhihu/hot-search",
        parser=parse_zhihu_rebang,
        response_type="html",
    ),
    HotboardSource(
        platform="kuaishou",
        source="rebang-kuaishou-hot-search",
        url="https://www.rebang.vip/kuaishou/hot-search",
        parser=parse_kuaishou_rebang,
        response_type="html",
    ),
    HotboardSource(
        platform="xhs",
        source="tophub-xiaohongshu-hot",
        url="https://tophub.today/n/L4MdA5ldxD",
        parser=parse_tophub_table,
        response_type="html",
        referer="https://tophub.today/",
    ),
)


async def fetch_source(client: httpx.AsyncClient, source: HotboardSource) -> list[HotboardItem]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if source.referer:
        headers["Referer"] = source.referer
    response = await client.get(source.url, headers=headers, timeout=30)
    response.raise_for_status()
    payload: object = response.text if source.response_type == "html" else response.json()
    items = source.parser(payload)
    if not items:
        raise SourceParseError(f"{source.source} returned no hotboard items")
    return items


async def fetch_all_sources(sources: tuple[HotboardSource, ...] = HOTBOARD_SOURCES) -> dict[str, tuple[str, list[HotboardItem] | Exception]]:
    results: dict[str, tuple[str, list[HotboardItem] | Exception]] = {}
    async with httpx.AsyncClient(trust_env=False, follow_redirects=True) as client:
        for source in sources:
            try:
                results[source.platform] = (source.source, await fetch_source(client, source))
            except Exception as exc:
                results[source.platform] = (source.source, exc)
    return results
