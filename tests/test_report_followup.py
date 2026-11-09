"""Follow-up to the report defect closure (Build Y): defects seen in DOCN run eea86100."""

import json
from unittest.mock import MagicMock

from tests.test_structured_agents import _make_trader_state, _structured_trader_llm
from tradingagents.agents.audit_pass import _case_context
from tradingagents.agents.citation_check import check_pm_citations
from tradingagents.agents.schemas import (
    TraderProposal,
    label_legacy_trader_price,
    qualitative_sizing,
    render_trader_proposal,
)
from tradingagents.agents.trader.trader import create_trader

_CARRIED = "Carried from the Research Manager's plan (not restated by the Trader)"
_RM_PLAN = ("**Recommendation**: Underweight\n\n**Rationale**: Bear wins.\n\n"
            "**Strategic Actions**: Trim exposure into strength.\n\n"
            "**Triggers**\n- Revenue below $348m\n- Gross margin below 50.15%")
_WITHHELD = ("Numeric sizing withheld: sizing is qualitative only without verified "
             "portfolio and loss-budget assumptions.")


# Y1 ------------------------------------------------------------------------

def test_structured_trader_carries_rm_actions_and_triggers():
    captured = {}
    proposal = TraderProposal(action="Sell", reasoning="Trim.", advisory_invalidation_level=90.5)
    trader = create_trader(_structured_trader_llm(captured, proposal))
    result = trader({**_make_trader_state(), "investment_plan": _RM_PLAN})
    text = result["trader_investment_plan"]
    assert text.count(_CARRIED) == 1
    assert "Trim exposure into strength." in text
    assert "**Triggers**\n- Revenue below $348m\n- Gross margin below 50.15%" in text
    assert "FINAL TRANSACTION PROPOSAL: **SELL**" in text
    assert result["messages"][0].content == text


def test_free_text_trader_carries_the_block_exactly_once():
    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
    llm.invoke.return_value = MagicMock(
        content="**Action**: Sell\n\n**Reasoning**\n\nBecause.", response_metadata={})
    text = create_trader(llm)({**_make_trader_state(), "investment_plan": _RM_PLAN})["trader_investment_plan"]
    assert text.count(_CARRIED) == 1
    assert "- Gross margin below 50.15%" in text


_PRICED_RM_PLAN = ("**Recommendation**: Underweight\n\n"
                   "**Strategic Actions**: Trim exposure.\nStop Loss: 95\nEntry Price: 70\n\n"
                   "**Rationale**: Bear wins.")


def _fallback_llm(content):
    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
    llm.invoke.return_value = MagicMock(content=content, response_metadata={})
    return llm


def test_carried_block_keeps_price_shaped_manager_lines_word_for_word():
    """The price relabelling is for the Trader's own text; the block says it is copied."""
    structured = create_trader(_structured_trader_llm(
        {}, TraderProposal(action="Sell", reasoning="Trim.", advisory_invalidation_level=90.5)))
    free_text = create_trader(_fallback_llm("**Action**: Sell\n\n**Reasoning**\n\nBecause.\n\nStop Loss: 88"))
    for trader in (structured, free_text):
        result = trader({**_make_trader_state(), "investment_plan": _PRICED_RM_PLAN})
        text = result["trader_investment_plan"]
        carried = text[text.index(_CARRIED):]
        assert "Trim exposure.\nStop Loss: 95\nEntry Price: 70" in carried
        assert "Advisory Thesis Invalidation Level" not in carried and "Legacy Price Level" not in carried
        assert result["messages"][0].content == text
        # Report preparation applies the relabelling again.
        assert label_legacy_trader_price(text) == text
    lines = [line for line in structured({**_make_trader_state(), "investment_plan": _PRICED_RM_PLAN})[
        "trader_investment_plan"].splitlines() if "Advisory Thesis Invalidation Level" in line]
    assert lines == ["**Advisory Thesis Invalidation Level**: 90.5"]


