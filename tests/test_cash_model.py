"""Operating cash and capital spending as rates of the case's own revenue (after run 9149f33b).

That run's analyst met the request for a cash bridge with amounts chosen to net to zero, the same in every
case. Rates applied by code to each case's revenue make the cases differ and leave no figure to plug.
"""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from tests.test_case_funding import SCHEDULE, SNAPSHOT
from tradingagents.agents.valuation_cases import (
    CaseCapital,
    bridge_revenue,
    filed_cash_rates,
    funding_check,
    model_flows,
    states_operations,
)

END = date(2027, 12, 31)


def _value(amount, label="x", assumption="unchanged_from_snapshot"):
    return {"value": str(amount), "fact_ids": [label], "assumption": assumption, "reason": "r"}


def _capital(**extra):
    return CaseCapital.model_validate({
        "valuation_date": "2027-12-31", "currency": "USD", "closing_shares": _value(120),
        "cash": _value(666096000), "obligations": {"borrowings": _value(461630000)}, **extra})


MODEL = {"operating_cash_margin": "0.30", "operating_cash_reason": "Below the 37% of the last nine months.",
         "capex_rate": "0.12", "capex_reason": "In line with the last nine months."}


def _fact(metric, value, start, end):
    return SimpleNamespace(metric=metric, value=Decimal(value), period_start=start, period_end=end,
                           basis="US-GAAP", unit="USD")


FACTS = SimpleNamespace(facts=[
    _fact("Revenue", 321192000, date(2026, 7, 1), SNAPSHOT), _fact("Revenue", 860281000, date(2026, 1, 1), SNAPSHOT),
    _fact("Operating Cash Flow", 318116000, date(2026, 1, 1), SNAPSHOT),
    _fact("Capital Expenditure", 105124000, date(2026, 1, 1), SNAPSHOT),
    _fact("Software Development Payments", 19279000, date(2026, 1, 1), SNAPSHOT)])
FORECAST = SimpleNamespace(value=Decimal(1930000000), period_start=date(2027, 1, 1), period_end=END)


def test_revenue_between_the_filing_and_the_period_end_uses_the_latest_quarter_then_the_forecast():
    revenue, how = bridge_revenue(FACTS, SNAPSHOT, FORECAST, "USD")
    # 92 days from 2026-10-01 to 2026-12-31 at the 321.192M the last 92-day quarter earned, then the 2027 forecast.
    assert revenue == Decimal(321192000) + Decimal(1930000000)
    assert "the latest reported quarter's rate to 2026-12-31, then the case's forecast" in how
    bare, how = bridge_revenue(SimpleNamespace(facts=[]), SNAPSHOT, FORECAST, "USD")
    assert abs(bare - Decimal(1930000000) * (92 + 365) / 365) < 1 and "the case's forecast rate throughout" in how
    inside = SimpleNamespace(value=Decimal(1200), period_start=date(2026, 1, 1), period_end=date(2026, 12, 31))
    part, _ = bridge_revenue(FACTS, SNAPSHOT, SimpleNamespace(**{**inside.__dict__}), "USD")
    assert abs(part - Decimal(1200) * 92 / 365) < 1


def test_rates_become_amounts_from_the_cases_own_revenue_so_cases_differ():
    base, down = (model_flows(_capital(cash_model=MODEL), Decimal(revenue)) for revenue in (2251192000, 2021192000))
    assert base == {"operations": Decimal(675357600), "capex": Decimal(270143040)}
    assert down["operations"] < base["operations"] and down["capex"] < base["capex"]
    assert model_flows(_capital(), Decimal(2251192000)) is None
    assert states_operations(_capital(cash_model=MODEL)) and not states_operations(_capital())


def test_rates_and_amounts_for_the_same_thing_are_refused_and_rates_have_bounds():
    for clash in ("operations", "capex"):
        with pytest.raises(ValidationError, match="not both"):
            _capital(cash_model=MODEL, cash=_value(666096001, assumption="estimated"),
                     cash_changes=[{"source": clash, "amount": "1", "reason": "r"}])
    for bad in ({"operating_cash_margin": "1.5"}, {"capex_rate": "-0.1"}, {"capex_reason": ""}):
        with pytest.raises(ValidationError):
            _capital(cash_model={**MODEL, **bad})
    # Other stated changes can sit beside the rates.
    kept = _capital(cash_model=MODEL, cash=_value(666096000 + 5, assumption="estimated"),
                    cash_changes=[{"source": "other", "amount": "5", "reason": "r"}])
    assert kept.cash_model.capex_rate == Decimal("0.12")
    assert "cash_model" not in _capital().model_dump(mode="json")


