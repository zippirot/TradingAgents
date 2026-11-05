"""Portfolio-manager integration uses synthetic facts and one mocked model call."""

from unittest.mock import MagicMock

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
from tradingagents.dataflows.financial_evidence import EvidencePackage, FinancialFact, SourceRecord


def evidence():
    source = SourceRecord(
        source_id="source",
        cik="0001582961",
        url="https://www.sec.gov/example",
        filed_date="2026-02-01",
        retrieved_at="2026-11-04T12:00:00Z",
        content_hash="a" * 64,
        locator="synthetic",
        form="10-K",
    )
    eps = FinancialFact(
        fact_id="eps-source-id",
        metric="Diluted EPS",
        value=2,
        unit="USD/shares",
        period_start="2025-01-01",
        period_end="2025-12-31",
        as_of="2026-10-19",
        cik=source.cik,
        source_ids=(source.source_id,),
        locator="synthetic/eps",
    )
    return EvidencePackage(cik=source.cik, as_of=eps.as_of, sources=(source,), facts=(eps,))


def request():
    return {
        "method": "pe",
        "eps_fact_id": "eps-source-id",
        "eps_basis": "diluted",
        "accounting_basis": "US-GAAP",
        "multiple": "20",
        "multiple_rationale": "Subjective test multiple.",
    }


def decision(**overrides):
    values = {
        "rating": "Buy",
        "executive_summary": "Qualitative summary.",
        "investment_thesis": "Qualitative thesis.",
        "price_target": 96,
    }
    values.update(overrides)
    return PortfolioDecision(**values)


def state():
    return {
        "company_of_interest": "DOCN",
        "trade_date": "2026-10-19",
        "investment_plan": "Plan",
        "trader_investment_plan": "Proposal",
        "financial_evidence": evidence().model_dump(mode="json"),
        "unvalidated_outputs": {"earlier": "retain me"},
        "risk_debate_state": {
            "history": "Debate",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "count": 1,
        },
    }


def invoke(value, inputs=None):
    llm = MagicMock()
    llm.with_structured_output.return_value.invoke.return_value = value
    result = create_portfolio_manager(llm)(inputs or state())
    return result, llm


def test_legacy_target_is_preserved_as_input_but_not_rendered():
    raw = decision()
    assert raw.price_target == 96
    rendered = render_pm_decision(raw)
    assert "**Price Target**: not provided" in rendered
    assert "96" not in rendered


def test_portfolio_schema_exposes_optional_typed_valuation():
    raw = decision(valuation_request=request())
    assert raw.valuation_request.method == "pe"
    assert raw.valuation_request.multiple == 20
    schema = PortfolioDecision.model_json_schema()
    assert "valuation_request" in schema["properties"]


def test_portfolio_validates_once_and_renders_formula_derived_target():
    result, llm = invoke(decision(valuation_request=request()))
    assert result["final_rating"] == "Buy"
    assert result["target_validation"]["status"] == "supported"
    assert result["target_validation"]["target"] == "40"
    assert result["target_validation"]["request"]["eps_fact_id"] == "eps-source-id"
    text = result["final_trade_decision"]
    assert "**Conditional valuation sensitivity**: 40" in text and "96" not in text
    assert "eps-source-id" in text
    assert "20" in text and "historical" in text.lower()
    llm.with_structured_output.return_value.invoke.assert_called_once()
    llm.invoke.assert_not_called()


def test_original_structured_output_and_earlier_diagnostics_survive():
    result, _ = invoke(decision(valuation_request=request()))
    assert result["unvalidated_outputs"]["earlier"] == "retain me"
    saved = result["unvalidated_outputs"]["portfolio_manager"]["structured"]
    assert saved["price_target"] == 96
    assert saved["valuation_request"]["method"] == "pe"


def test_unsupported_request_does_not_discard_rating_or_trigger_retry():
    raw = decision(valuation_request={"method": "dcf", "target": 96})
    assert raw.valuation_request is None
    result, llm = invoke(raw)
    assert result["final_rating"] == "Buy"
    assert result["target_validation"]["target"] is None
    assert result["target_validation"]["request"] == {"method": "dcf", "target": 96}
    assert "96" not in result["final_trade_decision"]
    llm.invoke.assert_not_called()


