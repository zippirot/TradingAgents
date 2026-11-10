"""The manager's earlier case weights are the reference for the next decision; a flag means the case's own inputs."""

from tradingagents.agents.decision_brief import _case_weights, attach_weights, render


def _case(role, weight, disposition="accepted", name=None):
    return {"role": role, "name": name or role.title(), "disposition": disposition, "weight": weight}


THEN = {"decision_context": {"scenario_decision": {"status": "addressed", "cases": [
    _case("base", "0.45"), _case("downside", "0.45"), _case("upside", "0.10")]}}}


def _brief(filings=None):
    return {"version": 1, "status": "available", "parts_unavailable": [],
            "prior": {"decision_id": "b9dde628-x", "published_at": "2026-11-10 20:47 UTC", "rating": "Underweight",
                      "as_of": "2026-11-10", "label": "x"},
            "filings": filings if filings is not None else {"status": "known", "rows": []},
            "weights": _case_weights(THEN)}


def _now(base, down, up, **kw):
    return {"status": "addressed", "cases": [_case("base", base, **kw), _case("downside", down), _case("upside", up)]}


def test_the_earlier_weights_are_read_from_the_saved_card():
    assert [(row["role"], row["weight"]) for row in _case_weights(THEN)["rows"]] == [
        ("base", "0.45"), ("downside", "0.45"), ("upside", "0.10")]
    for snapshot in ({}, {"decision_context": {"scenario_decision": {"status": "unaddressed", "cases": []}}},
                     {"decision_context": {"scenario_decision": {"status": "addressed", "cases": [{"role": "base"}]}}}):
        assert _case_weights(snapshot) == {"status": "none", "rows": []}


def test_the_manager_is_shown_its_earlier_weights_and_the_rule():
    text = "\n".join(render(_brief(), for_manager=True))
    assert "- Your case weights in that decision: base 45%, downside 45%, upside 10%." in text
    assert "reading the same evidence differently is not a new fact" in text
    assert "'Changed since the last decision:'" in text
    assert "Your case weights" not in "\n".join(render({**_brief(), "weights": {"status": "none", "rows": []}},
                                                       for_manager=True))


def test_unchanged_weights_read_as_unchanged_and_changed_ones_are_named():
    same = attach_weights(_brief(), _now("0.45", "0.45", "0.1"))
    assert same["weights"]["changed"] is False
    line = next(text for text in render(same) if text.startswith("- Case weights:"))
    assert line == "- Case weights: base 45%, downside 45%, upside 10% then; base 45%, downside 45%, upside 10% now."
    moved = attach_weights(_brief(), _now("0.5", "0.35", "0.15"))
    assert moved["weights"]["changed"] is True
    line = next(text for text in render(moved) if text.startswith("- Case weights:"))
    assert "base 50%, downside 35%, upside 15% now. Weights changed and no new filing was retained" in line
    assert "the earlier weight remains the reference" in line
    # With a new filing the change is stated without the label.
    filed = attach_weights(_brief({"status": "known", "rows": [{"form": "10-K", "filed_date": "2027-02-24"}]}),
                           _now("0.5", "0.35", "0.15"))
    line = next(text for text in render(filed) if text.startswith("- Case weights:"))
    assert line.endswith("now.") and "Weights changed" not in line


def test_a_rejection_counts_as_a_change_and_unmatched_cases_are_not_compared():
    rejected = attach_weights(_brief(), {"status": "addressed", "cases": [
        _case("base", "0.6"), _case("downside", None, disposition="rejected"), _case("upside", "0.4")]})
    assert rejected["weights"]["changed"] is True
    assert "downside rejected" in next(text for text in render(rejected) if text.startswith("- Case weights:"))
    other = attach_weights(_brief(), {"status": "addressed", "cases": [_case("base", "0.5"), _case("bear", "0.5")]})
    assert other["weights"]["changed"] is None
    assert "Not matched case for case" in next(text for text in render(other) if text.startswith("- Case weights:"))
    # Nothing to attach when this decision gave no usable answer, or the earlier one had none.
    assert "now" not in attach_weights(_brief(), {"status": "unaddressed", "cases": []})["weights"]
    plain = {**_brief(), "weights": {"status": "none", "rows": []}}
    assert attach_weights(plain, _now("0.5", "0.3", "0.2")) is plain
    assert attach_weights(None, _now("0.5", "0.3", "0.2")) is None


def test_weights_travel_from_one_publication_to_the_next_card(tmp_path, monkeypatch):
    from tests.test_assumption_history import inputs
    from tests.test_decision_brief import _published
    from tradingagents.agents.decision_brief import since_last_decision

    first = inputs()
    first["decision_context"]["scenario_decision"] = THEN["decision_context"]["scenario_decision"]
    config, _record = _published(tmp_path, monkeypatch, first)
    brief = since_last_decision(config, "DOCN", inputs())
    assert [row["weight"] for row in brief["weights"]["rows"]] == ["0.45", "0.45", "0.10"]
    assert any("Your case weights in that decision: base 45%" in text for text in render(brief, for_manager=True))


# What a flag means -----------------------------------------------------------------------------------

def _flagged(role, quote):
    from tests.test_disputed_case_range import inputs
    from tradingagents.agents.audit_pass import prepare_audit_dispositions

    value = inputs()
    value["advisory_audit"]["findings"][0].update(role=role, quoted_claim=quote)
    value["unvalidated_outputs"]["portfolio_manager"]["structured"]["audit_dispositions"] = [
        {"finding_id": f["finding_id"], "disposition": "accepted", "reason": "Reviewed"}
        for f in prepare_audit_dispositions(value)["findings"]]
    return value


def test_the_analysts_own_narrative_about_a_case_is_a_statement_not_a_disputed_input():
    from tradingagents.agents.decision_context import (
        prepare_decision_context,
        render_decision_context,
    )

    value = _flagged("fundamentals_analyst", "Funding is unassessed")
    card = prepare_decision_context(value)
    assert card["scenarios"]["disputed_count"] == 0
    text = render_decision_context(card)
    assert "corrects a statement the fundamentals analyst made about this case" in text
    assert "flagged by accepted audit finding" not in text


def test_a_finding_quoting_the_cases_own_input_still_disputes_it_whoever_is_named():
    from tradingagents.agents.decision_context import (
        prepare_decision_context,
        render_decision_context,
    )

    card = prepare_decision_context(_flagged("fundamentals_analyst", "The distinct equipment assumption."))
    assert card["scenarios"]["disputed_count"] == 1
    assert "flagged by accepted audit finding" in render_decision_context(card)
