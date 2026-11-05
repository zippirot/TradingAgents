"""Ticker news falls back to Yahoo search when its quote feed is unavailable."""

from datetime import UTC, datetime

import pytest
from yfinance.exceptions import YFRateLimitError

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors.yahoo import common, news

DAY = "2026-10-01"


def article(title, day=DAY, tags=("AAPL",)):
    return {
        "title": title,
        "providerPublishTime": int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp()),
        "relatedTickers": list(tags),
    }


def install_yahoo(monkeypatch, feed, search_articles=(), search_error=None):
    calls = {"quote": 0, "search": 0}

    class Ticker:
        def __init__(self, symbol):
            assert symbol == "AAPL"

        def get_news(self, *, count):
            calls["quote"] += 1
            if isinstance(feed, Exception):
                raise feed
            return feed

    class Search:
        def __init__(self, symbol, *, news_count):
            assert symbol == "AAPL"
            calls["search"] += 1
            if search_error:
                raise search_error
            self.news = list(search_articles)
            self.quotes = [{"symbol": "AAPL"}]

    monkeypatch.setattr(news.yf, "Ticker", Ticker)
    monkeypatch.setattr(news.yf, "Search", Search)
    return calls


@pytest.mark.unit
@pytest.mark.parametrize("feed", [[article("QUOTE")], []], ids=["quote-success", "empty-quote"])
def test_quote_feed_or_empty_feed_uses_expected_source(monkeypatch, feed):
    calls = install_yahoo(monkeypatch, feed, [article("SEARCH")])
    result = news.get_news_yfinance("AAPL", DAY, DAY)
    assert ("QUOTE" in result, "SEARCH" in result) == (bool(feed), not bool(feed))
    assert calls == {"quote": 1, "search": int(not bool(feed))}


@pytest.mark.unit
def test_quote_failure_uses_only_tagged_in_window_search_articles(monkeypatch):
    calls = install_yahoo(
        monkeypatch,
        TimeoutError("quote timed out"),
        [article("MATCH"), article("OTHER", tags=("MSFT",)), article("FUTURE", "2026-10-02")],
    )
    result = news.get_news_yfinance("AAPL", DAY, DAY)
    assert "MATCH" in result
    assert "OTHER" not in result and "FUTURE" not in result
    assert calls == {"quote": 1, "search": 1}


@pytest.mark.unit
@pytest.mark.parametrize("articles", [[], [article("OTHER", tags=("MSFT",))]], ids=["empty", "untagged"])
def test_quote_failure_without_tagged_search_news_is_unavailable(monkeypatch, articles):
    calls = install_yahoo(monkeypatch, TimeoutError("quote timed out"), articles)
    with pytest.raises(VendorUnavailableError, match="AAPL"):
        news.get_news_yfinance("AAPL", DAY, DAY)
    assert calls == {"quote": 1, "search": 1}


@pytest.mark.unit
def test_quote_failure_with_only_out_of_window_search_news_reports_sample_limit(monkeypatch):
    calls = install_yahoo(monkeypatch, TimeoutError("quote timed out"), [article("OLD", "2026-09-01")])
    result = news.get_news_yfinance("AAPL", DAY, DAY)
    assert "unavailable" in result and "not an absence" in result and "OLD" not in result
    assert calls == {"quote": 1, "search": 1}


@pytest.mark.unit
def test_both_yahoo_endpoints_failing_remain_unavailable(monkeypatch):
    calls = install_yahoo(monkeypatch, TimeoutError("quote timed out"), search_error=TimeoutError("search timed out"))
    with pytest.raises(VendorUnavailableError):
        news.get_news_yfinance("AAPL", DAY, DAY)
    assert calls == {"quote": 1, "search": 1}


@pytest.mark.unit
def test_malformed_expected_quote_response_falls_back_to_search(monkeypatch):
    # A missing feed is an expected Yahoo response, not evidence of zero articles.
    calls = install_yahoo(monkeypatch, None, [article("SEARCH")])
    result = news.get_news_yfinance("AAPL", DAY, DAY)
    assert "SEARCH" in result
    assert calls == {"quote": 1, "search": 1}


@pytest.mark.unit
def test_unexpected_search_programming_error_is_not_reported_as_empty_news(monkeypatch):
    install_yahoo(monkeypatch, TimeoutError("quote timed out"))

    def broken_search(*args):
        raise AssertionError("search code is broken")

    monkeypatch.setattr(news, "_search_news", broken_search)
    with pytest.raises(AssertionError, match="search code is broken"):
        news.get_news_yfinance("AAPL", DAY, DAY)


@pytest.mark.unit
def test_rate_limited_quote_has_bounded_retries_before_one_search(monkeypatch):
    calls = install_yahoo(monkeypatch, YFRateLimitError(), [article("SEARCH")])
    monkeypatch.setattr(common.time, "sleep", lambda seconds: None)
    result = news.get_news_yfinance("AAPL", DAY, DAY)
    assert "SEARCH" in result
    assert calls == {"quote": 4, "search": 1}
