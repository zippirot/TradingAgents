"""The comparison with the last decision reads earnings cases.

Found 2026-11-12 on follow-up MSFT runs: every earnings case, in the earlier record and in the current run,
was printed as "unusable (Unsupported retained case)". The manager repeated it ("saved case records are
flagged unusable ... no individual case is adopted") and evaluators marked the report down for cases that
were "accepted", "unusable" and "not adopted" at once. The comparison supported revenue cases only.
"""
from tradingagents.agents.assumption_history import _case_changes, _fields


def _case(name, role, eps, multiple):
    return {"name": name, "scenario_role": role, "request": {
        "method": "earnings_case", "eps_fact_id": "f" * 64, "multiple": multiple,
        "multiple_assumption_date": "2026-11-12", "multiple_rationale": "r",
        "forecast": {"value": eps, "unit": "USD/shares", "period_start": "2026-07-01", "period_end": "2027-06-30",
                     "basis": "US-GAAP", "kind": "analyst_forecast", "rationale": "r"}}}


def test_earnings_cases_are_usable_and_an_unchanged_set_shows_no_change():
    unusable = []
    record = {"requests": [_case("Base", "base", "20.50", "27"), _case("Downside", "downside", "18.80", "23")]}
    old, new = _fields(record, unusable), _fields(record, unusable)
    assert unusable == [] and len(old) == 2 and old[0]["fields"]["multiple"].startswith("27")
    assert _case_changes(old, new) == []


def test_a_changed_forecast_or_multiple_is_reported_field_by_field():
    old = _fields({"requests": [_case("Base", "base", "20.50", "27")]}, [])
    new = _fields({"requests": [_case("Base", "base", "21.00", "28")]}, [])
    changes = {row["field"]: (row["previous"], row["current"]) for row in _case_changes(old, new)}
    assert set(changes) == {"forecast", "multiple"}
    assert "20.5" in changes["forecast"][0] and "21" in changes["forecast"][1]
