"""Banks and insurers reach a decision without a net-debt or capital-spending frame.

Wider-mix test, 2026-11-12: JPMorgan and Progressive stopped at the source checks. A bank files no
ordinary revenue, cash or capital-spending lines, and an insurer no unrestricted cash line; borrowings and
deposits fund a financial company's business, so "net debt" and "cash spending" do not describe it. The
user's decision: give them their own path. For a company recognised as financial from its own filing
tags, the obligation and cash-spending checks lower confidence when unavailable but do not stop the run,
and it is valued on earnings cases, which need neither.

Boundary: only a company whose filing carries a bank or insurer tag is treated this way; for every other
company the two checks stay required. A failure (a contradiction) still stops the run for anyone.
"""
from types import SimpleNamespace

from tradingagents.agents.evidence_validation import evidence_quality, financial_kind

PASSING = [{"code": code, "status": "pass", "message": "ok"} for code in (
    "source_integrity", "core_statements", "balance_sheet", "equity_movement", "disclosure_coverage", "material_claims")]
GAPS = [{"code": "obligation_perimeter", "status": "unavailable", "message": "unrestricted cash is not established"},
        {"code": "cash_flow_perimeter", "status": "unavailable", "message": "explicit complete cash spending coverage required"}]


def _package(*locators):
    return SimpleNamespace(facts=[SimpleNamespace(metric="x", locator=locator) for locator in locators])


def test_a_bank_or_an_insurer_is_recognised_from_its_own_filing_tags():
    assert financial_kind(_package("us-gaap/RevenuesNetOfInterestExpense/USD/2026-07-01/2026-09-30/2026-11-01")) == "bank"
    assert financial_kind(_package("us-gaap/Deposits/USD/instant/2026-09-30/2026-11-01")) == "bank"
    assert financial_kind(_package("us-gaap/PremiumsEarnedNet/USD/2026-07-01/2026-09-30/2026-11-01")) == "insurer"
    assert financial_kind(_package("us-gaap/Revenues/USD/2026-07-01/2026-09-30/2026-11-01")) is None
    assert financial_kind(_package()) is None


def test_for_a_financial_company_the_two_checks_lower_confidence_and_do_not_stop_the_run():
    stopped = evidence_quality([*PASSING, *GAPS])
    assert stopped["status"] == "insufficient"                      # an ordinary company: unchanged
    quality = evidence_quality([*PASSING, *GAPS], financial="bank")
    assert quality["status"] == "limited"
    text = " ".join(quality["warnings"])
    assert "financial company" in text and "Net debt" in text and "Capital spending" in text


def test_a_contradiction_still_stops_a_financial_company_and_other_checks_stay_required():
    failed = [*PASSING, {**GAPS[0], "status": "fail"}, GAPS[1]]
    assert evidence_quality(failed, financial="bank")["status"] == "insufficient"
    missing_core = [check for check in PASSING if check["code"] != "core_statements"] + [
        {"code": "core_statements", "status": "unavailable", "message": "Revenue missing"}, *GAPS]
    assert evidence_quality(missing_core, financial="insurer")["status"] == "insufficient"


def test_the_analyst_is_told_to_value_a_financial_company_on_earnings():
    from tradingagents.agents.analysts.fundamentals_analyst import SHARED_VALUATION_INPUTS
    assert "bank or an insurer" in SHARED_VALUATION_INPUTS and "earnings cases" in SHARED_VALUATION_INPUTS


def test_a_claim_naming_one_of_the_codes_own_long_fact_labels_is_not_malformed():
    """Progressive's first run stopped at REVIEW on "Claim 14: malformed fields": the analyst had copied the
    fact's own label, 'Equity Movement [tag | member | member]', 190 characters, and the claim allowed 160."""
    from tradingagents.agents.evidence_validation import FinancialClaim

    label = ("Equity Movement [us-gaap:OtherComprehensiveIncomeLossNetOfTax | "
             "us-gaap:AccumulatedOtherComprehensiveIncomeMember | us-gaap:AccumulatedOtherComprehensiveIncomeMember]")
    assert len(label) > 160
    claim = FinancialClaim.model_validate({"kind": "reported", "fact_id": "5" * 64, "metric": label, "value": "-2847000000",
                                           "unit": "USD", "period_start": "2026-01-01", "period_end": "2026-09-30"})
    assert claim.metric == label
