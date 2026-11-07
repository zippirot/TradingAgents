"""Synthetic dated outlook excerpts; no live issuer claims or model calls."""

import copy
import hashlib
import json
from datetime import date
from decimal import Decimal

import pytest

from tradingagents.agents.valuation import _outlooks
from tradingagents.agents.valuation_outlooks import grounded_outlooks
from tradingagents.dataflows.financial_evidence import EvidencePackage, SourceRecord

FENCE = chr(96) * 3


def state(
    metric="Revenue",
    value="1.170",
    upper="1.180",
    unit="billion USD",
    kind="guidance",
    period="2027-01-01 to 2027-12-31",
    basis="US-GAAP",
):
    quote = f"{basis} {metric} {kind} is {value} to {upper} {unit} for {period}."
    claim = {
        "source_id": "doc",
        "locator": "block-1",
        "metric": metric,
        "value": value,
        "upper_value": upper,
        "unit": unit,
        "period": period,
        "kind": kind,
        "quote": quote,
        "definition": None,
    }
    url = "https://www.sec.gov/Archives/edgar/data/1582961/000158296126000001/doc.htm"
    content_hash = hashlib.sha256(quote.encode()).hexdigest()
    source = SourceRecord(
        source_id="doc",
        cik="0001582961",
        url=url,
        filed_date="2026-08-04",
        retrieved_at="2026-11-04T00:00:00Z",
        content_hash=content_hash,
        locator="document",
        accession="0001582961-26-000001",
        form="8-K",
    )
    document = {
        "source_id": "doc",
        "filing": {
            "cik": "0001582961",
            "accession": source.accession,
            "form": "8-K",
            "filed_date": "2026-08-04",
            "report_date": "2026-08-04",
            "primary_document": "doc.htm",
            "items": "2.02",
            "url": url,
        },
        "url": url,
        "retrieved_at": "2026-11-04T00:00:00Z",
        "content_hash": content_hash,
        "blocks": [{"locator": "block-1", "section": "Financial outlook", "text": quote}],
        "gaps": [],
    }
    report = "Research\n" + FENCE + "disclosures\n" + json.dumps([claim]) + "\n" + FENCE
    return {
        "trade_date": "2026-10-19",
        "financial_evidence": EvidencePackage(
            cik=source.cik, as_of="2026-10-19", sources=(source,)
        ).model_dump(mode="json"),
        "filing_evidence": {
            "schema_version": 1,
            "cik": source.cik,
            "as_of": "2026-10-19",
            "documents": [document],
            "gaps": [],
            "selected_accessions": [source.accession],
        },
        "financial_claim_validation": {"raw_report": report},
        "fundamentals_report": "Canonical rewritten report",
    }


def test_annual_revenue_range_scaled_exactly_and_registered_with_valuation():
    s = state()
    result = grounded_outlooks(s)
    assert len(result) == 1
    outlook = result[0]
    assert outlook.metric == "Revenue" and outlook.unit == "USD" and outlook.basis == "US-GAAP"
    assert outlook.low == Decimal(1170000000) and outlook.high == Decimal(1180000000)
    assert (outlook.period_start, outlook.period_end) == (date(2027, 1, 1), date(2027, 12, 31))
    assert outlook.source_ids == ("doc",)
    package = EvidencePackage.model_validate(s["financial_evidence"])
    assert _outlooks(package, result) == result
    assert grounded_outlooks(s) == result


def test_adjusted_diluted_eps_and_ambition_remain_distinct():
    s = state(
        metric="Diluted EPS",
        value="1.10",
        upper="1.20",
        unit="USD per share",
        kind="ambition",
        basis="non-GAAP adjusted",
    )
    result = grounded_outlooks(s)
    assert len(result) == 1 and result[0].metric == "Diluted EPS"
    assert result[0].unit == "USD/shares" and result[0].basis == "management-adjusted"
    assert result[0].kind == "ambition" and result[0].low == Decimal("1.10")


@pytest.mark.parametrize(
    "changes",
    [
        {"period": "FY2027"},
        {"period": "2027-01-01 to 2027-03-31"},
        {"period": "2025-01-01 to 2025-12-31"},
        {"metric": "AI Customer ARR"},
        {"metric": "EPS", "unit": "USD per share", "value": "1", "upper": "2"},
        {"basis": ""},
        {"unit": "billion"},
        {"kind": "historical"},
    ],
)
def test_ambiguous_or_incompatible_outlook_is_unavailable(changes):
    assert grounded_outlooks(state(**changes)) == ()


