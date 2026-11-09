"""The seven model disclosures rejected in the 2026-11-09 DOCN run, by disposition."""
import json

import pytest

from tests.test_disclosure_context import blocks_for, recorded_package
from tradingagents.dataflows.disclosure_evidence import parse_disclosure_report

_BULLET = "\u2022"
_Q3 = {"period": "Third Quarter 2026", "kind": "historical", "period_locator": "block-11"}
_FY = {"period": "full year 2026", "kind": "guidance", "period_locator": "block-45"}
_Q4 = {"period": "fourth quarter ending December 31, 2026", "kind": "guidance", "period_locator": "block-40"}
_DROPS = "numeric quote drops part of the source subject or qualifier"
_TEMPORAL = "claim clause has its own or contradictory temporal qualifier"
RECORDS = [
    ("block-46", "Total revenue", "1.208", "1.211", "billion", _FY, None),
    ("block-41", "Total revenue", "348", "351", "million", _Q4, None),
    ("block-48", "Adjusted free cash flow margin", "20", "22", "%", _FY, None),
    ("block-12", "Revenue", "321", None, "million", _Q3, None),
    ("block-13", "AI Customer ARR", "376", None, "million", _Q3, _DROPS),
    ("block-24", "Remaining Performance Obligation", "800", None, "million", _Q3, _DROPS),
    ("block-21", "Adjusted free cash flow", "130", None, "million", _Q3, _TEMPORAL),
]


def _parse(package, records):
    fence = "```disclosures\n" + json.dumps(records) + "\n```"
    return parse_disclosure_report(fence, blocks_for(package), packages=(package,))


def _record(package, locator, metric, value, upper, unit, context):
    doc = package.documents[0]
    quote = next(b.text for b in doc.blocks if b.locator == locator)
    assert quote.startswith(_BULLET)
    return {"source_id": doc.source_id, "locator": locator, "metric": metric, "value": value, "upper_value": upper,
            "unit": unit, "quote": quote, "definition": None, **context}


@pytest.mark.parametrize("row", RECORDS, ids=[row[1] for row in RECORDS])
def test_recorded_rejection_has_its_true_disposition(row):
    package = recorded_package()
    *fields, expected = row
    result = _parse(package, [_record(package, *fields)])
    if expected is None:
        assert len(result.claims) == 1, result.rejected
        assert not result.claims[0].quote.startswith(_BULLET)
    else:
        assert not result.claims and expected in " ".join(result.rejected)


def test_verbatim_span_with_metric_phrase_is_accepted():
    package = recorded_package()
    assert len(_parse(package, [_record(package, *RECORDS[3][:-1])]).claims) == 1


def test_quote_missing_subject_is_still_rejected():
    package = recorded_package()
    record = _record(package, *RECORDS[3][:-1])
    record["quote"] = record["quote"].split("Revenue ")[1]
    result = _parse(package, [record])
    assert not result.claims and result.rejected
