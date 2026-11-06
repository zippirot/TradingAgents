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
    assert result["advisory_audit"]["status"] == "unavailable"
    assert "not run" in result["advisory_audit"]["error"]
    assert result["advisory_audit"]["submitted_count"] == 0


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
    # Equal acquisition and principal amounts do not establish the same cash scope.
    assert check["status"] == "unavailable"
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


def test_downstream_narrative_is_labeled_bounded_and_extraction_free():
    from tradingagents.agents.context import get_instrument_context_from_state

    state = {
        "company_of_interest": "DOCN",
        "canonical_financial_context": "Checked revenue: 100 USD",
        "financial_claim_validation": {
            "raw_report": (
                "Revenue is a trillion dollars; investigate AI retention.\n"
                '```financial_claims\n[{"fact_id":"untrusted-id"}]\n```\n'
                "Research context. " * 1000
            ),
        },
    }
    import copy

    original = copy.deepcopy(state)
    context = get_instrument_context_from_state(state)
    assert "Checked revenue: 100 USD" in context
    assert "Analyst research — unvalidated interpretation" in context
    assert "investigate AI retention" in context
    assert "untrusted-id" not in context
    assert "truncated" in context.lower()
    assert len(context) < 7500
    assert state == original


def test_unterminated_extraction_cannot_become_research_prose():
    from tradingagents.agents.context import get_instrument_context_from_state

    context = get_instrument_context_from_state({
        "company_of_interest": "DOCN",
        "canonical_financial_context": "Checked revenue: 100 USD",
        "financial_claim_validation": {
            "raw_report": 'Research hypothesis.\n```valuation_scenarios\n{"secret_claim":999}',
        },
    })
    assert "Research hypothesis." in context
    assert "secret_claim" not in context


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


def test_gate_uses_trusted_filing_quantum_for_same_vintage_duplicate():
    from decimal import Decimal

    from tests.test_evidence_validation import rounded_equity_fixture
    from tests.test_filing_facts import EQUITY, package as filing_package
    from tradingagents.agents.evidence_validation import assess_financial_package

    evidence, _, equity = rounded_equity_fixture()
    assets = equity.model_copy(
        update={
            "fact_id": "assets",
            "metric": "Total Assets",
            "value": equity.value + Decimal(100000400),
        }
    )
    liabilities = equity.model_copy(
        update={
            "fact_id": "liabilities",
            "metric": "Total Liabilities",
            "value": Decimal(100000000),
        }
    )
    evidence = evidence.model_copy(update={"facts": (*evidence.facts, assets, liabilities)})
    result = assess_financial_package(
        {"fundamentals_report": "Raw research"}, evidence, filing_package(EQUITY)
    )
    checks = {check["code"]: check for check in result["evidence_quality"]["checks"]}
    assert checks["source_integrity"]["status"] == "pass"
    assert checks["balance_sheet"]["status"] == "pass"
    assert any(
        fact["fact_id"] == "companyfacts-value" for fact in result["financial_evidence"]["facts"]
    )
    assert any(fact["fact_id"] == equity.fact_id for fact in result["financial_evidence"]["facts"])


def test_obligation_component_comparison_uses_same_filing_rounding_not_exact_equality():
    from decimal import Decimal

    from tests.test_evidence_validation import rounded_equity_fixture
    from tradingagents.agents.evidence_validation import obligation_checks

    base, precision, template = rounded_equity_fixture()
    # Synthetic categories share the parsed fixture's known thousands precision
    # on the total; unrounded comparison inputs receive no extra allowance.
    values = {
        "Total Assets": Decimal(1000000),
        "Total Borrowings": Decimal(100000),
        "Long-term Borrowings (including current)": Decimal(90000),
        "Short-term Borrowings": Decimal(10400),
        "Finance Lease Liabilities": Decimal(10000),
        "Equipment Financing Obligations": Decimal(5000),
        "Operating Lease Liabilities": Decimal(7000),
        "Cash and Equivalents": Decimal(20000),
    }
    facts = tuple(
        template.model_copy(update={"fact_id": metric, "metric": metric, "value": value})
        for metric, value in values.items()
    )
    current = base.model_copy(update={"facts": facts})
    quantum = {"Total Borrowings": precision[template.fact_id]}
    assert obligation_checks(current)[-1].status == "unavailable"
    assert obligation_checks(current, quantum)[-1].status == "pass"
    bad = next(fact for fact in facts if fact.metric == "Short-term Borrowings").model_copy(
        update={"value": Decimal(10501)}
    )
    broken = current.model_copy(
        update={"facts": tuple(bad if fact.fact_id == bad.fact_id else fact for fact in facts)}
    )
    assert obligation_checks(broken, quantum)[-1].status == "unavailable"


