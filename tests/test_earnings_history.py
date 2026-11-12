"""A price-to-earnings reference from the company's own fiscal year ends.

Named as the biggest weakness on the loop's WMT and MSFT reports: case multiples of 30x to 44x with "no
verified peer or own-history P/E reference". The close at each fiscal year end over the diluted EPS filed
for that year needs no share count, so it can be stated where the revenue-based history cannot.
"""
from decimal import Decimal

from tradingagents.agents.valuation_reference import calculate_earnings_history
from tradingagents.dataflows.financial_evidence import EvidencePackage, FinancialFact, SourceRecord

CIK = "0000104169"
YEARS = (("2023-02-01", "2024-01-31", "1.91", "55"), ("2024-02-01", "2025-01-31", "2.41", "98"),
         ("2025-02-01", "2026-01-31", "2.73", "119"))


def _package(years=YEARS, extra=()):
    source = SourceRecord(source_id="sec", cik=CIK, url="https://www.sec.gov/test", filed_date="2026-03-20",
                          retrieved_at="2026-11-11T22:00:00Z", content_hash="a" * 64, locator="fixture", form="10-K")
    facts = [FinancialFact(fact_id=f"eps-{end}", metric="Diluted EPS", value=value, unit="USD/shares", cik=CIK,
                           period_start=start, period_end=end, as_of="2026-11-11", source_ids=("sec",), locator="f")
             for start, end, value, _close in years]
    return EvidencePackage(cik=CIK, as_of="2026-11-11", sources=(source,), facts=(*facts, *extra))


def _prices(years=YEARS):
    return [{"ticker": "WMT", "quarter_end": end, "session_date": end, "session_status": "completed", "close": close,
             "currency": "USD", "source_id": "yahoo-history", "content_hash": "b" * 64,
             "source_url": "https://query2.finance.yahoo.com/chart/WMT",
             "adjustment_basis": "historical_split_adjusted", "split_basis_date": "2026-11-11"}
            for _start, end, _value, close in years]


def _splits(*actions):
    return {"ticker": "WMT", "coverage_complete": True, "coverage_start": "2023-01-01", "coverage_end": "2026-11-11",
            "split_basis_date": "2026-11-11", "source_id": "yahoo-history", "content_hash": "b" * 64,
            "splits": [{"session_date": day, "ratio": ratio, "source_id": "yahoo-history"} for day, ratio in actions]}


def _run(package=None, prices=None, splits=None, close="125.67"):
    return calculate_earnings_history(package or _package(), prices if prices is not None else _prices(),
                                      splits or _splits(), ticker="WMT", current_close=close)


def test_each_fiscal_year_end_close_is_set_over_the_diluted_eps_filed_for_that_year():
    result = _run()
    assert result["status"] == "available"
    assert [(row["year_end"], Decimal(row["multiple"]).quantize(Decimal("0.1"))) for row in result["rows"]] == [
        ("2024-01-31", Decimal("28.8")), ("2025-01-31", Decimal("40.7")), ("2026-01-31", Decimal("43.6"))]
    assert Decimal(result["today"]["multiple"]).quantize(Decimal("0.01")) == Decimal("46.03")
    assert result["today"]["eps_period_end"] == "2026-01-31"
    assert "28.8×" in result["summary"] and "43.6×" in result["summary"] and "46.0×" in result["summary"]


def test_a_split_inside_the_three_years_of_the_latest_annual_report_is_already_restated():
    # Split on 2024-02-26: the fiscal 2024 figure comes restated in the later annual reports, so it stays.
    assert len(_run(splits=_splits(("2024-02-26", "3")))["rows"]) == 3


def test_years_that_cannot_be_trusted_across_a_split_or_have_two_values_or_a_loss_are_left_out():
    older = (("2021-02-01", "2022-01-31", "4.87", "46"), *YEARS)          # before the split, outside the three years
    result = _run(_package(older), _prices(older), _splits(("2024-02-26", "3")))
    assert [row["year_end"] for row in result["rows"]] == ["2024-01-31", "2025-01-31", "2026-01-31"]
    assert any("2022-01-31" in reason and "split" in reason for reason in result["excluded"])
    twice = FinancialFact(fact_id="eps-b", metric="Diluted EPS", value="5.74", unit="USD/shares", cik=CIK,
                          period_start="2023-02-01", period_end="2024-01-31", as_of="2026-11-11",
                          source_ids=("sec",), locator="f")
    result = _run(_package(extra=(twice,)))
    assert [row["year_end"] for row in result["rows"]] == ["2025-01-31", "2026-01-31"]
    loss = (YEARS[0], ("2024-02-01", "2025-01-31", "-0.40", "98"), YEARS[2])
    assert [row["year_end"] for row in _run(_package(loss), _prices(loss))["rows"]] == ["2024-01-31", "2026-01-31"]


def test_a_split_after_the_latest_annual_report_or_too_few_years_states_nothing():
    late = _run(splits=_splits(("2026-06-01", "2")))
    assert late["status"] == "unavailable" and "split" in late["reason"]
    one = _run(_package(YEARS[2:]), _prices(YEARS[2:]))
    assert one["status"] == "unavailable" and "Fewer than two" in one["reason"]
    assert _run(prices=[])["status"] == "unavailable"
