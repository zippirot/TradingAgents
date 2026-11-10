"""Required return, value today and the holdings-free sizing rule (decision-quality plan, Build 3)."""
from decimal import Decimal

import pytest

from tests.test_scenario_decision import _accept, _reject, _row, _state
from tradingagents.agents.required_return import (
    fetch_required_return,
    premium_from_config,
    render_required_return,
    required_return_record,
    value_today,
)
from tradingagents.agents.scenario_decision import render, summarize

RETURN = {"schema_version": 1, "status": "available", "series": "DGS10", "source": "FRED",
          "observation_date": "2026-11-06", "as_of": "2026-11-10", "risk_free_rate": "0.0486",
          "premium": "0.05", "rate": "0.0986"}


def _three():
    """Run d58117ef's three cases against its 78.30 close."""
    rows = [_row("base", "77.22"), _row("down", "42.93", role="downside"), _row("up", "103.25", role="upside")]
    for row in rows:
        row["comparison"]["price"]["close"] = "78.30"
    return {"rows": rows}


def _run(view, required=RETURN, **extra):
    state = {**_state(view), "trade_date": "2026-11-10", **extra}
    if required is not None:
        state["required_return"] = required
    return summarize(state, _three())


def test_a_retrieved_yield_plus_the_premium_is_the_required_return():
    record = required_return_record({"date": "2026-11-06", "value": "4.86"}, Decimal("0.05"), "2026-11-10")
    assert record == RETURN
    text = render_required_return(record)
    assert "Required return 9.86% a year" in text and "4.86% (FRED DGS10, 2026-11-06)" in text
    assert "premium of 5.00 points" in text and "not a forecast" in text


@pytest.mark.parametrize("point", [None, {}, {"date": "2026-11-06", "value": "."}, {"date": "2026-11-06", "value": "-1"},
                                   {"date": "2026-11-06", "value": "40"}, {"date": "2026-11-11", "value": "4.86"},
                                   {"date": "not a date", "value": "4.86"}])
def test_an_unusable_or_later_yield_is_never_used(point):
    record = required_return_record(point, Decimal("0.05"), "2026-11-10")
    assert record["status"] == "unavailable" and "rate" not in record
    assert "No value today or sizing rule is stated" in render_required_return(record)


def test_the_premium_setting_is_bounded_and_a_missing_source_assumes_nothing(monkeypatch):
    assert premium_from_config({}) == Decimal("0.05") and premium_from_config({"required_return_premium": "0.07"}) == Decimal("0.07")
    for bad in (-0.01, 0.31, "x", True, None):
        assert premium_from_config({"required_return_premium": bad}) is None
    assert fetch_required_return("2026-11-10", {"required_return_premium": 2})["status"] == "unavailable"
    no_source = fetch_required_return("2026-11-10", {"data_vendors": {"macro_data": ""}})
    assert no_source["status"] == "unavailable" and "no other vendor was used" in no_source["reason"]
    from tradingagents.dataflows.vendors import fred

    monkeypatch.setattr(fred, "latest_observation", lambda series, as_of: (_ for _ in ()).throw(OSError("down")))
    failed = fetch_required_return("2026-11-10", {"data_vendors": {"macro_data": "fred"}})
    assert failed["status"] == "unavailable" and "OSError" in failed["reason"]
    monkeypatch.setattr(fred, "latest_observation", lambda series, as_of: {"date": "2026-11-06", "value": "4.86"})
    assert fetch_required_return("2026-11-10", {"data_vendors": {"macro_data": "fred"}}) == RETURN


def test_the_yield_is_read_at_the_analysis_date_vintage(monkeypatch):
    from tradingagents.dataflows.vendors import fred

    seen = {}

    def request(path, params):
        seen.update(path=path, **params)
        return {"observations": [{"date": "2026-11-05", "value": "4.90"}, {"date": "2026-11-06", "value": "4.86"},
                                 {"date": "2026-11-09", "value": "."}]}

    monkeypatch.setattr(fred, "_request", request)
    monkeypatch.setattr(fred, "_fred_today", lambda: "2026-12-01")
    assert fred.latest_observation("DGS10", "2026-11-10") == {"date": "2026-11-06", "value": "4.86"}
    assert seen["observation_end"] == seen["realtime_start"] == seen["realtime_end"] == "2026-11-10"
    monkeypatch.setattr(fred, "_request", lambda path, params: {"observations": [{"date": "2026-11-09", "value": "."}]})
    assert fred.latest_observation("DGS10", "2026-11-10") is None


