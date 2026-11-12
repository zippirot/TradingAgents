"""An equity table the reader cannot tie out lowers the stated confidence; it no longer stops the run.

Eight of 31 large filers were sent to REVIEW for this alone, with revenue, cash, debt and shares all read.
The check is an integrity check on the books, not a valuation input. A failed check (a contradiction,
not an absence) still stops the run, and so does any other required check that is not passed.
"""
from tradingagents.agents.evidence_validation import REQUIRED_FINANCIAL_CHECKS, evidence_quality


def _checks(**changed):
    return [{"code": code, "status": changed.get(code, "pass"), "message": f"{code} message"}
            for code in REQUIRED_FINANCIAL_CHECKS]


def test_an_equity_table_that_is_not_tied_out_limits_the_evidence_and_says_so():
    quality = evidence_quality(_checks(equity_movement="unavailable"))
    assert quality["status"] == "limited"
    assert quality["warnings"] == ["Equity movement not tied out (confidence lowered, run continues): equity_movement message"]
    assert evidence_quality(_checks())["status"] == "sufficient"


def test_a_failed_equity_check_and_every_other_required_check_still_stop_the_run():
    assert evidence_quality(_checks(equity_movement="fail"))["status"] == "insufficient"
    for code in REQUIRED_FINANCIAL_CHECKS:
        if code != "equity_movement":
            assert evidence_quality(_checks(**{code: "unavailable"}))["status"] == "insufficient", code


def test_one_temporary_equity_balance_filed_under_two_tags_is_counted_once_in_the_balance_identity():
    # Tesla: redeemable noncontrolling interests of 54 appear under two tags; the identity holds exactly.
    from tests.test_face_liabilities import _fact, _package
    from tradingagents.agents.evidence_validation import latest_balance_check
    from tradingagents.dataflows.financial_evidence import TEMPORARY_EQUITY_METRICS, TOTAL_EQUITY

    first, second = sorted(TEMPORARY_EQUITY_METRICS)[:2]
    base = (_fact("Total Assets", 1575), _fact("Total Liabilities", 676), _fact("Stockholders Equity", 893),
            _fact(TOTAL_EQUITY, 898), _fact("Noncontrolling Interests", 5))
    assert latest_balance_check(_package(*base, _fact(first, 1), _fact(second, 1))).status == "pass"
    # Two different temporary balances are still not guessed at.
    assert latest_balance_check(_package(*base, _fact(first, 1), _fact(second, 2))).status != "pass"