def test_trader_authored_stop_on_a_sell_is_still_relabelled():
    text = create_trader(_fallback_llm("**Action**: Sell\n\n**Reasoning**\n\nBecause.\n\nStop Loss: 88"))(
        {**_make_trader_state(), "investment_plan": _PRICED_RM_PLAN})["trader_investment_plan"]
    own = text[:text.index("**" + _CARRIED)]
    assert "**Advisory Thesis Invalidation Level (unvalidated)**: 88" in own
    assert "Stop Loss" not in own
    assert own.rstrip().endswith("holdings may be unknown.")


# Y2 ------------------------------------------------------------------------

def _labelled(**fields):
    return label_legacy_trader_price(render_trader_proposal(TraderProposal(reasoning="Why.", **fields)))


def test_sell_prints_one_invalidation_line_with_its_level():
    text = _labelled(action="Sell", advisory_invalidation_level=90.5)
    lines = [line for line in text.splitlines() if "Advisory Thesis Invalidation Level" in line]
    assert lines == ["**Advisory Thesis Invalidation Level**: 90.5"]
    assert "Stop Loss" not in text and "(unvalidated)" not in text
    assert text.rstrip().endswith("FINAL TRANSACTION PROPOSAL: **SELL**")


def test_sell_without_a_level_still_prints_one_line():
    text = _labelled(action="Sell")
    lines = [line for line in text.splitlines() if "Advisory Thesis Invalidation Level" in line]
    assert lines == ["**Advisory Thesis Invalidation Level**: not provided"]


def test_buy_and_hold_keep_the_stop_loss_row():
    assert "**Stop Loss**: 60.0" in render_trader_proposal(
        TraderProposal(action="Buy", reasoning="Why.", stop_loss=60))
    assert "**Stop Loss**: not provided" in render_trader_proposal(
        TraderProposal(action="Hold", reasoning="Why."))


# Y3 ------------------------------------------------------------------------

_EEA_SIZING = ("Holdings unknown. Trim in stages toward a modest underweight, roughly 25–35% below "
               "your standard DOCN allocation, and keep a core position. Add nothing new until there "
               "is source-verified settlement of the 2026 notes and clarity on at-the-market share "
               "sales. This is not a short.")


def test_numeric_sizing_sentence_is_withheld_and_the_rest_kept():
    text = qualitative_sizing(_EEA_SIZING)
    assert "25" not in text and "35%" not in text
    assert text.startswith("Holdings unknown. Add nothing new until there is source-verified "
                           "settlement of the 2026 notes")
    assert "This is not a short." in text
    assert text.endswith(_WITHHELD)


def test_qualitative_sizing_is_unchanged():
    text = "Holdings unknown. Trim modestly and keep a core position until the 2026 notes settle."
    assert qualitative_sizing(text) == text
    assert qualitative_sizing(None) is None


def test_other_numeric_allocations_are_withheld():
    for sentence in ("Sell 500 shares now.", "Cut exposure by $25,000.", "Reduce by 50 bps.",
                     "Sell half of the position.", "Keep 5 percent of portfolio."):
        assert qualitative_sizing(sentence) == _WITHHELD, sentence


def test_rendered_proposal_uses_the_qualitative_sizing():
    text = render_trader_proposal(TraderProposal(action="Sell", reasoning="Why.", position_sizing=_EEA_SIZING))
    assert "25–35%" not in text
    assert "**Position Sizing**: Holdings unknown." in text and _WITHHELD in text


def test_trader_is_asked_for_qualitative_sizing_only():
    captured = {}
    create_trader(_structured_trader_llm(captured))(_make_trader_state())
    prompt = " ".join(message["content"] for message in captured["prompt"])
    assert "qualitative" in prompt
    description = TraderProposal.model_json_schema()["properties"]["position_sizing"]["description"]
    assert "qualitative" in description.lower() and "%" not in description


def test_currency_code_and_fraction_allocations_are_withheld():
    for text in ("Allocate USD 25,000.", "Reduce the position by 1/2.", "Sell one-third now.",
                 "Cut the position in half.", "Trim by EUR 10k."):
        assert qualitative_sizing(text) == _WITHHELD, text


