"""Material financial claims cannot replace canonical source facts."""

import json

from tradingagents.agents.evidence_validation import validate_financial_claims
from tradingagents.dataflows.financial_evidence import EvidencePackage, FinancialFact, SourceRecord

FENCE = chr(96) * 3


def package():
    source = SourceRecord(
        source_id="s",
        cik="1",
        url="https://data.sec.gov/example",
        filed_date="2026-08-04",
        retrieved_at="2026-11-04T00:00:00Z",
        content_hash="a" * 64,
        locator="Revenue",
        form="10-Q",
    )
    fact = FinancialFact(
        fact_id="f",
        metric="Revenue",
        value="234000000",
        unit="USD",
        cik="1",
        period_start="2026-04-01",
        period_end="2026-06-30",
        as_of="2026-10-19",
        source_ids=("s",),
        locator="Revenue",
    )
    return EvidencePackage(cik="1", as_of="2026-10-19", sources=(source,), facts=(fact,))


def report(**changes):
    claim = {
        "kind": "reported",
        "fact_id": "f",
        "metric": "Revenue",
        "value": "234000000",
        "unit": "USD",
        "period_start": "2026-04-01",
        "period_end": "2026-06-30",
    }
    claim.update(changes)
    return (
        "Revenue is a trillion dollars.\n"
        + FENCE
        + "financial_claims\n"
        + json.dumps([claim])
        + "\n"
        + FENCE
    )


def test_material_claims_render_from_canonical_facts_not_raw_prose():
    result = validate_financial_claims(report(), package())
    assert result["status"] == "pass"
    assert "234000000" in result["canonical_summary"]
    assert "trillion" not in result["canonical_summary"]
    assert result["raw_report"].startswith("Revenue is a trillion")
    assert result["fact_ids"] == ["f"]


def test_changed_value_metric_unit_period_or_reference_is_rejected():
    for changes in [
        {"value": "235000000"},
        {"metric": "AI product revenue"},
        {"unit": "EUR"},
        {"period_end": "2026-09-30"},
        {"fact_id": "missing"},
        {"kind": "derived"},
    ]:
        result = validate_financial_claims(report(**changes), package())
        assert result["status"] == "unavailable"
        assert result["reasons"]


def test_missing_or_duplicate_extraction_does_not_pass():
    for raw in [
        "Unstructured report",
        report() + report(),
        FENCE + "financial_claims\n[]\n" + FENCE,
        FENCE + "financial_claims\n{}\n" + FENCE,
    ]:
        assert validate_financial_claims(raw, package())["status"] == "unavailable"


def test_hypotheses_never_become_facts():
    raw = (
        FENCE
        + 'financial_claims\n[{"kind":"hypothesis","text":"A conversion explains the equity increase"}]\n'
        + FENCE
    )
    result = validate_financial_claims(raw, package())
    assert result["status"] == "unavailable"
    assert result["hypotheses"] == ["A conversion explains the equity increase"]
    assert "conversion" not in result["canonical_summary"]


def test_claim_prompt_requires_exact_source_references():
    from tradingagents.agents.analysts.fundamentals_analyst import FINANCIAL_CLAIM_EXTRACTION

    for field in ("financial_claims", "fact_id", "period_start", "period_end", "hypothesis", "32"):
        assert field in FINANCIAL_CLAIM_EXTRACTION
    # Canonical TTM facts can be in the shared brief rather than the raw tool.
    # The claim schema calls source `origin` by a different field name, `kind`.
    assert "kind must exactly match the canonical fact's origin" in FINANCIAL_CLAIM_EXTRACTION
    assert "shared source brief" in FINANCIAL_CLAIM_EXTRACTION
    assert "TTM" in FINANCIAL_CLAIM_EXTRACTION
    assert "quarter inputs are reported" in FINANCIAL_CLAIM_EXTRACTION