def test_source_scoped_combined_principal_replays_actual_filing_before_coverage():
    import json
    from decimal import Decimal
    from pathlib import Path

    from tradingagents.agents.evidence_validation import (
        cash_flow_checks,
        filing_accounting_evidence,
    )
    from tradingagents.dataflows.financial_evidence import EvidencePackage
    from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

    recorded = json.loads(Path("tests/fixtures/docn_2026q3/filing_tables.json").read_text())
    disclosures = DisclosurePackage.model_validate(recorded["disclosures"])
    empty = EvidencePackage(cik=disclosures.cik, as_of=disclosures.as_of)
    merged, _, extraction = filing_accounting_evidence(empty, disclosures)
    combined = next(
        f
        for f in merged.facts
        if f.metric == "Finance Lease and Financing Arrangement Principal Payments"
        and f.origin == "derived"
        and str(f.period_end) == "2026-09-30"
    )
    # Synthetic OCF/capex support isolates the recorded principal scope, not a
    # claim that these two amounts came from the recorded table excerpt.
    additions = tuple(
        combined.model_copy(
            update={
                "fact_id": metric,
                "metric": metric,
                "value": Decimal(value),
                "period_start": None if metric == "Total Assets" else combined.period_start,
            }
        )
        for metric, value in {
            "Total Assets": 1000000000,
            "Operating Cash Flow": 100000000,
            "Capital Expenditure": 20000000,
        }.items()
    )
    replaced_metrics = {f.metric for f in additions}
    current = merged.model_copy(
        update={
            "facts": (
                *(f for f in merged.facts if f.metric not in replaced_metrics),
                *additions,
            )
        }
    )
    results, check, _ = cash_flow_checks(current, disclosures, extraction.rounding_quantum_by_fact)
    assert check["status"] == "pass"
    assert results[1].result == Decimal(40105000)
    assert combined.fact_id in results[1].input_fact_ids
    _, absent, _ = cash_flow_checks(current)
    assert absent["status"] == "unavailable"
    doc = disclosures.documents[0]
    altered = disclosures.model_copy(
        update={
            "documents": (
                doc.model_copy(
                    update={
                        "blocks": tuple(
                            b.model_copy(
                                update={
                                    "text": b.text.replace(
                                        "for data center equipment", "for unrelated transactions"
                                    )
                                }
                            )
                            for b in doc.blocks
                        )
                    }
                ),
            )
        }
    )
    _, tampered, _ = cash_flow_checks(current, altered)
    assert tampered["status"] == "unavailable"
    wrong_amount = disclosures.model_copy(
        update={
            "documents": (
                doc.model_copy(
                    update={
                        "blocks": tuple(
                            b.model_copy(
                                update={"text": b.text.replace("$39.9 million", "$123.4 million")}
                            )
                            for b in doc.blocks
                        )
                    }
                ),
            )
        }
    )
    assert cash_flow_checks(current, wrong_amount)[1]["status"] == "unavailable"