def test_value_today_brings_a_period_end_value_back_at_the_yearly_rate():
    assert value_today("110", "2026-01-01", "2027-01-01", "0.10").quantize(Decimal("0.0001")) == Decimal("100.0000")
    assert value_today("77.22", "2026-11-10", "2026-11-10", "0.0986") == Decimal("77.22")
    for bad in (("77.22", "2026-11-10", "2026-11-09", "0.1"), ("0", "2026-11-10", "2027-12-31", "0.1"),
                ("77.22", "x", "2027-12-31", "0.1"), ("77.22", "2026-11-10", "2027-12-31", "-0.1"),
                ("77.22", "2026-11-10", "2027-12-31", None)):
        assert value_today(*bad) is None


def test_the_saved_run_gets_values_today_and_a_sizing_rule_from_its_downside_case():
    summary = _run([_accept("base", 0.55), _accept("down", 0.30), _accept("up", 0.15)])
    today = {case["case_id"]: Decimal(case["value_today"]).quantize(Decimal("0.01")) for case in summary["cases"]}
    # 416 days at 9.86% a year: each value is divided by 1.0986 ** (416 / 365).
    assert today == {"base": Decimal("69.37"), "down": Decimal("38.57"), "up": Decimal("92.76")}
    rule = summary["sizing_rule"]
    assert (rule["status"], rule["case_id"], rule["role"]) == ("available", "down", "downside")
    assert Decimal(rule["fall"]).quantize(Decimal("0.001")) == Decimal("0.507")
    assert Decimal(rule["weight_per_point_of_loss"]).quantize(Decimal("0.01")) == Decimal("1.97")
    text = "\n".join(render(summary))
    assert "42.93 USD/shares at 2027-12-31, 38.57 USD/shares today" in text
    assert "Required return 9.86% a year" in text
    assert "50.7% below the 2026-11-09 close" in text and "at most 2.0% of the portfolio" in text
    assert "not an allocation" in text
    # The period-end comparison and rating check are unchanged by this build.
    assert Decimal(summary["weighted_value"]).quantize(Decimal("0.01")) == Decimal("70.84") and summary["direction"] == "near"


def test_a_rejected_downside_does_not_set_the_rule_and_a_case_above_the_close_sets_no_limit():
    summary = _run([_accept("base", 0.5), _reject("down"), _accept("up", 0.5)])
    assert summary["sizing_rule"]["case_id"] == "base" and summary["sizing_rule"]["status"] == "available"
    only_up = _run([_reject("base"), _reject("down"), _accept("up", 1)])
    assert only_up["sizing_rule"]["status"] == "not_limiting" and "weight_per_point_of_loss" not in only_up["sizing_rule"]
    text = "\n".join(render(only_up))
    assert "set no loss-based limit on the position" in text and "at most" not in text


def test_without_a_required_return_nothing_is_brought_back_and_no_rule_is_printed():
    accepted = [_accept("base", 0.55), _accept("down", 0.30), _accept("up", 0.15)]
    for required in (None, {"status": "unavailable", "reason": "The 10-year Treasury yield could not be retrieved (OSError)"},
                     {"status": "available", "rate": "nonsense"}):
        summary = _run(accepted, required=required)
        assert summary["sizing_rule"] is None and all("value_today" not in case for case in summary["cases"])
        text = "\n".join(render(summary))
        assert "Sizing from the downside" not in text and "USD/shares today" not in text and "at most" not in text
    assert "Required return unavailable" in "\n".join(render(_run(accepted, required={"status": "unavailable", "reason": "x"})))
    # A run saved before this build has no record at all: its card is unchanged.
    assert "Required return" not in "\n".join(render(_run(accepted, required=None)))


def test_all_rejected_or_no_comparable_close_states_no_rule():
    assert _run([_reject("base"), _reject("down"), _reject("up")])["sizing_rule"] is None
    state = {**_state([_accept("base", 0.55), _accept("down", 0.30), _accept("up", 0.15)]),
             "trade_date": "2026-11-10", "required_return": RETURN}
    rows = _three()
    for row in rows["rows"]:
        row["comparison"] = {"status": "unavailable"}
    summary = summarize(state, rows)
    assert summary["close"] is None and summary["sizing_rule"] is None


