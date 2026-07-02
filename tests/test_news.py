import app.tools.news as news
from app.tools.news import search_news


async def test_search_news_dedupes_near_identical_headlines(monkeypatch):
    raw = [
        {"headline": "NVDA soars on earnings beat", "source": "A", "url": "u1", "datetime": 1700000000, "summary": "s"},
        {"headline": "NVDA  soars on earnings  beat", "source": "B", "url": "u2", "datetime": 1700000100, "summary": "s"},
        {"headline": "Fed holds rates steady", "source": "C", "url": "u3", "datetime": 1700000200, "summary": "s"},
    ]
    monkeypatch.setattr(news, "_fetch_finnhub_news", lambda q, lb, mx: raw)
    monkeypatch.setattr(news, "get_settings", lambda: type("S", (), {"finnhub_api_key": "x"})())

    out = await search_news({"query": "NVDA"})
    assert out["source"] == "finnhub"
    assert out["count"] == 2  # near-duplicate dropped
    assert {i["headline"] for i in out["items"]} == {
        "NVDA soars on earnings beat",
        "Fed holds rates steady",
    }


async def test_search_news_falls_back_to_yfinance_on_finnhub_error(monkeypatch):
    def boom(q, lb, mx):
        raise RuntimeError("finnhub down")

    yf_items = [
        {
            "content": {
                "title": "SHOP jumps 5%",
                "provider": {"displayName": "Reuters"},
                "canonicalUrl": {"url": "http://x"},
                "pubDate": "2024-01-01T00:00:00Z",
                "summary": "long summary " * 100,
            }
        }
    ]
    monkeypatch.setattr(news, "_fetch_finnhub_news", boom)
    monkeypatch.setattr(news, "_fetch_yfinance_news", lambda q: yf_items)

    out = await search_news({"query": "SHOP.TO", "lookback_days": 5})
    assert out["source"] == "yfinance"
    assert out["count"] == 1
    item = out["items"][0]
    assert item["headline"] == "SHOP jumps 5%"
    assert item["source"] == "Reuters"
    # summary is truncated, never full text
    assert len(item["summary"]) <= news.SUMMARY_MAX_CHARS


async def test_search_news_validates_inputs():
    for bad in [{"query": ""}, {"query": "x", "lookback_days": 40}, {"query": "x", "max_results": 99}]:
        try:
            await search_news(bad)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass


def test_finnhub_symbol_candidates_extracts_ticker_from_phrase():
    assert news._finnhub_symbol_candidates("NOW ServiceNow stock") == ["NOW"]
    assert news._finnhub_symbol_candidates("SHOP.TO Shopify") == ["SHOP.TO", "SHOP"]