@pytest.mark.parametrize(
    "field,value", [("value", "9"), ("metric", "Adjusted Revenue"), ("kind", "ambition")]
)
def test_model_claim_cannot_self_certify_against_unmodified_source(field, value):
    s = state()
    report = s["financial_claim_validation"]["raw_report"]
    claims = json.loads(report.split(FENCE + "disclosures\n")[1].split("\n" + FENCE)[0])
    claims[0][field] = value
    s["financial_claim_validation"]["raw_report"] = (
        FENCE + "disclosures\n" + json.dumps(claims) + "\n" + FENCE
    )
    s["disclosure_evidence"] = {"extraction": {"claims": claims, "status": "verified"}}
    assert grounded_outlooks(s) == ()


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_issuer",
        "late_filing",
        "cutoff_mismatch",
        "hash_mismatch",
        "truncated",
        "duplicate_source",
        "missing_package_source",
    ],
)
def test_provenance_must_match_canonical_package(mutation):
    s = state()
    doc = s["filing_evidence"]["documents"][0]
    if mutation == "wrong_issuer":
        doc["filing"]["cik"] = "0000320193"
    elif mutation == "late_filing":
        doc["filing"]["filed_date"] = "2026-11-01"
    elif mutation == "cutoff_mismatch":
        s["filing_evidence"]["as_of"] = "2026-11-04"
    elif mutation == "hash_mismatch":
        doc["content_hash"] = "b" * 64
    elif mutation == "truncated":
        doc["blocks"][0]["truncated"] = True
    elif mutation == "duplicate_source":
        s["filing_evidence"]["documents"].append(copy.deepcopy(doc))
    elif mutation == "missing_package_source":
        s["financial_evidence"]["sources"] = []
    assert grounded_outlooks(s) == ()


def test_malformed_or_absent_state_is_unavailable():
    for s in [
        {},
        {"financial_evidence": []},
        {"filing_evidence": {"documents": "bad"}},
        {"financial_claim_validation": [1]},
    ]:
        assert grounded_outlooks(s) == ()


def test_accounting_gate_registers_document_sources_for_outlook_comparison():
    from tradingagents.agents.evidence_validation import assess_financial_package
    from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

    s = state()
    empty = EvidencePackage(cik="0001582961", as_of="2026-10-19")
    s["fundamentals_report"] = s["financial_claim_validation"]["raw_report"]
    result = assess_financial_package(
        s, empty, DisclosurePackage.model_validate(s["filing_evidence"])
    )
    package = EvidencePackage.model_validate(result["financial_evidence"])
    assert "doc" in {source.source_id for source in package.sources}
    result_state = {**s, **result}
    assert len(grounded_outlooks(result_state)) == 1
    assert _outlooks(package, grounded_outlooks(result_state))


def test_document_source_collision_is_not_silently_replaced():
    from tradingagents.agents.evidence_validation import assess_financial_package
    from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

    s = state()
    package = EvidencePackage.model_validate(s["financial_evidence"])
    changed = package.sources[0].model_copy(update={"content_hash": "b" * 64})
    package = EvidencePackage(cik=package.cik, as_of=package.as_of, sources=(changed,))
    result = assess_financial_package(
        s, package, DisclosurePackage.model_validate(s["filing_evidence"])
    )
    quality = result["evidence_quality"]
    check = next(check for check in quality["checks"] if check["code"] == "source_integrity")
    assert check["status"] == "fail" and "collision" in check["message"]
    assert result["financial_evidence"]["sources"][0]["content_hash"] == "b" * 64


def combine(first, second, filed_date):
    second = copy.deepcopy(second)
    second["filing_evidence"]["documents"][0]["source_id"] = "doc-2"
    second["filing_evidence"]["documents"][0]["filing"]["filed_date"] = filed_date
    second["financial_evidence"]["sources"][0]["source_id"] = "doc-2"
    second["financial_evidence"]["sources"][0]["filed_date"] = filed_date
    first_claims = json.loads(
        first["financial_claim_validation"]["raw_report"]
        .split(FENCE + "disclosures\n")[1]
        .split("\n" + FENCE)[0]
    )
    second_claims = json.loads(
        second["financial_claim_validation"]["raw_report"]
        .split(FENCE + "disclosures\n")[1]
        .split("\n" + FENCE)[0]
    )
    second_claims[0]["source_id"] = "doc-2"
    merged = copy.deepcopy(first)
    merged["filing_evidence"]["documents"].extend(second["filing_evidence"]["documents"])
    merged["financial_evidence"]["sources"].extend(second["financial_evidence"]["sources"])
    merged["financial_claim_validation"]["raw_report"] = (
        FENCE + "disclosures\n" + json.dumps(first_claims + second_claims) + "\n" + FENCE
    )
    return merged


