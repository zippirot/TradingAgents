"""The evidence boundary preserves asset scope and readable failure results."""

from tradingagents.agents.evidence_validation import create_evidence_gate


def test_unselected_or_nonstock_scope_never_fetches_sec(monkeypatch):
    from tradingagents.dataflows.vendors import sec_edgar

    monkeypatch.setattr(
        sec_edgar,
        "cik_for",
        lambda ticker: (_ for _ in ()).throw(AssertionError("SEC must not be called")),
    )
    for selected, asset in [(["market"], "stock"), (["fundamentals"], "crypto")]:
        result = create_evidence_gate(selected)({"asset_type": asset})
        assert result["evidence_quality"]["scope"] == "not_applicable"
        assert "final_rating" not in result


def test_unavailable_sec_lookup_is_readable_review(monkeypatch):
    from tradingagents.dataflows.errors import VendorUnavailableError
    from tradingagents.dataflows.vendors import sec_edgar

    def unavailable(ticker):
        raise VendorUnavailableError("SEC unavailable")

    monkeypatch.setattr(sec_edgar, "cik_for", unavailable)
    result = create_evidence_gate(["fundamentals"])(
        {
            "asset_type": "stock",
            "company_of_interest": "DOCN",
            "trade_date": "2026-10-19",
            "fundamentals_report": "Saved research",
        }
    )
    assert result["final_rating"] == "REVIEW"
    assert "SEC unavailable" in result["final_trade_decision"]
    assert "fundamentals_report" not in result


def test_non_sec_instrument_is_explicitly_outside_scope(monkeypatch):
    from tradingagents.dataflows.vendors import sec_edgar

    monkeypatch.setattr(sec_edgar, "cik_for", lambda ticker: None)
    result = create_evidence_gate(["fundamentals"])(
        {"asset_type": "stock", "company_of_interest": "OTHER", "trade_date": "2026-10-19"}
    )
    assert result["evidence_quality"]["scope"] == "not_applicable"
    assert "final_rating" not in result


def test_graph_routes_missing_evidence_to_end_before_debate(monkeypatch):
    from langchain_core.messages import AIMessage

    from tradingagents.dataflows.errors import VendorUnavailableError
    from tradingagents.dataflows.vendors import sec_edgar
    from tradingagents.graph import setup
    from tradingagents.graph.conditional_logic import ConditionalLogic
    from tradingagents.graph.propagation import Propagator

    def unavailable(ticker):
        raise VendorUnavailableError("SEC unavailable")

    monkeypatch.setattr(sec_edgar, "cik_for", unavailable)
    monkeypatch.setattr(
        setup,
        "create_fundamentals_analyst",
        lambda llm: (
            lambda state: {
                "messages": [AIMessage(content="Saved research")],
                "fundamentals_report": "Saved research",
            }
        ),
    )

    def forbidden_factory(llm):
        def forbidden(state):
            raise AssertionError("Debate must not run with critical evidence unavailable")

        return forbidden

    for name in (
        "create_bull_researcher",
        "create_bear_researcher",
        "create_research_manager",
        "create_trader",
        "create_aggressive_debator",
        "create_neutral_debator",
        "create_conservative_debator",
        "create_portfolio_manager",
    ):
        monkeypatch.setattr(setup, name, forbidden_factory)
    graph = (
        setup.GraphSetup(object(), object(), ConditionalLogic(), 1)
        .setup_graph(["fundamentals"])
        .compile()
    )
    result = graph.invoke(Propagator().create_initial_state("DOCN", "2026-10-19"))
    assert result["final_rating"] == "REVIEW"
    assert result["fundamentals_report"] == "Saved research"
    assert result["investment_plan"] == ""
    assert result["evidence_quality"]["status"] == "insufficient"


def test_filing_equity_bridge_uses_verified_cells_and_rejects_omitted_movement():
    from tests.test_filing_facts import EQUITY, package as filing_package
    from tradingagents.agents.evidence_validation import filing_accounting_evidence
    from tradingagents.dataflows.financial_evidence import EvidencePackage
    from tradingagents.dataflows.vendors.sec_documents import SourceBlock

    docs = filing_package(EQUITY)
    base = EvidencePackage(cik=docs.cik, as_of=docs.as_of)
    merged, calculations, extraction = filing_accounting_evidence(base, docs)
    assert calculations[0].status == "pass"
    assert any(f.metric == "Equity Common Stock Issuance Value" for f in merged.facts)
    assert extraction.equity_coverage[0].complete
    bad_table = EQUITY.replace("Net income | 0 | 30000 ;", "Unclassified movement | 0 | 30000 ;")
    bad_doc = docs.documents[0].model_copy(
        update={
            "blocks": (
                SourceBlock(
                    locator="table-1", section=docs.documents[0].blocks[0].section, text=bad_table
                ),
            )
        }
    )
    bad_docs = docs.model_copy(update={"documents": (bad_doc,)})
    _, calculations, _ = filing_accounting_evidence(base, bad_docs)
    assert calculations[0].status == "unavailable"