def test_dates_and_qualitative_sentences_survive_the_sizing_filter():
    for text in ("Add nothing until the second half of 2027.", "Review on 11/09/2026.",
                 "Hold a core position through the December 1, 2026 maturity."):
        assert qualitative_sizing(text) == text
    proposal = TraderProposal(
        action="Sell", reasoning="Trim.",
        position_sizing="Keep a core position. Allocate USD 25,000. Review on 11/09/2026.")
    expected = f"**Position Sizing**: Keep a core position. Review on 11/09/2026. {_WITHHELD}"
    assert expected in render_trader_proposal(proposal)
    text = create_trader(_structured_trader_llm({}, proposal))(_make_trader_state())["trader_investment_plan"]
    assert expected in text and "25,000" not in text and text.count(_WITHHELD) == 1


# Y4 ------------------------------------------------------------------------

_BRIEF = """Accepted evidence brief

<!-- evidence-references:start -->
- K2: source_id rpo-prior; source
<!-- evidence-references:end -->"""


def _rpo_state(thesis):
    return {
        "canonical_financial_context": _BRIEF,
        "unvalidated_outputs": {"portfolio_manager": {"structured": {
            "executive_summary": "", "investment_thesis": thesis}}},
        "disclosure_evidence": {"kpi_comparisons": [{
            "status": "pass", "current_value": "799707000", "prior_value": "893828000",
            "absolute_change": "-94121000",
            "percentage_change": "-10.530101988301999937348125142644893648442429639707",
            "currency": "USD",
            "sources": {"current": {"source_id": "rpo-current"}, "prior": {"source_id": "rpo-prior"}},
        }]},
    }


def test_k_label_matches_the_change_between_its_two_figures():
    for sentence in ("RPO fell 10.53% sequentially (K2, S27); its cause is not established.",
                     "RPO changed -10.53% sequentially (K2).",
                     "RPO declined by $94.1 million in the quarter (K2)."):
        result = check_pm_citations(_rpo_state(sentence))
        assert (result["matched"], result["checked"], result["mismatches"]) == (1, 1, []), sentence


def test_k_label_with_a_wrong_change_is_still_a_mismatch():
    result = check_pm_citations(_rpo_state("RPO fell 12.00% sequentially (K2)."))
    assert (result["matched"], result["checked"]) == (0, 1)
    assert result["mismatches"][0]["citation_id"] == "K2"


def test_failed_comparison_adds_no_change_values():
    state = _rpo_state("RPO fell 10.53% sequentially (K2).")
    state["disclosure_evidence"]["kpi_comparisons"][0]["status"] = "fail"
    result = check_pm_citations(state)
    assert result["matched"] == 0 and result["unresolved_citations"] == ["K2"]


# Y5 ------------------------------------------------------------------------

def _rows(*sizes):
    return {"rows": [{"case_id": f"case-{index}", "name": f"Case {index}",
                      "request": {"note": "x" * size}} for index, size in enumerate(sizes)]}


def test_each_valuation_case_has_its_own_audit_budget(monkeypatch):
    monkeypatch.setattr("tradingagents.agents.shared_valuation.replay_cases", lambda state: _rows(3500, 2500, 3500))
    context = _case_context({})
    cases = json.loads(context["shared_valuation_cases"])
    assert [len(case["request"]["note"]) for case in cases] == [3500, 2500, 3500]
    assert json.loads(context["shared_valuation_case_coverage"]) == {"total_cases": 3, "requests_omitted": 0}


def test_an_oversized_case_is_omitted_and_counted_without_hiding_the_others(monkeypatch):
    monkeypatch.setattr("tradingagents.agents.shared_valuation.replay_cases", lambda state: _rows(9000, 2500))
    context = _case_context({})
    cases = json.loads(context["shared_valuation_cases"])
    assert cases[0] == {"case_id": "case-0", "name": "Case 0",
                        "request": "omitted at 8000-character per-case input cap"}
    assert len(cases[1]["request"]["note"]) == 2500
    assert json.loads(context["shared_valuation_case_coverage"]) == {"total_cases": 2, "requests_omitted": 1}