def with_discovered_release(first, *, low="800", high="900", filed_date="2026-09-01"):
    """Add a source-bound annual heading and bullet, without a model claim for it."""
    result = copy.deepcopy(first)
    accession = "0001582961-26-000002"
    url = "https://www.sec.gov/Archives/edgar/data/1582961/000158296126000002/new.htm"
    source_id = "sec-document-" + hashlib.sha256(url.encode()).hexdigest()
    heading = "For the full year 2027, we now expect:"
    bullet = f"• Revenue was {low} to {high} million."
    content_hash = hashlib.sha256((heading + bullet).encode()).hexdigest()
    result["financial_evidence"]["sources"].append({
        **result["financial_evidence"]["sources"][0], "source_id": source_id,
        "url": url, "accession": accession, "filed_date": filed_date,
        "content_hash": content_hash,
    })
    result["filing_evidence"]["documents"].append({
        **result["filing_evidence"]["documents"][0], "source_id": source_id,
        "url": url, "content_hash": content_hash,
        "filing": {**result["filing_evidence"]["documents"][0]["filing"],
                   "url": url, "accession": accession, "filed_date": filed_date},
        "blocks": [
            {"locator": "block-1", "section": "US-GAAP USD calendar year 2027", "text": heading},
            {"locator": "block-2", "section": "US-GAAP USD calendar year 2027", "text": bullet},
        ],
    })
    return result


@pytest.mark.parametrize("reverse", [False, True])
def test_newer_discovered_guidance_supersedes_old_model_quote(reverse):
    s = with_discovered_release(state())
    if reverse:
        s["filing_evidence"]["documents"].reverse()
        s["financial_evidence"]["sources"].reverse()
    result = grounded_outlooks(s)
    assert len(result) == 1
    assert result[0].low == Decimal("800000000")
    assert result[0].high == Decimal("900000000")


def test_same_day_discovered_conflict_has_stable_warning_and_no_outlook():
    from tradingagents.agents.valuation_outlooks import grounded_outlook_warnings

    s = with_discovered_release(state(), filed_date="2026-08-04")
    s = with_discovered_release(s, low="700", high="750", filed_date="2026-08-04")
    # A third document needs its own canonical source identity.
    doc = s["filing_evidence"]["documents"].pop()
    source = s["financial_evidence"]["sources"].pop()
    url = doc["url"].replace("new.htm", "other.htm")
    source_id = "sec-document-" + hashlib.sha256(url.encode()).hexdigest()
    doc.update(source_id=source_id, url=url)
    doc["filing"]["url"] = url
    source.update(source_id=source_id, url=url)
    s["filing_evidence"]["documents"].append(doc)
    s["financial_evidence"]["sources"].append(source)
    assert grounded_outlooks(s) == ()
    warnings = grounded_outlook_warnings(s)
    assert len(warnings) == 1 and "conflicting" in warnings[0].lower()
    s["filing_evidence"]["documents"].reverse()
    s["financial_evidence"]["sources"].reverse()
    assert grounded_outlook_warnings(s) == warnings


def test_cached_extraction_cannot_add_or_repair_discovered_guidance():
    s = with_discovered_release(state())
    s["disclosure_evidence"] = {"deterministic_extraction": {"status": "verified", "claims": [
        {"source_id": s["filing_evidence"]["documents"][1]["source_id"], "value": "9000"}
    ]}}
    assert grounded_outlooks(s)[0].low == Decimal("800000000")
    s["filing_evidence"]["documents"][1]["blocks"][1]["truncated"] = True
    assert grounded_outlooks(s)[0].low == Decimal("1170000000")


def test_discovery_works_without_model_report_but_duplicate_source_is_excluded():
    s = with_discovered_release(state())
    s["financial_claim_validation"] = {"raw_report": None}
    s["fundamentals_report"] = None
    assert grounded_outlooks(s)[0].low == Decimal("800000000")
    s["financial_evidence"]["sources"].append(copy.deepcopy(s["financial_evidence"]["sources"][1]))
    assert grounded_outlooks(s) == ()


