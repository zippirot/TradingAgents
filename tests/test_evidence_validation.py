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