def test_gate_acquires_verified_filing_cells_without_relying_on_model_choice(monkeypatch):
    from tests.test_evidence_validation import package as facts_package, report
    from tests.test_filing_facts import EQUITY, package as filing_package
    from tradingagents.dataflows.vendors import sec_documents, sec_edgar

    docs = filing_package(EQUITY)
    facts = facts_package().model_copy(
        update={
            "cik": docs.cik,
            "facts": tuple(f.model_copy(update={"cik": docs.cik}) for f in facts_package().facts),
            "sources": tuple(
                s.model_copy(update={"cik": docs.cik}) for s in facts_package().sources
            ),
        }
    )
    monkeypatch.setattr(sec_edgar, "cik_for", lambda ticker: docs.cik)
    monkeypatch.setattr(sec_edgar, "get_financial_evidence", lambda *args: facts)
    calls = []
    monkeypatch.setattr(
        sec_documents, "get_filing_evidence", lambda *args: calls.append(args) or docs
    )
    result = create_evidence_gate(["fundamentals"])(
        {
            "asset_type": "stock",
            "company_of_interest": "DOCN",
            "trade_date": "2026-10-19",
            "fundamentals_report": report(),
        }
    )
    assert calls == [("DOCN", "2026-10-19")]
    assert any(
        c["method"] == "opening_equity_plus_disclosed_movements_v1" and c["status"] == "pass"
        for c in result["financial_calculations"]
    )


def test_conflicting_reported_values_cannot_pass_source_integrity():
    from decimal import Decimal

    from tests.test_evidence_validation import package, report
    from tradingagents.agents.evidence_validation import assess_financial_package

    base = package()
    contradiction = base.facts[0].model_copy(update={"fact_id": "conflict", "value": Decimal(99)})
    result = assess_financial_package(
        {"fundamentals_report": report()},
        base.model_copy(update={"facts": (*base.facts, contradiction)}),
    )
    checks = {c["code"]: c for c in result["evidence_quality"]["checks"]}
    assert checks["source_integrity"]["status"] == "fail"


def test_obligation_gate_requires_short_term_coverage_or_explicit_total():
    from decimal import Decimal

    from tests.test_evidence_validation import package
    from tradingagents.agents.evidence_validation import obligation_checks

    base = package()
    values = {
        "Total Assets": 200,
        "Long-term Borrowings (including current)": 100,
        "Cash and Equivalents": 20,
        "Finance Lease Liabilities": 5,
        "Equipment Financing Obligations": 3,
        "Operating Lease Liabilities": 7,
    }
    facts = tuple(
        base.facts[0].model_copy(
            update={
                "fact_id": metric,
                "metric": metric,
                "period_start": None,
                "value": Decimal(value),
            }
        )
        for metric, value in values.items()
    )
    current = base.model_copy(update={"facts": facts})
    results = obligation_checks(current)
    assert results[-1].status == "unavailable"
    total = facts[1].model_copy(
        update={"fact_id": "total", "metric": "Total Borrowings", "value": Decimal(100)}
    )
    results = obligation_checks(current.model_copy(update={"facts": (*facts, total)}))
    assert results[-1].status == "pass"
    assert results[-1].result == Decimal(95)


def test_cash_checks_keep_unclassified_equipment_payments_unavailable():
    from decimal import Decimal

    from tests.test_evidence_validation import package
    from tradingagents.agents.evidence_validation import cash_flow_checks

    base = package()
    values = {
        "Operating Cash Flow": 100,
        "Capital Expenditure": 20,
        "Software Development Payments": 5,
        "Finance Lease Principal Payments": 3,
        "Equipment on Lease Payments": 7,
    }
    facts = [
        base.facts[0].model_copy(
            update={"fact_id": metric, "metric": metric, "value": Decimal(value)}
        )
        for metric, value in values.items()
    ]
    facts.append(
        base.facts[0].model_copy(
            update={
                "fact_id": "assets",
                "metric": "Total Assets",
                "period_start": None,
                "value": Decimal(1000),
            }
        )
    )
    current = base.model_copy(update={"facts": tuple(facts)})
    results, check, warnings = cash_flow_checks(current)
    assert results[0].result == Decimal(75)
    assert check["status"] == "unavailable"
    classified = facts[0].model_copy(
        update={
            "fact_id": "equipment-principal",
            "metric": "Equipment Financing Principal Payments",
            "value": Decimal(7),
        }
    )
    results, check, warnings = cash_flow_checks(
        current.model_copy(update={"facts": (*facts, classified)})
    )
    assert check["status"] == "pass"
    assert results[1].result == Decimal(65)