def test_the_filed_rates_stand_beside_the_analysts():
    filed = filed_cash_rates(FACTS, SNAPSHOT, "USD")
    assert round(filed["operating_cash_margin"], 4) == Decimal("0.3698")
    assert round(filed["capex_rate"], 4) == Decimal("0.1446")          # property and equipment plus software
    assert filed["period"] == "2026-01-01 to 2026-09-30"
    assert filed_cash_rates(SimpleNamespace(facts=[]), SNAPSHOT, "USD") is None


def test_the_funding_line_says_what_is_covered_and_what_is_only_assumed():
    terms = {"schedule": SCHEDULE, "notes": []}
    covered = funding_check(_capital(cash_model=MODEL), SNAPSHOT, Decimal(461630000), terms)
    assert covered["status"] == "assessed"
    assert covered["summary"].startswith("Scheduled payments covered: ")
    assert covered["summary"].endswith("Operating cash flow and capital spending are the analyst's assumptions, not "
                                       "filed figures or guidance.")
    assert "Funding assessed" not in covered["summary"]
    silent = funding_check(_capital(), SNAPSHOT, Decimal(461630000), terms)
    assert silent["status"] == "partial" and silent["summary"].endswith(
        "The case states no operating cash flow or capital spending.")


def test_a_priced_case_with_rates_moves_by_exactly_the_modelled_cash_and_says_where_it_came_from():
    from tests.test_case_valuation import revenue_case
    from tests.test_shared_valuation import state
    from tradingagents.agents.shared_valuation import _lacks_bridge, prepare_shared_valuation
    from tradingagents.agents.valuation_cases import STATEMENT

    def price(row):
        record = prepare_shared_valuation(state([row]))
        assert record["status"] == "available", record["reasons"]
        return record["rows"][0]

    plain = revenue_case()
    plain["request"]["capital"]["cash"] = {**plain["request"]["capital"]["cash"], "value": "100",
                                           "assumption": "unchanged_from_snapshot"}
    plain["request"]["capital"]["cash_changes"] = []
    rated = {**plain, "request": {**plain["request"], "capital": {**plain["request"]["capital"], "cash_model": MODEL}}}
    assert _lacks_bridge(plain) and not _lacks_bridge(rated)
    before, after = price(plain), price(rated)
    line = next(a for a in after["result"]["assumptions"] if a.startswith("cash model: the analyst's operating cash "
                                                                         "margin of 30.0% and capital spending rate of 12.0%"))
    statement = next(a for a in after["result"]["assumptions"] if a.startswith(STATEMENT + "cash:"))
    assert "(the analyst's rates, applied by code to the case's revenue)" in statement and "Reasons (unvalidated): " in line
    moved = (Decimal(after["result"]["target"]) - Decimal(before["result"]["target"])) * 110
    revenue = Decimal(rated["request"]["forecast"]["value"])
    assert moved > 0 and moved > Decimal("0.18") * revenue * Decimal("0.9")      # 30% less 12% of at least the forecast
    assert after["funding"]["summary"].endswith("the analyst's assumptions, not filed figures or guidance.")
    assert after["request"]["capital"]["cash_model"]["capex_rate"] == "0.12"


def test_amounts_that_only_balance_one_another_are_called_that():
    from tradingagents.agents.valuation_cases import cash_model_line
    plug = _capital(cash_changes=[{"source": "operations", "amount": "500000000", "reason": "r"},
                                  {"source": "capex", "amount": "-179547000", "reason": "r"},
                                  {"source": "finance_payments", "amount": "-320453000", "reason": "r"}])
    line = cash_model_line(plug, None, Decimal(2251192000), "how", filed_cash_rates(FACTS, SNAPSHOT, "USD"), SNAPSHOT)
    assert "the case states amounts, not rates. Operating cash of +500.0M USD is 22.2% of" in line
    assert "In the filed period 2026-01-01 to 2026-09-30 they were 37.0% and 14.5%" in line
    assert line.endswith("the amounts balance one another and are not an independent forecast.")
    real = _capital(cash=_value(666096000 + 300000000, assumption="estimated"),
                    cash_changes=[{"source": "operations", "amount": "700000000", "reason": "r"},
                                  {"source": "capex", "amount": "-400000000", "reason": "r"}])
    assert "balance one another" not in cash_model_line(real, None, Decimal(2251192000), "how", None, SNAPSHOT)
    assert cash_model_line(_capital(), None, Decimal(2251192000), "how", None, SNAPSHOT) is None
