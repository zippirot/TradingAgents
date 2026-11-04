"""Recorded-source regression: malformed optional rows must not erase good rows."""
import json

from tests.test_disclosure_context import blocks_for, recorded_claim, recorded_package
from tradingagents.dataflows.disclosure_evidence import parse_disclosure_report


def report(rows):
    fence = chr(96) * 3
    return fence + "disclosures\n" + json.dumps(rows) + "\n" + fence


def test_one_malformed_record_preserves_valid_records_before_and_after():
    package = recorded_package()
    good = recorded_claim(package).model_dump(mode="json")
    bad = {**good, "value": "380,000"}
    cash = {
        "source_id": package.documents[0].source_id, "locator": "block-22",
        "metric": "Cash and cash equivalents", "value": "666", "unit": "million",
        "period": "September 30, 2026", "kind": "historical",
        "quote": "Cash and cash equivalents was $666 million as of September 30, 2026.",
    }
    result = parse_disclosure_report(report([good] * 28 + [bad, cash]), blocks_for(package), packages=(package,))
    assert {claim.metric for claim in result.claims} == {"AI Customer ARR", "Cash and cash equivalents"}
    assert len(result.rejected) == 1
    assert result.rejected[0].startswith("record 28: malformed")
    assert all(claim.value != 380000 for claim in result.claims)


def test_source_rejections_keep_original_indices_after_malformed_row():
    package = recorded_package()
    good = recorded_claim(package).model_dump(mode="json")
    bad = {**good, "value": "380,000"}
    contradicted = {**good, "value": "377"}
    result = parse_disclosure_report(report([good] * 28 + [bad, contradicted]), blocks_for(package), packages=(package,))
    assert result.claims == (recorded_claim(package),)
    assert result.rejected[0].startswith("record 28: malformed")
    assert result.rejected[1].startswith("record 29:")
    assert "numeric value" in result.rejected[1]


def test_malformed_nonobject_record_is_not_accepted_or_silently_lost():
    package = recorded_package()
    good = recorded_claim(package).model_dump(mode="json")
    result = parse_disclosure_report(report([None, good]), blocks_for(package), packages=(package,))
    assert result.claims == (recorded_claim(package),)
    assert result.rejected[0].startswith("record 0: malformed")


def test_disclosure_envelope_limits_still_fail_globally():
    package = recorded_package()
    good = recorded_claim(package).model_dump(mode="json")
    fence = chr(96) * 3
    invalid = [
        report([good] * 33),
        report([good]) + report([good]),
        report({"not": "a list"}),
        fence + "disclosures\n[\n" + fence,
        fence + "disclosures\n[" + " " * 48001 + "]\n" + fence,
    ]
    for raw in invalid:
        result = parse_disclosure_report(raw, blocks_for(package), packages=(package,))
        assert not result.claims and result.rejected
