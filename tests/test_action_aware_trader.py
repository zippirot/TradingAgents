from io import StringIO

from rich.console import Console

from cli import display
from tradingagents.agents.schemas import TraderProposal, render_trader_proposal
from tradingagents.memory.thesis import legacy_thesis_context
from tradingagents.report_html import render_report
from tradingagents.reporting import prepare_report_state


def test_action_aware_structured_levels():
    buy = render_trader_proposal(TraderProposal(action="Buy", reasoning="Buy case.", purchase_entry_price=75))
    sell = render_trader_proposal(TraderProposal(action="Sell", reasoning="Sell case.", reference_sale_level=79, purchase_entry_price=75))
    hold = render_trader_proposal(TraderProposal(action="Hold", reasoning="Wait."))
    assert "**Purchase Entry Price**: 75.0" in buy
    assert "**Reference Sale Level**: 79.0" in sell
    assert "**Purchase Entry Price**: 75.0" not in sell
    assert "**Reference Sale Level**: not provided" in hold
    assert "advisory" in sell.lower() and "holdings" in sell.lower()
    assert "FINAL TRANSACTION PROPOSAL: **SELL**" in sell


def test_legacy_price_is_explicitly_ambiguous():
    proposal = TraderProposal.model_validate({"action": "Sell", "reasoning": "Older record.", "entry_price": 77})
    assert "Legacy Price Level (meaning unverified)" in render_trader_proposal(proposal)
    assert "**Purchase Entry Price**: 77" not in render_trader_proposal(proposal)
    assert "entry_price" not in proposal.model_dump()


def test_legacy_free_text_is_labeled_in_every_report_consumer(monkeypatch):
    raw = "**Action**: Sell\n**Entry Price**: 77\nFINAL TRANSACTION PROPOSAL: **SELL**"
    state = {"trader_investment_plan": raw, "trade_date": "2026-11-05"}
    prepared = prepare_report_state(state)
    assert "**Legacy Price Level (meaning unverified)**: 77" in prepared["trader_investment_plan"]
    assert state["trader_investment_plan"] == raw
    from tradingagents.reporting import _report_parts
    html = render_report("DOCN", state, None, _report_parts(state))
    assert "Legacy Price Level (meaning unverified)" in html
    output = StringIO()
    monkeypatch.setattr(display, "console", Console(file=output, force_terminal=False, width=120))
    display.display_complete_report(state)
    assert "Legacy Price Level (meaning unverified)" in output.getvalue()


def test_structurally_fact_only_legacy_decision_is_omitted_but_thesis_survives():
    fact_only = ("**Rating**: Hold\n\n**Executive Summary**: Model recommendation; financial evidence and "
                 "valuation coverage are shown below. This does not validate all model reasoning.\n\n"
                 "**Investment Thesis — canonical evidence**:\n\nFacts only.\n\n"
                 "Original model narrative is retained separately in evidence.json diagnostics.")
    entries = [{"ticker": "DOCN", "date": "2026-11-04", "decision": fact_only}]
    assert legacy_thesis_context(entries, "DOCN", "2026-11-05") == ""
    entries[0]["decision"] = fact_only.replace("Facts only.", "Thesis continuity — advisory, not binding.\nRationale: Genuine thesis.")
    assert "Genuine thesis" in legacy_thesis_context(entries, "DOCN", "2026-11-05")


def test_new_schema_does_not_offer_legacy_entry_field():
    properties = TraderProposal.model_json_schema()["properties"]
    assert "purchase_entry_price" in properties
    assert "reference_sale_level" in properties
    assert "entry_price" not in properties


def test_free_text_fallback_labels_ambiguous_price():
    from unittest.mock import MagicMock

    from tradingagents.agents.trader.trader import create_trader

    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError("unsupported")
    llm.invoke.return_value = MagicMock(content="**Action**: Sell\n- Entry Price: 77\nFINAL TRANSACTION PROPOSAL: **SELL**")
    state = {"company_of_interest": "DOCN", "investment_plan": "Sell", "market_report": ""}
    output = create_trader(llm)(state)["trader_investment_plan"]
    assert "**Legacy Price Level (meaning unverified)**: 77" in output
    assert "FINAL TRANSACTION PROPOSAL: **SELL**" in output


def test_sell_fallback_purchase_label_is_not_published_as_purchase_entry():
    from unittest.mock import MagicMock

    from tradingagents.agents.trader.trader import create_trader

    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError("unsupported")
    llm.invoke.return_value = MagicMock(content=(
        "**Action**: Sell\n**Purchase Entry Price**: 77\n"
        "FINAL TRANSACTION PROPOSAL: **SELL**"
    ))
    state = {"company_of_interest": "DOCN", "investment_plan": "Sell", "market_report": ""}
    output = create_trader(llm)(state)["trader_investment_plan"]
    assert "**Purchase Entry Price**: 77" not in output
    assert "**Legacy Price Level (meaning unverified)**: 77" in output
    assert "FINAL TRANSACTION PROPOSAL: **SELL**" in output
    report = prepare_report_state({"trader_investment_plan": llm.invoke.return_value.content})
    assert "**Purchase Entry Price**: 77" not in report["trader_investment_plan"]
