"""The advisory model has no authority over evidence or the final rating."""

from tradingagents.agents.audit_pass import create_advisory_audit, render_advisory_audit


class FakeModel:
    def __init__(self, output=None, error=None):
        self.output = output
        self.error = error
        self.calls = []

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, prompt):
        self.calls.append(prompt)
        if self.error:
            raise self.error
        return self.output


def state():
    return {
        "shared_source_brief": "- [F1] Revenue: 100 USD; 2025.\n- S1: filing source",
        "canonical_financial_context": "Revenue was 100 USD [F1].",
        "valuation_reference_brief": "Peer median: 3.0 [P1].",
        "market_report": "The market report says revenue was 200 USD.",
        "sentiment_report": "Customers love the product.",
        "news_report": "There was a filing.",
        "fundamentals_report": "Revenue was 200 USD [F1].",
        "investment_debate_state": {"bull_history": "Revenue will double.", "bear_history": "Demand may decline."},
        "risk_debate_state": {"aggressive_history": "Buy now.", "conservative_history": "Liquidity is low.", "neutral_history": "The position is risky."},
        "investment_plan": "Revenue was 200 USD [F1].",
        "trader_investment_plan": "Buy at 120.",
        "final_rating": "Hold",
        "financial_evidence": {"immutable": True},
    }


def finding(role="fundamentals_analyst", quote="Revenue was 200 USD [F1].", label="F1", issue="contradiction"):
    return {"role": role, "quoted_claim": quote, "issue_type": issue,
            "evidence_label": label, "explanation": "The supplied evidence says 100 USD."}


def test_valid_finding_one_call_and_no_authority_change():
    model = FakeModel({"findings": [finding()]})
    original = state()
    output = create_advisory_audit(model, deep_model_id="deep", quick_model_id="quick")(original)
    record = output["advisory_audit"]
    assert len(model.calls) == 1
    assert list(output) == ["advisory_audit"]
    assert original["final_rating"] == "Hold"
    assert original["financial_evidence"] == {"immutable": True}
    assert record["status"] == "completed with findings"
    assert record["counts_by_type"] == {"unsupported_claim": 0, "contradiction": 1, "numerical_inconsistency": 0}
    assert record["independence_by_role"]["research_manager"] == "unknown"
    assert record["independence_by_role"]["fundamentals_analyst"] == "unknown"
    assert "Peer median: 3.0" in model.calls[0]


def test_partial_rejection_and_unknown_labels_or_misattributed_quotes():
    model = FakeModel({"findings": [finding(), finding(label="X99"),
                                      finding(role="trader", quote="Revenue was 200 USD [F1]."),
                                      finding(quote="Made up claim"), finding(role=["fundamentals_analyst"])]})
    record = create_advisory_audit(model, deep_model_id="same", quick_model_id="same")(state())["advisory_audit"]
    assert record["status"] == "completed with findings"
    assert record["submitted_count"] == 5
    assert record["accepted_count"] == 1
    assert record["rejected_count"] == 4
    assert len(record["rejection_reasons"]) == 4
    assert all(value == "unknown" for value in record["independence_by_role"].values())
    assert "4 rejected" in render_advisory_audit(record)


def test_all_rejected_is_unavailable_but_valid_empty_is_zero():
    bad = FakeModel({"findings": [finding(label="BAD9")]})
    empty = FakeModel({"findings": []})
    bad_record = create_advisory_audit(bad, deep_model_id="d", quick_model_id="q")(state())["advisory_audit"]
    empty_record = create_advisory_audit(empty, deep_model_id="d", quick_model_id="q")(state())["advisory_audit"]
    assert bad_record["status"] == "unavailable"
    assert bad_record["rejected_count"] == 1
    assert empty_record["status"] == "completed with zero findings"
    assert empty_record["submitted_count"] == 0


def test_over_limit_malformed_and_provider_error_are_unavailable_without_retry():
    for output, error in (({"findings": [finding()] * 21}, None), ({"findings": "bad"}, None), (None, RuntimeError("private provider detail"))):
        model = FakeModel(output, error)
        record = create_advisory_audit(model, deep_model_id="d", quick_model_id="q")(state())["advisory_audit"]
        assert record["status"] == "unavailable"
        assert len(model.calls) == 1
        assert "private provider detail" not in render_advisory_audit(record)


def test_render_escapes_model_text_and_is_bounded():
    model = FakeModel({"findings": [finding(issue="numerical_inconsistency") | {"explanation": "<script>alert(1)</script> **FAKE** " * 1000}]})
    record = create_advisory_audit(model, deep_model_id="d", quick_model_id="q")(state())["advisory_audit"]
    rendered = render_advisory_audit(record)
    assert "<script>" not in rendered
    assert "**FAKE**" not in rendered
    assert len(rendered) < 10000


def test_real_brief_ids_and_price_source_are_accepted():
    from tradingagents.agents.audit_pass import AuditOutput

    original = state()
    original["shared_source_brief"] = (
        '{"fact_id":"f-abc","metric":"Revenue","source_ids":["sec-f123"],'
        '"input_fact_ids":["f-parent"]}\n'
        'Source sec-f123; filed 2026-09-30; https://www.sec.gov/example\n'
        'Canonical completed price: 20 USD; source_id yahoo-price-abcdef.'
    )
    original["canonical_financial_context"] = (
        "- [F1] Revenue: 100 USD\n- S1: source_id sec-f123"
    )
    original["fundamentals_report"] = "Revenue was 200 USD [F1]."
    model = FakeModel({"findings": [
        finding(label="f-abc"), finding(label="sec-f123"),
        finding(label="f-parent"), finding(label="yahoo-price-abcdef"),
        finding(label="F1"), finding(label="S1"),
        finding(label="sec-not-supplied"),
    ]})
    record = create_advisory_audit(model, deep_model_id="d", quick_model_id="q")(original)["advisory_audit"]
    assert record["accepted_count"] == 6
    assert record["rejected_count"] == 1
    schema = AuditOutput.model_json_schema()
    props = schema["$defs"]["AuditFinding"]["properties"]
    assert set(props) == {"role", "quoted_claim", "issue_type", "evidence_label", "explanation", "case_id"}


def test_renderer_tolerates_corrupt_saved_record_without_markup():
    rendered = render_advisory_audit({
        "status": "completed with findings",
        "counts_by_type": {"contradiction": "<script>x</script>"},
        "independence_by_role": {"<script>bad</script>": "same model"},
        "findings": "bad",
        "rejected_count": "bad",
    })
    assert "<script>" not in rendered
    assert "Advisory audit" in rendered


def test_audit_reads_original_fundamentals_after_gate_and_discloses_bounded_inputs():
    model = FakeModel({"findings": [finding()]})
    original = state()
    original["financial_claim_validation"] = {"raw_report": original["fundamentals_report"]}
    original["fundamentals_report"] = "Canonical financial evidence: revenue 100."
    original["news_report"] = "News text. " * 1000
    record = create_advisory_audit(model, deep_model_id="same", quick_model_id="same")(original)["advisory_audit"]
    assert record["accepted_count"] == 1
    assert record["input_truncation"]["news_analyst"] is True
    assert record["input_truncation"]["fundamentals_analyst"] is False
    assert "bounded" in render_advisory_audit(record).lower()