def test_optional_software_gap_does_not_invent_zero_or_block_known_zero_financing():
    from decimal import Decimal

    from tests.test_evidence_validation import package
    from tradingagents.agents.evidence_validation import cash_flow_checks

    base = package()
    values = {
        "Operating Cash Flow": 100,
        "Capital Expenditure": 20,
        "Finance Lease Principal Payments": 0,
        "Equipment Financing Principal Payments": 0,
    }
    facts = [
        base.facts[0].model_copy(
            update={"fact_id": metric, "metric": metric, "value": Decimal(value)}
        )
        for metric, value in values.items()
    ]
    facts.append(
        base.facts[0].model_copy(
            update={
                "fact_id": "assets",
                "metric": "Total Assets",
                "period_start": None,
                "value": Decimal(1000),
            }
        )
    )
    results, check, warnings = cash_flow_checks(base.model_copy(update={"facts": tuple(facts)}))
    assert check["status"] == "pass"
    assert warnings
    assert all("Software" not in ident for ident in results[0].input_fact_ids)


def complete_evidence():
    """Synthetic complete sources; not actual DOCN primary-document proof."""
    from datetime import date
    from decimal import Decimal

    from tests.test_evidence_validation import package as base_package
    from tests.test_filing_facts import EQUITY, package as filing_package

    docs = filing_package(EQUITY)
    base = base_package()
    template = base.facts[0].model_copy(update={"cik": docs.cik})
    instant = {
        "Total Assets": 1200000000,
        "Total Liabilities": 214447000,
        "Stockholders Equity": 985553000,
        "Total Borrowings": 100000000,
        "Cash and Equivalents": 20000000,
        "Finance Lease Liabilities": 5000000,
        "Equipment Financing Obligations": 3000000,
        "Operating Lease Liabilities": 7000000,
    }
    flows = {
        "Revenue": 234000000,
        "Net Income": 30000000,
        "Operating Cash Flow": 100000000,
        "Capital Expenditure": 20000000,
        "Software Development Payments": 5000000,
        "Finance Lease Principal Payments": 3000000,
        "Equipment Financing Principal Payments": 7000000,
    }
    facts = [
        template.model_copy(
            update={
                "fact_id": metric,
                "metric": metric,
                "period_start": None,
                "value": Decimal(value),
            }
        )
        for metric, value in instant.items()
    ]
    facts += [
        template.model_copy(
            update={
                "fact_id": metric,
                "metric": metric,
                "period_start": date(2026, 1, 1),
                "value": Decimal(value),
            }
        )
        for metric, value in flows.items()
    ]
    return base.model_copy(
        update={
            "cik": docs.cik,
            "facts": tuple(facts),
            "sources": tuple(s.model_copy(update={"cik": docs.cik}) for s in base.sources),
        }
    ), docs


def test_complete_accounting_path_replaces_unvalidated_prose_before_debate():
    import json

    from tradingagents.agents.evidence_validation import assess_financial_package

    facts, docs = complete_evidence()
    revenue = next(f for f in facts.facts if f.metric == "Revenue")
    row = {
        "kind": revenue.origin,
        "fact_id": revenue.fact_id,
        "metric": revenue.metric,
        "value": str(revenue.value),
        "unit": revenue.unit,
        "period_start": str(revenue.period_start),
        "period_end": str(revenue.period_end),
    }
    fence = chr(96) * 3
    raw = (
        "Revenue is a trillion dollars.\n"
        + fence
        + "financial_claims\n"
        + json.dumps([row])
        + "\n"
        + fence
    )
    result = assess_financial_package({"fundamentals_report": raw}, facts, docs)
    assert result["evidence_quality"]["status"] == "limited"  # no optional KPI/guidance extraction
    assert "final_rating" not in result
    assert "trillion" not in result["fundamentals_report"]
    assert result["financial_claim_validation"]["raw_report"] == raw
    assert "ocf_less_enumerated_cash_capex_v1" in result["canonical_financial_context"]
    assert "75000000" in result["canonical_financial_context"]


def test_downstream_context_receives_canonical_values_directly():
    from tradingagents.agents.context import get_instrument_context_from_state

    result = get_instrument_context_from_state(
        {
            "company_of_interest": "DOCN",
            "instrument_context": "Issuer DOCN",
            "canonical_financial_context": "Checked OCF: 100 USD",
        }
    )
    assert "Issuer DOCN" in result and "Checked OCF: 100 USD" in result


