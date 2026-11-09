"""Behavioral contracts for the run-scoped operational assessment."""

import pytest

from tradingagents.operational_audit import (
    assess_audit,
    merge_observations,
    observation,
    render_assessment,
    render_audit,
    settings_digest,
)

STAGES = ["Source Acquisition", "Market Analyst", "Evidence Check", "Run Metrics"]


def run_state():
    return {"run_id": "run-1", "company_of_interest": "DOCN", "trade_date": "2026-11-06",
            "run_settings": {"analysts": ["market"], "data_vendors": {"core_stock_apis": "yfinance"}}}


def observed(*events):
    state = run_state()
    rows = [observation(state, "Source Acquisition", expected_stages=STAGES)]
    rows += [observation(state, stage, route="full" if stage == "Evidence Check" else None)
             for stage in STAGES[1:]]
    rows += list(events)
    state["operational_observations"] = merge_observations({}, {r["event_id"]: r for r in rows})
    return state


@pytest.mark.parametrize("code,stage,expected", [
    (None, None, (5, "Strong")),
    ("recovered_retry", "News Analyst", (5, "Strong")),
    ("fallback_recovered", "get_news", (4, "Good")),
    ("input_unavailable", "News Analyst", (3, "Degraded")),
    ("stage_unusable", "Market Analyst", (2, "Low confidence")),
    ("mixed_run_input", "Market Analyst", (1, "Compromised")),
])
def test_five_grades_follow_explicit_operational_reasons(code, stage, expected):
    event = [] if code is None else [observation(run_state(), stage, status="unusable", code=code,
                                                  severity=1 if code == "recovered_retry" else 5,
                                                  scope="News analysis")]
    assessment = assess_audit(observed(*event))
    assert (assessment["score"], assessment["name"]) == expected
    assert assessment["definition"]
    assert assessment["findings"] or expected[0] == 5
    assert len(assessment["inputs"]) == 5


def test_critical_finding_outweighs_clean_checks_and_research_verdict_is_irrelevant():
    row = observation(run_state(), "Market Analyst", status="unusable", code="mixed_run_input")
    state = observed(row)
    for rating, evidence in (("Buy", "sufficient"), ("REVIEW", "insufficient")):
        state["final_rating"] = rating
        state["evidence_quality"] = {"status": evidence}
        assert assess_audit(state)["score"] == 1


def test_unrated_and_unknown_essential_stage_are_distinct():
    state = run_state()
    assert assess_audit(state)["score"] is None
    state = observed()
    state["operational_observations"].pop(next(k for k, v in state["operational_observations"].items()
                                              if v["stage"] == "Market Analyst"))
    result = assess_audit(state)
    assert result["score"] == 2
    assert "Market Analyst" in result["consequence"]


def test_stale_or_malformed_evidence_cannot_certify_completion():
    state = observed()
    key = next(k for k, v in state["operational_observations"].items() if v["stage"] == "Market Analyst")
    state["operational_observations"][key] = {**state["operational_observations"][key], "run_id": "other"}
    assert assess_audit(state)["score"] == 2
    state = observed()
    state["operational_observations"]["bogus"] = {"stage": "Market Analyst", "status": "completed"}
    assert assess_audit(state)["score"] == 2


def test_identity_conflicts_are_rejected_and_replay_is_idempotent():
    a = observation(run_state(), "Market Analyst")
    assert merge_observations({a["event_id"]: a}, {a["event_id"]: a}) == {a["event_id"]: a}
    other = run_state() | {"run_id": "other"}
    b = observation(other, "News Analyst")
    with pytest.raises(ValueError, match="identity"):
        merge_observations({a["event_id"]: a}, {b["event_id"]: b})
    assert settings_digest({"b": 1, "a": 2}) == settings_digest({"a": 2, "b": 1})


def test_review_route_uses_retained_expectations_and_renderers_share_verdict():
    state = run_state()
    row = observation(state, "Source Acquisition", expected_stages=STAGES + ["Bull Researcher", "Portfolio Manager"])
    gate = observation(state, "Evidence Check", route="review")
    rows = [row, gate, observation(state, "Market Analyst"), observation(state, "Run Metrics")]
    state["operational_observations"] = {r["event_id"]: r for r in rows}
    result = assess_audit(state)
    assert result["score"] == 5
    footer = render_assessment(result, "./operational_audit.md")
    detail = render_audit(result)
    assert footer.startswith("**Operational quality: 5/5 — Strong**")
    assert detail.startswith("# Operational audit\n\n**Operational quality: 5/5 — Strong**")
    assert footer.rstrip().endswith("[./operational_audit.md](./operational_audit.md)")
    assert "Bull Researcher" not in result["coverage"]["missing_stages"]


def test_unverified_export_is_low_confidence_and_compromised_export_is_critical():
    assert assess_audit(observed(), integrity="unverified")["score"] == 2
    assert assess_audit(observed(), integrity="compromised")["score"] == 1


def test_in_memory_assessment_names_integrity_check_as_not_applicable():
    result = assess_audit(observed(), integrity="not_applicable")
    assert result["score"] == 5
    assert result["inputs"]["Report integrity"] == "not applicable (in-memory rendering)"


def test_editorial_failure_affects_only_summary_and_review_is_intentional():
    state = observed()
    state["executive_summary"] = {"status": "unavailable"}
    result = assess_audit(state)
    assert result["score"] == 3
    assert "executive summary" in result["consequence"].lower()
    state["executive_summary"] = {"status": "review"}
    assert assess_audit(state)["score"] == 5


def test_detailed_audit_discloses_interrupted_attempt_coverage():
    from tradingagents.operational_audit import assess_audit, render_audit

    text = render_audit(assess_audit({}))
    assert "Observations cover completed nodes" in text
    assert "count and causes remain unknown after resume" in text


def test_followup_override_code_is_valid():
    event = observation(run_state(), "Research Manager", code="followup_judgment_overridden", scope="bear-1")
    assessment = assess_audit(observed(event))
    assert (assessment["score"], assessment["name"]) == (5, "Strong")
    assert not any("malformed" in finding["text"] for finding in assessment["findings"])