def test_the_required_return_is_kept_in_the_run_log_and_the_evidence_record(tmp_path):
    """A re-export of a saved run must be able to state the same value today without a new fetch."""
    import json

    from tests.test_cli_display import _bare_graph, _state as log_state
    from tradingagents.reporting import evidence_snapshot

    state = {**log_state("NVDA"), "required_return": RETURN}
    _bare_graph(tmp_path)._log_state("2026-09-01", state)
    logged = json.loads(next(tmp_path.rglob("full_states_log*.json")).read_text(encoding="utf-8"))
    assert logged["required_return"] == RETURN
    assert evidence_snapshot(state)["required_return"] == RETURN
    # A run saved before this build has no record, and its stored evidence record is not altered.
    assert "required_return" not in evidence_snapshot(log_state("NVDA"))


def test_the_acquisition_step_records_the_required_return_once_beside_the_price(monkeypatch):
    from tests.test_evidence_gate import complete_evidence
    from tests.test_preanalyst_acquisition import acquire, initial
    from tradingagents.dataflows.vendors import fred, sec_documents, sec_edgar
    from tradingagents.dataflows.vendors.yahoo import price_observation

    facts, docs = complete_evidence()
    asked = []
    monkeypatch.setattr(sec_edgar, "cik_for", lambda ticker: facts.cik)
    monkeypatch.setattr(sec_edgar, "get_financial_evidence", lambda *a: facts)
    monkeypatch.setattr(sec_documents, "get_filing_evidence", lambda *a: docs)
    monkeypatch.setattr(price_observation, "get_price_observation",
                        lambda *a: {"status": "unavailable", "reason": "fixture price"})
    monkeypatch.setattr(fred, "latest_observation",
                        lambda series, as_of: asked.append((series, as_of)) or {"date": "2026-10-16", "value": "4.50"})
    prepared = acquire(initial())
    assert asked == [("DGS10", "2026-10-19")]
    record = prepared["required_return"]
    assert (record["status"], record["rate"], record["observation_date"]) == ("available", "0.095", "2026-10-16")
    # A source failure leaves the run going and the return unstated.
    monkeypatch.setattr(fred, "latest_observation", lambda series, as_of: (_ for _ in ()).throw(RuntimeError("x")))
    assert acquire(initial())["required_return"]["status"] == "unavailable"


def test_values_today_are_never_printed_without_the_assumption_behind_them():
    """Audit finding: the all-rejected and no-close paths printed values today and then returned early."""
    rejected = "\n".join(render(_run([_reject("base"), _reject("down"), _reject("up")])))
    assert "38.57 USD/shares today" in rejected and "Required return 9.86% a year" in rejected
    assert "Sizing from the downside" not in rejected
    state = {**_state([_accept("base", 0.55), _accept("down", 0.30), _accept("up", 0.15)]),
             "trade_date": "2026-11-10", "required_return": RETURN}
    rows = _three()
    for row in rows["rows"]:
        row["comparison"] = {"status": "unavailable"}
    no_close = "\n".join(render(summarize(state, rows)))
    assert "USD/shares today" in no_close and "Required return 9.86% a year" in no_close
    assert "Sizing from the downside" not in no_close
    unavailable = {"status": "unavailable", "reason": "x"}
    assert "Required return unavailable: x" in "\n".join(render(_run([_reject("base"), _reject("down"), _reject("up")],
                                                                    required=unavailable)))


@pytest.mark.parametrize("damage", [{"risk_free_rate": None}, {"premium": "x"}, {"observation_date": ""},
                                    {"series": None}, {"source": 7}, {"rate": "0.2"}, {"rate": "1.5"}])
def test_a_partial_saved_record_is_unusable_for_arithmetic_and_display_alike(damage):
    """Audit finding: a record with a usable rate but missing provenance was calculated on yet reported unusable."""
    summary = _run([_accept("base", 0.55), _accept("down", 0.30), _accept("up", 0.15)], required={**RETURN, **damage})
    assert summary["sizing_rule"] is None and all("value_today" not in case for case in summary["cases"])
    text = "\n".join(render(summary))
    assert "Required return unavailable: the saved record is not usable" in text
    assert "USD/shares today" not in text and "Sizing from the downside" not in text and "at most" not in text
