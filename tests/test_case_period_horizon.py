"""Valuation cases are priced on a period that reaches the decision horizon.

Seen in the loop's last batches: Walmart's cases ended 81 days out (its fiscal year end) in every run and
DigitalOcean's once ended 50 days out, against a six-month horizon, so a six-month rating rested on a value
the company would reach in weeks. The analyst is now given the earliest acceptable period end, and code says
so beside any case that ends before it. Nothing is refused: a short case still prices.
"""
from tradingagents.agents.analysts.fundamentals_analyst import case_period_rule
from tradingagents.agents.shared_valuation import horizon_note


def test_the_analyst_is_given_the_earliest_period_end_from_the_run_date_and_horizon():
    text = case_period_rule({"trade_date": "2026-11-12", "run_settings": {"decision_horizon_months": 6}})
    assert "2027-05-12" in text and "following fiscal year" in text
    assert "2027-02-28" in case_period_rule({"trade_date": "2026-08-31", "run_settings": {"decision_horizon_months": 6}})
    assert "2027-05-12" in case_period_rule({"trade_date": "2026-11-12"})          # default horizon is six months
    assert case_period_rule({"trade_date": "not a date"}) == ""


def test_a_case_ending_before_the_horizon_is_said_so_and_one_reaching_it_is_not():
    state = {"trade_date": "2026-11-12", "run_settings": {"decision_horizon_months": 6}}
    note = horizon_note("Base", "2027-01-31", state)
    assert "Base" in note and "2027-01-31" in note and "80 days" in note and "2027-05-12" in note
    assert horizon_note("Base", "2027-06-30", state) is None and horizon_note("Base", "2027-05-12", state) is None
    assert horizon_note("Base", "bad", state) is None