def test_earnings_bridge_never_substitutes_net_income_for_diluted_numerator():
    from decimal import Decimal

    from tests.test_evidence_validation import package
    from tradingagents.agents.evidence_validation import earnings_checks

    base = package()
    values = [
        ("Net Income", "30", "USD"),
        ("Weighted Average Diluted Shares", "100", "shares"),
        ("Diluted EPS", "0.3", "USD/shares"),
    ]
    facts = [
        base.facts[0].model_copy(
            update={"fact_id": metric, "metric": metric, "value": Decimal(value), "unit": unit}
        )
        for metric, value, unit in values
    ]
    results = earnings_checks(base.model_copy(update={"facts": tuple(facts)}))
    assert results[-1].status == "unavailable"
    numerator = facts[0].model_copy(
        update={"fact_id": "Diluted Earnings Numerator", "metric": "Diluted Earnings Numerator"}
    )
    results = earnings_checks(base.model_copy(update={"facts": (*facts, numerator)}))
    assert results[-1].status == "pass"
    assert results[-1].result == Decimal("0.3")
    wrong = numerator.model_copy(update={"value": Decimal("40")})
    result = earnings_checks(base.model_copy(update={"facts": (*facts, wrong)}))[-1]
    assert result.status == "unavailable"  # precision not asserted by model or inferred from zeroes
    assert result.result == Decimal("0.4")


def test_complete_synthetic_sources_reach_decision_through_real_graph_nodes(monkeypatch):
    import json

    from langchain_core.messages import AIMessage

    from tests.test_graph_end_to_end import ScriptedModel
    from tradingagents.dataflows.vendors import sec_documents, sec_edgar
    from tradingagents.graph import setup
    from tradingagents.graph.conditional_logic import ConditionalLogic
    from tradingagents.graph.propagation import Propagator

    facts, docs = complete_evidence()
    revenue = next(f for f in facts.facts if f.metric == "Revenue")
    row = {
        "kind": revenue.origin,
        "fact_id": revenue.fact_id,
        "metric": revenue.metric,
        "value": str(revenue.value),
        "unit": revenue.unit,
        "period_start": str(revenue.period_start),
        "period_end": str(revenue.period_end),
    }
    fence = chr(96) * 3
    raw = (
        "Incorrect unvalidated trillion-dollar claim.\n"
        + fence
        + "financial_claims\n"
        + json.dumps([row])
        + "\n"
        + fence
    )
    monkeypatch.setattr(sec_edgar, "cik_for", lambda ticker: facts.cik)
    monkeypatch.setattr(sec_edgar, "get_financial_evidence", lambda *args: facts)
    monkeypatch.setattr(sec_documents, "get_filing_evidence", lambda *args: docs)
    monkeypatch.setattr(
        setup,
        "create_fundamentals_analyst",
        lambda llm: (
            lambda state: {"messages": [AIMessage(content=raw)], "fundamentals_report": raw}
        ),
    )
    model = ScriptedModel()
    graph = (
        setup.GraphSetup(model, model, ConditionalLogic(), 1)
        .setup_graph(["fundamentals"])
        .compile()
    )
    result = graph.invoke(Propagator().create_initial_state("DOCN", "2026-10-19"))
    assert result["evidence_quality"]["status"] == "limited"
    assert result["final_rating"] == "Overweight"
    assert result["investment_plan"] and result["trader_investment_plan"]
    assert "trillion-dollar" not in result["fundamentals_report"]
    assert result["financial_claim_validation"]["raw_report"] == raw
    assert result["canonical_financial_context"]


def test_verified_adjusted_table_reaches_calculations_with_its_own_basis():
    from tests.test_filing_facts import ADJUSTED, package as filing_package
    from tradingagents.agents.evidence_validation import filing_accounting_evidence
    from tradingagents.dataflows.financial_evidence import EvidencePackage

    docs = filing_package(ADJUSTED, section="Non-GAAP reconciliation")
    base = EvidencePackage(cik=docs.cik, as_of=docs.as_of)
    _, calculations, _ = filing_accounting_evidence(base, docs)
    adjusted = [
        c for c in calculations if c.method == "gaap_plus_disclosed_management_adjustments_v1"
    ]
    assert len(adjusted) == 2 and all(c.status == "pass" for c in adjusted)
    assert {str(c.result) for c in adjusted} == {"122000", "90000"}
    bad = filing_package(
        ADJUSTED.replace("Adjusted net income | 122", "Adjusted net income | 150"),
        section="Non-GAAP reconciliation",
    )
    _, calculations, _ = filing_accounting_evidence(base, bad)
    assert any(c.status == "fail" for c in calculations)
