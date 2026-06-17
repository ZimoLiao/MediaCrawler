# -*- coding: utf-8 -*-
import pytest

from hotboard.sources import (
    HotboardItem,
    SourceParseError,
    parse_bilibili_ranking,
    parse_douyin_hot_search,
    parse_kuaishou_rebang,
    parse_tophub_media_table,
    parse_tophub_table,
    parse_weibo_hot_search,
)


def test_parse_weibo_hot_search_preserves_rank_heat_and_url():
    payload = {
        "data": {
            "realtime": [
                {"word": "话题一", "num": 123, "rank": 0},
                {"word": "话题二", "num": 45, "rank": 1, "word_scheme": "话题二"},
            ]
        }
    }

    items = parse_weibo_hot_search(payload)

    assert items == [
        HotboardItem(rank=1, title="话题一", heat_text="123", heat_value=123.0, url="https://s.weibo.com/weibo?q=%E8%AF%9D%E9%A2%98%E4%B8%80"),
        HotboardItem(rank=2, title="话题二", heat_text="45", heat_value=45.0, url="https://s.weibo.com/weibo?q=%E8%AF%9D%E9%A2%98%E4%BA%8C"),
    ]


def test_parse_douyin_hot_search_preserves_all_rows():
    payload = {"word_list": [{"word": "法国3:1塞内加尔", "hot_value": 12166333}]}

    items = parse_douyin_hot_search(payload)

    assert items[0].rank == 1
    assert items[0].title == "法国3:1塞内加尔"
    assert items[0].heat_text == "12166333"
    assert items[0].heat_value == 12166333.0
    assert items[0].url == "https://www.douyin.com/search/%E6%B3%95%E5%9B%BD3%3A1%E5%A1%9E%E5%86%85%E5%8A%A0%E5%B0%94"


def test_parse_bilibili_ranking_uses_aid_url_and_view_heat():
    payload = {
        "data": {
            "list": [
                {
                    "aid": 116749374593001,
                    "title": "《原神》动画短片",
                    "stat": {"view": 4980670},
                }
            ]
        }
    }

    items = parse_bilibili_ranking(payload)

    assert items == [
        HotboardItem(
            rank=1,
            title="《原神》动画短片",
            heat_text="4980670",
            heat_value=4980670.0,
            url="https://www.bilibili.com/video/av116749374593001",
        )
    ]


def test_parse_bilibili_ranking_rejects_business_error():
    payload = {"code": -352, "message": "-352"}

    with pytest.raises(SourceParseError):
        parse_bilibili_ranking(payload)


def test_parse_rebang_kuaishou_html_rows():
    html = """
    <a href="https://www.kuaishou.com/short-video/abc">1 沙特1比1战平乌拉圭 热度：11657663</a>
    <a href="https://www.kuaishou.com/short-video/def">2 世界杯阿根廷vs阿尔及利亚 热度：11327751</a>
    """

    items = parse_kuaishou_rebang(html)

    assert [item.title for item in items] == ["沙特1比1战平乌拉圭", "世界杯阿根廷vs阿尔及利亚"]
    assert [item.rank for item in items] == [1, 2]
    assert items[0].heat_value == 11657663.0


def test_parse_tophub_table_ignores_page_chrome():
    html = """
    <nav><a href="/">今日热榜 首页</a></nav>
    <div class="jc rank-all-item"><table><tbody>
      <tr><td align="center">1.</td><td><a href="https://www.xiaohongshu.com/search_result?keyword=a">用万能旅行拍照姿势美美出片</a></td><td class="ws">918.6w</td></tr>
      <tr><td align="center">2.</td><td><a href="https://www.xiaohongshu.com/search_result?keyword=b">耗时三年拍下古诗词里的中国</a></td><td class="ws">907w</td></tr>
    </tbody></table></div>
    """

    items = parse_tophub_table(html)

    assert [item.title for item in items] == ["用万能旅行拍照姿势美美出片", "耗时三年拍下古诗词里的中国"]
    assert items[0].heat_value == 9186000.0


def test_parse_tophub_media_table_handles_bilibili_rows():
    html = """
    <div class="jc rank-all-item"><table><tbody>
      <tr>
        <td align="center">1.</td>
        <td class="al"><img src="cover.jpg" /></td>
        <td class="al"><div><a href="https://www.bilibili.com/video/av1/">《原神》动画短片</a></div><div class="item-desc">498.4万</div></td>
      </tr>
    </tbody></table></div>
    """

    items = parse_tophub_media_table(html)

    assert items == [
        HotboardItem(
            rank=1,
            title="《原神》动画短片",
            heat_text="498.4万",
            heat_value=4984000.0,
            url="https://www.bilibili.com/video/av1/",
        )
    ]