def test_derived_lineage_recomputes_value_and_rejects_cycles():
    from tradingagents.agents.evidence_validation import validate_calculation_lineage
    from tradingagents.dataflows.financial_evidence import derive_quarter

    base = package()
    annual = base.facts[0].model_copy(
        update={
            "fact_id": "annual",
            "period_start": __import__("datetime").date(2025, 7, 1),
            "period_end": __import__("datetime").date(2026, 6, 30),
            "value": __import__("decimal").Decimal(100),
        }
    )
    ytd = annual.model_copy(
        update={
            "fact_id": "ytd",
            "period_end": __import__("datetime").date(2026, 3, 31),
            "value": __import__("decimal").Decimal(75),
        }
    )
    derived = derive_quarter(annual, ytd)
    good = base.model_copy(update={"facts": (annual, ytd, derived)})
    assert validate_calculation_lineage(good) == []
    wrong = derived.model_copy(update={"value": __import__("decimal").Decimal(99)})
    assert validate_calculation_lineage(base.model_copy(update={"facts": (annual, ytd, wrong)}))
    cyclic_a = derived.model_copy(update={"fact_id": "a", "input_fact_ids": ("b", "annual")})
    cyclic_b = derived.model_copy(update={"fact_id": "b", "input_fact_ids": ("a", "annual")})
    assert validate_calculation_lineage(
        base.model_copy(update={"facts": (annual, cyclic_a, cyclic_b)})
    )


def test_latest_balance_check_cannot_mix_statement_dates():
    from datetime import date
    from decimal import Decimal

    from tradingagents.agents.evidence_validation import latest_balance_check

    base = package()
    records = tuple(
        base.facts[0].model_copy(
            update={
                "fact_id": metric,
                "metric": metric,
                "period_start": None,
                "value": Decimal(value),
            }
        )
        for metric, value in [
            ("Total Assets", "100"),
            ("Total Liabilities", "60"),
            ("Stockholders Equity", "40"),
        ]
    )
    complete = base.model_copy(update={"facts": records})
    assert latest_balance_check(complete).status == "pass"
    mixed = complete.model_copy(
        update={
            "facts": (*records[:2], records[2].model_copy(update={"period_end": date(2026, 3, 31)}))
        }
    )
    assert latest_balance_check(mixed).status == "unavailable"
    assert latest_balance_check(base).status == "unavailable"


def test_quality_requires_all_critical_checks_but_optional_gaps_only_warn():
    from tradingagents.agents.evidence_validation import REQUIRED_FINANCIAL_CHECKS, evidence_quality

    checks = [
        {"code": code, "status": "pass", "message": "checked"} for code in REQUIRED_FINANCIAL_CHECKS
    ]
    assert evidence_quality(checks)["status"] == "sufficient"
    limited = evidence_quality(
        [
            *checks,
            {
                "code": "optional_nrr",
                "status": "unavailable",
                "message": "Not disclosed in selected sources",
            },
        ]
    )
    assert limited["status"] == "limited"
    assert evidence_quality(checks[:-1])["status"] == "insufficient"
    assert (
        evidence_quality(
            [{**c, "status": "fail"} if c["code"] == "equity_movement" else c for c in checks]
        )["status"]
        == "insufficient"
    )


def test_review_terminal_state_preserves_research_and_clears_actionable_fields():
    from tradingagents.agents.evidence_validation import review_terminal_state

    quality = {
        "status": "insufficient",
        "checks": [
            {
                "code": "equity_movement",
                "status": "unavailable",
                "message": "Equity movement source missing",
            }
        ],
    }
    state = review_terminal_state(quality)
    assert state["final_rating"] == "REVIEW"
    assert "Equity movement source missing" in state["final_trade_decision"]
    for field in ("investment_plan", "trader_investment_plan"):
        assert state[field] == ""
    assert state["investment_debate_state"]["history"] == ""
    assert state["risk_debate_state"]["history"] == ""
    assert "fundamentals_report" not in state  # merged graph state preserves research


