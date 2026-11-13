"""Related holdings are measured together (map 2b-4, user decision 2026-11-12).

Boundary: "related" is the same sector as the stock analysed. The figures are printed facts in the Position and
sizing block, shown to the manager before it decides; code never changes a rating or a size with them. A file
with no other holding in the sector, or a run with no portfolio file, reads exactly as before. A holding whose
price or sector cannot be found is left out and named, and the figure is called partial.
"""
from decimal import Decimal

from tradingagents.portfolio import PortfolioContext, related_holdings, render_sizing, sizing

WEIGHTS = {"Buy": 1.5, "Overweight": 1.25, "Hold": 1.0, "Underweight": 0.5, "Sell": 0}
FILE = {"currency": "USD", "portfolio_value": 100000, "default_standard_weight": 0.05, "loss_budget": 0.01,
        "rating_weights": WEIGHTS,
        "positions": [{"ticker": "MSFT", "quantity": 10}, {"ticker": "NVDA", "quantity": 20},
                      {"ticker": "AAPL", "quantity": 30}, {"ticker": "XOM", "quantity": 50}]}
QUOTE = {"close": "500", "currency": "USD", "session_date": "2026-11-11"}
CLOSES = {"NVDA": "200", "AAPL": "300", "XOM": "100"}
SECTORS = {"MSFT": "Technology", "NVDA": "Technology", "AAPL": "technology ", "XOM": "Energy"}


def _quote(ticker, as_of):
    return ({"status": "available", "close": CLOSES[ticker], "currency": "USD", "session_date": as_of}
            if ticker in CLOSES else {"status": "unavailable"})


def _inputs(**fields):
    book = PortfolioContext.model_validate({**FILE, **fields})
    return {**book.inputs(), **book.grouping()}


def _group(inputs=None, sectors=SECTORS, quote=_quote):
    return related_holdings(inputs or _inputs(), "MSFT", "2026-11-11", quote=quote, sector=sectors.get)


def test_the_other_holdings_in_the_sector_are_added_up_and_the_rest_ignored():
    group = _group()
    assert group["status"] == "available" and group["sector"] == "Technology" and group["count"] == 2
    assert Decimal(group["others_weight"]) == Decimal("0.13") and group["left_out"] == []      # 4% NVDA + 9% AAPL


def test_what_cannot_be_found_is_left_out_and_named():
    group = _group(sectors={**SECTORS, "AAPL": None}, quote=lambda t, d: {"status": "unavailable"})
    assert group["left_out"] == ["NVDA", "AAPL"] and group["count"] == 0
    other_currency = _group(quote=lambda t, d: {**_quote(t, d), "currency": "EUR"})
    assert other_currency["left_out"] == ["NVDA", "AAPL"]
    assert _group(sectors={**SECTORS, "MSFT": None})["status"] == "unavailable"


def test_nothing_is_built_without_sizing_inputs_or_other_holdings():
    assert related_holdings({"positions": FILE["positions"]}, "MSFT", "2026-11-11", quote=_quote, sector=SECTORS.get) is None
    alone = _inputs(positions=[{"ticker": "MSFT", "quantity": 10}])
    assert related_holdings(alone, "MSFT", "2026-11-11", quote=_quote, sector=SECTORS.get) is None


def test_the_file_sector_wins_and_the_limit_rides_along_only_when_set():
    assert PortfolioContext.model_validate(FILE).grouping() == {}
    own = _inputs(limits={"max_sector_weight": 0.15},
                  positions=[*FILE["positions"][:3], {"ticker": "XOM", "quantity": 50, "sector": "Technology"}])
    group = _group(own)
    assert group["count"] == 3 and Decimal(group["others_weight"]) == Decimal("0.18") and group["limit"] == 0.15


def test_the_block_states_the_group_now_after_the_action_and_against_the_limit():
    related = _group(_inputs(limits={"max_sector_weight": 0.15}))
    before = "\n".join(render_sizing(sizing(_inputs(), "MSFT", QUOTE, related=related)))
    assert "Related holdings (same sector, Technology)" in before and "18.0% of the portfolio now" in before
    after = sizing(_inputs(), "MSFT", QUOTE, rating="Underweight", related=related)
    assert Decimal(after["group"]["after"]) == Decimal("0.155") and after["group"]["over_limit"] is True
    text = "\n".join(render_sizing(after, final=True))
    assert "15.5% after the Underweight action" in text and "OVER your sector limit of 15.0%" in text
    assert "individual" not in text and "NVDA" not in text          # other holdings' own sizes are not printed


def test_the_group_is_tested_against_the_lowest_accepted_case():
    from tradingagents.portfolio import group_downside

    result = sizing(_inputs(), "MSFT", QUOTE, rating="Hold", related=_group())
    test = group_downside(result, {"status": "available", "fall": "0.30", "role": "down", "name": "slower cloud"})
    assert Decimal(test["loss"]) == Decimal("0.054") and test["inside"] is False               # 18% x 30% against 1%
    result["group"]["downside"] = test
    assert "would lose 5.40% of the portfolio, OUTSIDE the 1.00% budget" in "\n".join(render_sizing(result, final=True))


def test_a_partial_figure_says_so_and_no_group_means_no_line():
    partial = _group(quote=lambda t, d: _quote(t, d) if t == "NVDA" else {"status": "unavailable"})
    text = "\n".join(render_sizing(sizing(_inputs(), "MSFT", QUOTE, related=partial)))
    assert "Left out (price or sector not found): AAPL; the figure is partial" in text
    assert "Related holdings" not in "\n".join(render_sizing(sizing(_inputs(), "MSFT", QUOTE)))