def test_missing_canonical_evidence_omits_target_without_calling_more_models():
    inputs = state()
    inputs.pop("financial_evidence")
    result, llm = invoke(decision(valuation_request=request()), inputs)
    assert result["target_validation"]["target"] is None
    assert result["target_validation"]["reasons"]
    llm.invoke.assert_not_called()


def test_prompt_contains_bounded_canonical_fact_ids():
    _, llm = invoke(decision(valuation_request=request()))
    prompt = llm.with_structured_output.return_value.invoke.call_args.args[0]
    assert "eps-source-id" in prompt
    assert "valuation_request" in prompt
    assert "management" in prompt.lower()


def test_model_cannot_self_certify_management_outlook():
    future = request()
    future["forecast"] = {
        "value": "3",
        "unit": "USD/shares",
        "period_start": "2027-01-01",
        "period_end": "2027-12-31",
        "basis": "US-GAAP",
        "kind": "management_guidance",
        "rationale": "Claimed management forecast.",
        "outlook_id": "claimed-by-model",
    }
    result, _ = invoke(decision(valuation_request=future))
    assert result["target_validation"]["target"] is None
    assert any("grounded" in reason for reason in result["target_validation"]["reasons"])


def test_free_text_fallback_is_saved_with_no_fabricated_target():
    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError
    llm.invoke.return_value.content = "Rating: Buy\nTarget $96."
    result = create_portfolio_manager(llm)(state())
    assert result["final_rating"] == "Buy"
    assert result["target_validation"]["target"] is None
    assert result["target_validation"]["request"] is None
    assert (
        result["unvalidated_outputs"]["portfolio_manager"]["fallback"] == "Rating: Buy\nTarget $96."
    )
    llm.invoke.assert_called_once()


def test_renderer_accepts_validation_dict_with_replay_request():
    from tradingagents.agents.schemas import render_target_result

    result, _ = invoke(decision(valuation_request=request()))
    rendered = render_target_result(result["target_validation"])
    assert "40" in rendered and "eps-source-id" in rendered
    assert "96" not in rendered


def test_invalid_request_survives_revalidation_for_diagnostics():
    original = decision(valuation_request={"method": "unsupported", "target": 96})
    revalidated = PortfolioDecision.model_validate(original)
    result, _ = invoke(revalidated)
    assert result["target_validation"]["request"] == {"method": "unsupported", "target": 96}
    assert (
        result["unvalidated_outputs"]["portfolio_manager"]["structured"]["valuation_request"][
            "target"
        ]
        == 96
    )


def test_large_canonical_evidence_context_is_bounded_without_extra_calls():
    package = evidence()
    prototype = package.facts[0]
    facts = [prototype]
    for index in range(200):
        facts.append(
            prototype.model_copy(
                update={
                    "fact_id": f"extra-{index}",
                    "metric": f"Extra metric {index}",
                    "locator": "Synthetic " + "x" * 700,
                }
            )
        )
    package = package.model_copy(update={"facts": tuple(facts)})
    assert len(package.model_dump_json()) > 100000
    inputs = state()
    inputs["financial_evidence"] = package.model_dump(mode="json")
    result, llm = invoke(decision(valuation_request=request()), inputs)
    prompt = llm.with_structured_output.return_value.invoke.call_args.args[0]
    assert len(prompt) < 70000
    assert "eps-source-id" in prompt
    assert result["target_validation"]["target"] == "40"
    llm.invoke.assert_not_called()


def test_pm_receives_grounded_outlook_ids_and_ranges_in_primary_call():
    from tests.test_valuation_outlooks import state as outlook_state
    from tradingagents.agents.valuation_outlooks import grounded_outlooks

    inputs = {**state(), **outlook_state()}
    outlook = grounded_outlooks(inputs)[0]
    _, llm = invoke(decision(), inputs)
    prompt = str(llm.with_structured_output.return_value.invoke.call_args)
    assert outlook.record_id in prompt
    assert "1170000000" in prompt
    assert "guidance" in prompt
