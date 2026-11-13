"""What an earnings case assumes: how much of its change from the close is earnings and how much is the multiple.

Found 2026-11-13: nearly every company rates Underweight because the analysts' cases apply a lower multiple than
the price pays, yet the report never said so in one place. Revenue cases already carry this split; earnings cases
did not.

Boundary: a printed line on the decision card only. Nothing is sent to any agent and no rating, weight or value
changes. A case that is not forecast EPS times its multiple, or with no positive filed EPS, gets no line.
"""
from decimal import Decimal

from tests.test_scenario_decision import _accept, _row, _state
from tradingagents.agents.scenario_decision import priced_cases, render, summarize

FACT = "f" * 64


def _earnings(case_id, eps, multiple, role="base"):
    row = _row(case_id, str(Decimal(eps) * Decimal(multiple)), role=role)
    row["result"] = {**row["result"], "method": "earnings_case", "multiple": multiple}
    row["request"] = {"method": "earnings_case", "eps_fact_id": FACT, "multiple": multiple,
                      "forecast": {"value": eps, "period_start": "2027-01-01", "period_end": "2027-12-31"}}
    row["comparison"]["price"]["close"] = "500"
    return row


def _replayed(filed="20.00"):
    return {"rows": [_earnings("base", "22.00", "20"), _earnings("down", "18.00", "16", role="downside")],
            "earnings_baselines": {FACT: {"value": filed, "period_start": "2026-01-01", "period_end": "2026-12-31"}}}


VIEW = [_accept("base", 0.5), _accept("down", 0.5)]


def test_the_split_is_exact_and_names_the_multiple_the_price_pays():
    summary = summarize(_state(VIEW), _replayed())
    parts = summary["cases"][0]["return_parts_earnings"]
    # close 500 on filed 20 is 25x; earnings to 22 at 25x is 550 (+50); 25x to 20x on 22 is -110; total -60 to 440
    assert (Decimal(parts["earnings_effect"]), Decimal(parts["multiple_effect"]), Decimal(parts["total"])) == (50, -110, -60)
    card = "\n".join(render(summary))
    assert "Today's price is 25.0x the diluted EPS of 20.00 filed for the year to 2026-12-31" in card
    assert "base — earnings 20.00 to 22.00 (+10.0%): +50.00; multiple 25.0x to 20.0x: -110.00; total -60.00 to 440.00" in card
    assert "The close is 22.7x this case's own forecast" in card


def test_no_line_without_a_positive_filed_figure_or_for_a_case_not_built_this_way():
    for replayed in (_replayed(filed="-1.00"), {**_replayed(), "earnings_baselines": {}}):
        assert "return_parts_earnings" not in summarize(_state(VIEW), replayed)["cases"][0]
    odd = _replayed()
    odd["rows"][0]["result"]["target"] = "470"          # not 22 x 20
    assert "return_parts_earnings" not in summarize(_state(VIEW), odd)["cases"][0]
    assert priced_cases(_replayed())[0]["filed_eps"] == "20.00"