def test_recorded_financed_acquisition_is_separate_from_principal_and_replays_scope():
    import json
    from decimal import Decimal
    from pathlib import Path

    from tradingagents.agents.evidence_validation import (
        cash_flow_checks,
        filing_accounting_evidence,
    )
    from tradingagents.dataflows.financial_evidence import EvidencePackage
    from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

    recorded = json.loads(Path("tests/fixtures/docn_2026q3/filing_tables.json").read_text())
    disclosures = DisclosurePackage.model_validate(recorded["disclosures"])
    empty = EvidencePackage(cik=disclosures.cik, as_of=disclosures.as_of)
    merged, _, extraction = filing_accounting_evidence(empty, disclosures)
    acquisition = next(
        f
        for f in merged.facts
        if f.metric == "Equipment Financing Acquisition Payments"
        and str(f.period_end) == "2026-09-30"
    )
    # Synthetic companion facts isolate classification of actual gross cash rows.
    additions = tuple(
        acquisition.model_copy(
            update={
                "fact_id": metric,
                "metric": metric,
                "value": Decimal(value),
                "period_start": None if metric == "Total Assets" else acquisition.period_start,
            }
        )
        for metric, value in {
            "Total Assets": 1000000000,
            "Operating Cash Flow": 100000000,
            "Capital Expenditure": 20000000,
            "Equipment on Lease Payments": 75143000,
        }.items()
    )
    replaced_metrics = {f.metric for f in additions}
    current = merged.model_copy(
        update={
            "facts": (
                *(f for f in merged.facts if f.metric not in replaced_metrics),
                *additions,
            )
        }
    )
    results, check, _ = cash_flow_checks(current, disclosures, extraction.rounding_quantum_by_fact)
    assert check["status"] == "pass"
    assert results[0].result == Decimal(80000000)
    assert results[1].result == Decimal(40105000)
    assert results[2].status == "pass" and results[2].residual == 0
    assert acquisition.fact_id in results[2].input_fact_ids
    assert acquisition.fact_id not in results[1].input_fact_ids
    no_proceeds = current.model_copy(
        update={
            "facts": tuple(f for f in current.facts if f.metric != "Equipment Financing Proceeds")
        }
    )
    assert cash_flow_checks(no_proceeds, disclosures)[1]["status"] == "unavailable"
    assert cash_flow_checks(current, None)[1]["status"] == "unavailable"
    conflicting = current.model_copy(
        update={
            "facts": tuple(
                f.model_copy(update={"value": Decimal(75100000)})
                if f.metric == "Equipment on Lease Payments"
                else f
                for f in current.facts
            )
        }
    )
    assert cash_flow_checks(conflicting, disclosures)[1]["status"] == "unavailable"
    old_source = current.sources[0].model_copy(
        update={
            "source_id": "older-acquisition-source",
            "accession": "0001582961-25-000001",
        }
    )
    older = current.model_copy(
        update={
            "sources": (*current.sources, old_source),
            "facts": tuple(
                f.model_copy(update={"source_ids": (old_source.source_id,)})
                if f.metric == "Equipment on Lease Payments"
                else f
                for f in current.facts
            ),
        }
    )
    assert cash_flow_checks(older, disclosures)[1]["status"] == "unavailable"


def test_cash_period_prefers_reported_statement_over_derived_quarter_and_ttm():
    from datetime import date
    from decimal import Decimal

    from tests.test_evidence_validation import package
    from tradingagents.agents.evidence_validation import cash_flow_checks

    base = package()
    template = base.facts[0]
    end = date(2026, 9, 30)
    start = date(2026, 1, 1)
    facts = tuple(
        template.model_copy(
            update={
                "fact_id": metric,
                "metric": metric,
                "value": Decimal(value),
                "period_start": None if metric == "Total Assets" else start,
                "period_end": end,
                "origin": "reported",
                "input_fact_ids": (),
                "formula_id": None,
            }
        )
        for metric, value in {
            "Total Assets": 1000,
            "Operating Cash Flow": 100,
            "Capital Expenditure": 20,
            "Finance Lease Principal Payments": 0,
            "Equipment Financing Principal Payments": 0,
        }.items()
    )
    reported = next(f for f in facts if f.metric == "Operating Cash Flow")
    derived = tuple(
        reported.model_copy(
            update={
                "fact_id": key,
                "origin": "derived",
                "period_start": beginning,
                "value": Decimal(value),
                "input_fact_ids": (reported.fact_id,),
                "formula_id": formula,
            }
        )
        for key, beginning, value, formula in (
            ("quarter", date(2026, 7, 1), 40, "cumulative_difference_v1"),
            ("ttm", date(2025, 10, 1), 150, "four_quarter_sum_v1"),
        )
    )
    current = base.model_copy(update={"facts": (*facts, *derived)})
    results, check, _ = cash_flow_checks(current)
    assert check["status"] == "pass"
    assert results[0].result == 80
    assert results[0].input_fact_ids[0] == reported.fact_id
    assert len(current.facts) == len(facts) + 2  # supplemental facts remain untouched
    annual = current.model_copy(
        update={
            "facts": tuple(
                f.model_copy(update={"period_start": date(2025, 10, 1)})
                if f.origin == "reported" and f.period_start
                else f.model_copy(update={"value": reported.value})
                if f.fact_id == "ttm"
                else f
                for f in current.facts
            )
        }
    )
    annual_results, annual_check, _ = cash_flow_checks(annual)
    assert annual_check["status"] == "pass"
    assert annual_results[0].result == 80