def test_discovered_guidance_does_not_replace_distinct_ambition():
    s = with_discovered_release(state(kind="ambition"))
    result = grounded_outlooks(s)
    assert {(o.kind, o.low) for o in result} == {
        ("guidance", Decimal("800000000")),
        ("ambition", Decimal("1170000000")),
    }


@pytest.mark.parametrize("missing", ["calendar year 2027", "US-GAAP", "USD"])
def test_discovered_annual_range_needs_explicit_period_basis_and_currency(missing):
    s = with_discovered_release(state())
    doc = s["filing_evidence"]["documents"][1]
    for block in doc["blocks"]:
        block["section"] = block["section"].replace(missing, "")
    assert grounded_outlooks(s)[0].low == Decimal("1170000000")


def test_latest_filed_outlook_replaces_old_same_period_range():
    s = combine(state(), state(value="1.2", upper="1.3"), "2026-09-01")
    result = grounded_outlooks(s)
    assert len(result) == 1
    assert result[0].low == Decimal(1200000000) and result[0].source_ids == ("doc-2",)


def test_conflicting_same_vintage_ranges_remain_unavailable():
    s = combine(state(), state(value="1.2", upper="1.3"), "2026-08-04")
    assert grounded_outlooks(s) == ()


def test_accounting_gate_retains_outlook_conflict_warning_without_mutating_input():
    from tradingagents.agents.evidence_validation import assess_financial_package
    from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

    s = combine(state(), state(value="1.2", upper="1.3"), "2026-08-04")
    original = copy.deepcopy(s)
    package = EvidencePackage.model_validate(s["financial_evidence"])
    s["fundamentals_report"] = s["financial_claim_validation"]["raw_report"]
    expected_input = copy.deepcopy(s)
    update = assess_financial_package(s, package, DisclosurePackage.model_validate(s["filing_evidence"]))
    assert any("conflicting" in w.lower() for w in update["disclosure_evidence"].get("warnings", []))
    assert s == expected_input
    assert original["financial_evidence"] == s["financial_evidence"]


def test_guidance_and_ambition_are_not_collapsed_to_same_forecast():
    s = combine(state(), state(value="1.2", upper="1.3", kind="ambition"), "2026-09-01")
    result = grounded_outlooks(s)
    assert {outlook.kind for outlook in result} == {"guidance", "ambition"}


@pytest.mark.parametrize(
    "period,start,end",
    [
        ("calendar year 2027", "2027-01-01", "2027-12-31"),
        ("twelve months ending September 30, 2027", "2026-10-01", "2027-09-30"),
    ],
)
def test_explicit_annual_period_wording_is_parsed_without_fiscal_guess(period, start, end):
    result = grounded_outlooks(state(period=period))
    assert len(result) == 1
    assert (str(result[0].period_start), str(result[0].period_end)) == (start, end)


def test_wrong_period_numeric_binding_does_not_create_grounded_outlook():
    quote = "US-GAAP calendar year 2027 revenue guidance is USD 1.2 billion; US-GAAP calendar year 2026 revenue guidance is USD 1.5 billion."
    current = state(value="1.5", upper=None, unit="billion", period="calendar year 2027")
    content_hash = hashlib.sha256(quote.encode()).hexdigest()
    current["filing_evidence"]["documents"][0]["content_hash"] = content_hash
    current["filing_evidence"]["documents"][0]["blocks"][0]["text"] = quote
    current["financial_evidence"]["sources"][0]["content_hash"] = content_hash
    claim = {
        "source_id": "doc",
        "locator": "block-1",
        "metric": "revenue",
        "value": "1.5",
        "upper_value": None,
        "unit": "billion",
        "period": "calendar year 2027",
        "kind": "guidance",
        "quote": quote,
        "definition": None,
    }
    current["financial_claim_validation"]["raw_report"] = (
        FENCE + "disclosures\n" + json.dumps([claim]) + "\n" + FENCE
    )
    assert grounded_outlooks(current) == ()
    claim.update(value="1.2", quote=quote.split(";")[0])
    current["financial_claim_validation"]["raw_report"] = (
        FENCE + "disclosures\n" + json.dumps([claim]) + "\n" + FENCE
    )
    result = grounded_outlooks(current)
    assert len(result) == 1 and result[0].low == Decimal("1200000000")
    assert result[0].period_start == date(2027, 1, 1)