def test_core_statements_require_current_revenue_earnings_and_cash_flow():
    from decimal import Decimal

    from tradingagents.agents.evidence_validation import core_statement_check

    base = package()
    records = list(base.facts)
    records.extend(
        base.facts[0].model_copy(
            update={"fact_id": metric, "metric": metric, "value": Decimal(value)}
        )
        for metric, value in [("Net Income", "10"), ("Operating Cash Flow", "20")]
    )
    records.extend(
        base.facts[0].model_copy(
            update={
                "fact_id": metric,
                "metric": metric,
                "period_start": None,
                "value": Decimal(value),
            }
        )
        for metric, value in [
            ("Total Assets", "100"),
            ("Total Liabilities", "60"),
            ("Stockholders Equity", "40"),
        ]
    )
    complete = base.model_copy(update={"facts": tuple(records)})
    assert core_statement_check(complete)["status"] == "pass"
    missing = complete.model_copy(
        update={"facts": tuple(f for f in records if f.metric != "Operating Cash Flow")}
    )
    assert core_statement_check(missing)["status"] == "unavailable"
    stale = complete.model_copy(
        update={
            "facts": tuple(
                f.model_copy(update={"period_end": __import__("datetime").date(2026, 3, 31)})
                if f.metric == "Operating Cash Flow"
                else f
                for f in records
            )
        }
    )
    assert core_statement_check(stale)["status"] == "unavailable"


def test_identical_balance_facts_from_two_sources_do_not_create_false_ambiguity():
    from decimal import Decimal

    from tradingagents.agents.evidence_validation import latest_balance_check

    base = package()
    records = tuple(
        base.facts[0].model_copy(
            update={
                "fact_id": metric,
                "metric": metric,
                "period_start": None,
                "value": Decimal(value),
            }
        )
        for metric, value in [
            ("Total Assets", "100"),
            ("Total Liabilities", "60"),
            ("Stockholders Equity", "40"),
        ]
    )
    duplicate = records[-1].model_copy(update={"fact_id": "filing-equity"})
    assert (
        latest_balance_check(base.model_copy(update={"facts": (*records, duplicate)})).status
        == "pass"
    )
    conflict = duplicate.model_copy(update={"value": Decimal(41)})
    assert (
        latest_balance_check(base.model_copy(update={"facts": (*records, conflict)})).status
        == "unavailable"
    )


def rounded_equity_fixture(delta=400, *, different_vintage=False):
    from decimal import Decimal

    from tests.test_filing_facts import EQUITY, package as filing_package
    from tradingagents.agents.evidence_validation import filing_accounting_evidence

    disclosures = filing_package(EQUITY)
    empty = EvidencePackage(cik=disclosures.cik, as_of=disclosures.as_of)
    evidence, _, extraction = filing_accounting_evidence(empty, disclosures)
    equity = next(
        f
        for f in evidence.facts
        if f.metric == "Stockholders Equity" and str(f.period_end) == "2026-06-30"
    )
    duplicate = equity.model_copy(
        update={"fact_id": "companyfacts-value", "value": equity.value + Decimal(delta)}
    )
    sources = evidence.sources
    if different_vintage:
        from datetime import date

        old = next(s for s in sources if s.source_id == equity.source_ids[0])
        changed = old.model_copy(
            update={
                "source_id": "different-filing",
                "filed_date": date(2026, 9, 1),
                "accession": "0001582961-26-000002",
            }
        )
        sources = (*sources, changed)
        duplicate = duplicate.model_copy(update={"source_ids": (changed.source_id,)})
    return (
        evidence.model_copy(update={"facts": (*evidence.facts, duplicate), "sources": sources}),
        extraction.rounding_quantum_by_fact,
        equity,
    )


def test_same_vintage_table_rounding_is_not_a_reported_fact_conflict():
    from tradingagents.agents.evidence_validation import reported_fact_conflicts

    evidence, precision, equity = rounded_equity_fixture()
    assert precision[equity.fact_id] == 1000
    assert reported_fact_conflicts(evidence, precision) == []
    assert len(evidence.facts) > 1  # original exact source facts remain intact


def test_excess_difference_missing_precision_and_different_vintage_stay_conflicts():
    from tradingagents.agents.evidence_validation import reported_fact_conflicts

    evidence, precision, _ = rounded_equity_fixture(501)
    assert reported_fact_conflicts(evidence, precision)
    evidence, precision, _ = rounded_equity_fixture(400)
    assert reported_fact_conflicts(evidence, {})
    evidence, precision, _ = rounded_equity_fixture(400, different_vintage=True)
    assert reported_fact_conflicts(evidence, precision)


