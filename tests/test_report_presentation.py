"""Readable display must preserve exact payloads and advisory uncertainty."""

from copy import deepcopy

import pytest

from tests.test_decision_context import state
from tests.test_shared_valuation import state as scenario_state
from tests.test_valuation import ev_request
from tradingagents.agents.decision_context import prepare_decision_context, render_decision_context
from tradingagents.agents.shared_valuation import prepare_shared_valuation, render_shared_valuation
from tradingagents.agents.valuation_comparison import display_number
from tradingagents.reporting import _header, evidence_appendix


@pytest.mark.parametrize(
    "value,expected",
    [
        ("12.3456789", "12.35"),
        ("0", "0.00"),
        ("0.000000001", "1.00E-9"),
        ("-0.0001", "-1.00E-4"),
        ("100000000000000000000000000000", "1.00E+29"),
        (None, "unavailable"),
    ],
)
def test_display_precision_never_rounds_nonzero_to_zero(value, expected):
    assert display_number(value) == expected


def test_shared_render_rounds_only_display_and_keeps_traceable_inputs():
    from tests.test_case_valuation import bridge, revenue_case

    row = revenue_case()
    request = row["request"]
    request["multiple"] = "3.123456789123456789"
    for label, amount in (("closing_shares", "100"), ("cash", "100")):
        request["capital"][label]["value"] = amount
    request["capital"]["obligations"]["borrowings"]["value"] = "200"
    bridge(request)
    record = prepare_shared_valuation(scenario_state([row]))
    original = deepcopy(record)
    text = render_shared_valuation(record)
    assert "36.48 USD/shares" in text and "1200.00 × 3.12" in text
    assert record["rows"][0]["request"]["multiple"] == "3.123456789123456789"
    assert "references shares" in text and "evidence.json" in text
    assert record == original


def test_condition_summary_is_next_to_rating_and_keeps_roles_unknown_override():
    card = prepare_decision_context(state())
    card["conditions"] = [
        {
            "metric": "Revenue",
            "thesis_role": "supports_thesis",
            "status": "breached",
            "disposition": "overridden",
            "reason": "Demand assumption; source " + "a" * 64,
        },
        {
            "metric": "Margin",
            "thesis_role": "reconsideration_trigger",
            "status": "unknown",
            "disposition": "kept",
            "reason": "No comparable observation.",
        },
    ]
    original = deepcopy(card)
    rendered = render_decision_context(card)
    assert rendered.index("Advisory conditions at a glance") < rendered.index("**Basis**")
    assert (
        "overridden" in rendered and "unknown" in rendered and "Supports the current rating" in rendered
    )
    assert "a" * 64 not in rendered and "evidence.json" in rendered
    assert card == original
    header = _header(
        "DOCN",
        {
            "final_trade_decision": "Rating: Underweight",
            "final_rating": "Underweight",
            "decision_context": card,
        },
        None,
    )
    assert header.index("Advisory conditions at a glance") < header.index("Generated:")


def test_calculation_appendix_rounds_display_without_changing_payload():
    value = {
        "financial_calculations": [
            {
                "method": "margin",
                "result": "33.3333333333333333333333",
                "unit": "percent",
                "status": "pass",
                "input_fact_ids": [],
                "message": "Derived margin.",
            }
        ]
    }
    original = deepcopy(value)
    assert "33.33 percent" in evidence_appendix(value)
    assert value == original


def test_final_target_rounds_price_and_capital_not_rationale():
    from tests.test_valuation import evidence
    from tradingagents.agents.schemas import render_target_result
    from tradingagents.agents.valuation import validate_target

    request = ev_request()
    request["scenarios"][0]["multiple"] = "3.123456789123456789"
    request["scenarios"][0]["multiple_rationale"] = "Preserve analyst wording 3.123456789."
    result = validate_target(request, evidence())
    before = result.model_dump(mode="json")
    text = render_target_result(result)
    assert "36.48 USD/shares" in text
    assert "| 3.12 |" in text
    assert "Preserve analyst wording 3.123456789." in text
    assert result.model_dump(mode="json") == before


def test_unmet_reconsideration_is_not_a_support_breach():
    from tradingagents.agents.decision_context import render_condition_summary

    text = render_condition_summary(
        {
            "conditions": [
                {
                    "metric": "Revenue",
                    "thesis_role": "supports_thesis",
                    "status": "breached",
                    "disposition": "overridden",
                    "reason": "Research assumption retained.",
                },
                {
                    "metric": "Margin",
                    "thesis_role": "reconsideration_trigger",
                    "status": "breached",
                    "disposition": "kept",
                    "reason": "Trigger threshold not reached.",
                },
            ]
        }
    )
    assert "Support condition breached" in text
    assert "Reconsideration trigger not met" in text
    assert "overridden" in text and "kept" in text
