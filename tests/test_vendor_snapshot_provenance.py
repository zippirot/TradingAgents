"""Yahoo profile values must not masquerade as completed-close calculations."""
from datetime import UTC, datetime
from unittest import mock

import pytest

from tradingagents.dataflows import date_window
from tradingagents.dataflows.vendors.yahoo import fundamentals

NOW = datetime(2026, 11, 5, 16, 5, tzinfo=UTC)
TODAY = "2026-11-05"


def render(info, now=NOW):
    with mock.patch.object(date_window, "get_current_date", return_value=TODAY), \
         mock.patch.object(fundamentals, "_now", return_value=now, create=True), \
         mock.patch.object(fundamentals, "yf_retry", lambda fn: info):
        return fundamentals.get_fundamentals("DOCN", TODAY)


@pytest.mark.unit
def test_intraday_vendor_multiples_are_noncanonical_and_quote_is_provisional():
    out = render({
        "longName": "DigitalOcean", "currency": "USD", "financialCurrency": "USD",
        "exchangeTimezoneName": "America/New_York", "marketState": "REGULAR",
        "regularMarketTime": 1793894400, "regularMarketPrice": 74.24,
        "marketCap": 9910000000, "sharesOutstanding": 120000000,
        "trailingPE": 42.1, "forwardPE": 39.2,
        "trailingEps": 1.8, "forwardEps": 2.1,
    })
    assert "Retrieved at: 2026-11-05T16:05:00+00:00" in out
    assert "Source: Yahoo Finance Ticker.info" in out
    assert "Exchange timezone: America/New_York" in out
    assert "Quote status: provisional intraday" in out
    assert "Observed regular-market quote" in out
    assert "Market Cap: 9910000000 USD" in out
    assert "PE Ratio (TTM): 42.1" in out
    assert "Forward PE: 39.2" in out
    assert "Market Cap, PE Ratio (TTM), Forward PE: Yahoo vendor snapshot; noncanonical" in out
    assert "not a completed-close calculation" in out
    assert "retrieval time does not date every constituent" in out
    assert "forward earnings" in out.lower()


@pytest.mark.unit
def test_vendor_closed_state_qualifies_quote_without_canonizing_ratios():
    out = render({
        "currency": "USD", "exchangeTimezoneName": "America/New_York",
        "marketState": "CLOSED", "regularMarketTime": 1793912400,
        "regularMarketPrice": 80.0, "marketCap": 1000, "trailingPE": 20,
    }, now=datetime(2026, 11, 5, 22, 5, tzinfo=UTC))
    assert "Quote status: vendor reports closed session" in out
    assert "Market Cap: 1000 USD" in out
    assert "Market Cap, PE Ratio (TTM), Forward PE: Yahoo vendor snapshot; noncanonical" in out
    assert "not a completed-close calculation" in out


@pytest.mark.unit
def test_missing_or_stale_quote_time_does_not_invent_intraday_timestamp():
    base = {"currency": "USD", "exchangeTimezoneName": "America/New_York",
            "marketState": "REGULAR", "regularMarketPrice": 74.24, "marketCap": 1000}
    missing = render(base)
    assert "Quote status: unknown (quote timestamp unavailable)" in missing
    assert "Observed regular-market quote" not in missing
    stale = render({**base, "regularMarketTime": 1793808000})
    assert "Quote status: stale or earlier session" in stale
    assert "Observed regular-market quote" not in stale
    assert "2026-11-05T16:05:00+00:00" in stale


@pytest.mark.unit
def test_vendor_share_and_earnings_bases_remain_unverified_even_if_values_present():
    out = render({
        "currency": "USD", "financialCurrency": "TWD", "marketCap": 1000,
        "sharesOutstanding": 100, "trailingEps": 5, "forwardEps": 6,
        "trailingPE": 20, "forwardPE": 18,
    })
    assert "Share-count basis: vendor-defined; date, class, dilution and compatibility unverified" in out
    assert "Trailing earnings basis: vendor-defined; period, currency and share basis unverified" in out
    assert "Forward earnings basis: vendor estimate; forecast period, currency and share basis unverified" in out
    assert "Reported income currency: TWD" in out
    assert "Quote currency: USD" in out
    assert "Quote status: unknown (exchange timezone unavailable)" in out
