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
