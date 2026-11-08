"""News timestamps and degraded search provenance reach consumers."""
from datetime import UTC, datetime, timedelta, timezone

from langchain_core.messages import ToolMessage

from tests.test_news_error_fallback import DAY, article, install_yahoo
from tradingagents.agents.issuer_events import news_tool_coverage
from tradingagents.dataflows.vendors.yahoo import news


def test_formatted_articles_show_publish_date():
    text = news._format_articles([{'title': 'Issuer headline', 'publisher': 'Named publisher',
        'pub_date': datetime(2026, 10, 1, 7, 30, tzinfo=timezone(timedelta(hours=-4))),
        'summary': '', 'link': ''}])
    assert 'Named publisher' in text
    assert '2026-10-01T11:30:00+00:00' in text


def test_search_fallback_marks_coverage_degraded(monkeypatch):
    install_yahoo(monkeypatch, TimeoutError('quote timed out'), [article('MATCH')])
    text = news.get_news_yfinance('AAPL', DAY, DAY)
    assert 'Coverage: degraded: search_fallback, headlines_only' in text
    coverage = news_tool_coverage([ToolMessage(content=text, name='get_news', tool_call_id='news')])
    assert coverage['independent_news']['status'] == 'degraded'
    assert coverage['independent_news']['reason'] == 'search_fallback, headlines_only'


def test_quote_news_keeps_available_coverage_and_undated_is_explicit(monkeypatch):
    install_yahoo(monkeypatch, [article('QUOTE')])
    text = news.get_news_yfinance('AAPL', DAY, DAY)
    assert datetime.fromisoformat(DAY).replace(tzinfo=UTC).isoformat() in text
    coverage = news_tool_coverage([ToolMessage(content=text, name='get_news', tool_call_id='news')])
    assert coverage['independent_news']['status'] == 'available'
    undated = news._format_articles([{'title': 'No time', 'publisher': 'P', 'pub_date': None,
                                     'summary': '', 'link': ''}])
    assert 'publication time unavailable' in undated.lower()