def test_rounded_duplicate_balance_selector_applies_only_known_source_allowance():
    from decimal import Decimal

    from tradingagents.agents.evidence_validation import latest_balance_check

    evidence, precision, equity = rounded_equity_fixture()
    a = equity.model_copy(
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
    evidence = evidence.model_copy(update={"facts": (*evidence.facts, a, liabilities)})
    before = evidence.model_dump_json()
    result = latest_balance_check(evidence, precision)
    assert result.status == "pass" and result.tolerance == Decimal(500)
    assert equity.fact_id in result.input_fact_ids
    assert evidence.model_dump_json() == before
    assert latest_balance_check(evidence).status == "unavailable"


def test_rounding_never_merges_different_unit_basis_or_period():
    from datetime import date

    from tradingagents.agents.evidence_validation import _instant_at

    evidence, precision, equity = rounded_equity_fixture()
    for update in [{"unit": "EUR"}, {"basis": "management-adjusted"}]:
        changed = evidence.facts[-1].model_copy(update=update)
        mixed = evidence.model_copy(update={"facts": (*evidence.facts[:-1], changed)})
        assert _instant_at(mixed, "Stockholders Equity", equity.period_end, precision) is None
    changed = evidence.facts[-1].model_copy(update={"period_end": date(2026, 3, 31)})
    separate = evidence.model_copy(update={"facts": (*evidence.facts[:-1], changed)})
    selected = _instant_at(separate, "Stockholders Equity", equity.period_end, precision)
    assert selected.fact_id == equity.fact_id


def test_duration_selector_uses_the_same_rounding_policy_as_instant_selector():
    from decimal import Decimal

    from tests.test_filing_facts import EQUITY, package as filing_package
    from tradingagents.agents.evidence_validation import _duration_at, filing_accounting_evidence

    disclosures = filing_package(EQUITY)
    empty = EvidencePackage(cik=disclosures.cik, as_of=disclosures.as_of)
    evidence, _, extraction = filing_accounting_evidence(empty, disclosures)
    income = next(fact for fact in evidence.facts if fact.metric == "Net Income")
    other = income.model_copy(
        update={"fact_id": "companyfacts-income", "value": income.value + Decimal(400)}
    )
    current = evidence.model_copy(update={"facts": (*evidence.facts, other)})
    assert _duration_at(current, "Net Income", income.period_start, income.period_end) is None
    chosen = _duration_at(
        current,
        "Net Income",
        income.period_start,
        income.period_end,
        extraction.rounding_quantum_by_fact,
    )
    assert chosen.fact_id == income.fact_id


def test_rounded_table_cannot_hide_two_disagreeing_unknown_precision_sources():
    from decimal import Decimal

    from tradingagents.agents.evidence_validation import reported_fact_conflicts

    evidence, precision, equity = rounded_equity_fixture(400)
    another = equity.model_copy(
        update={"fact_id": "another-companyfacts-value", "value": equity.value + Decimal(300)}
    )
    evidence = evidence.model_copy(update={"facts": (*evidence.facts, another)})
    assert reported_fact_conflicts(evidence, precision)
    for invalid in (Decimal("NaN"), Decimal("-1000")):
        assert reported_fact_conflicts(evidence, {equity.fact_id: invalid})


def test_extraction_prompts_show_the_literal_parser_fences():
    from tradingagents.agents.analysts.fundamentals_analyst import (
        DISCLOSURE_EXTRACTION,
        FINANCIAL_CLAIM_EXTRACTION,
    )

    # A real model returned two valid JSON arrays under generic json fences.
    # The parser deliberately requires distinct names; the prompt must show them.
    fence = chr(96) * 3
    for prompt, label in (
        (FINANCIAL_CLAIM_EXTRACTION, "financial_claims"),
        (DISCLOSURE_EXTRACTION, "disclosures"),
    ):
        assert fence + label + '\n' in prompt
        assert "generic" in prompt
