"""Recorded SEC release context: exact numeric spans with separately cited context."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from tradingagents.dataflows.disclosure_evidence import (
    DisclosureClaim,
    parse_disclosure_report,
    validate_disclosure_claims,
)
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

FIXTURE = Path(__file__).parent / "fixtures/docn_2026q3/release_context.json"


def recorded_package():
    fixture = json.loads(FIXTURE.read_text())
    package = DisclosurePackage.model_validate(fixture["package"])
    doc = package.documents[0]
    assert fixture["provenance"]["source_url"] == doc.url
    assert fixture["provenance"]["source_content_hash"] == doc.content_hash
    assert len(doc.blocks) == 148
    return package


def blocks_for(package):
    return {
        (doc.source_id, block.locator): block.section + "\n" + block.text
        for doc in package.documents
        for block in doc.blocks
    }


def recorded_claim(package, **changes):
    doc = package.documents[0]
    definition = next(b.text for b in doc.blocks if b.locator == "block-95")
    data = {
        "source_id": doc.source_id,
        "locator": "block-13",
        "metric": "AI Customer ARR",
        "value": "376",
        "unit": "million",
        "period": "Third Quarter 2026",
        "kind": "historical",
        "quote": "AI Customer ARR was $376 million",
        "period_locator": "block-11",
        "definition": definition,
        "definition_locator": "block-95",
        "comparison": {
            "quote": ", an increase of 288%",
            "value": "288",
            "unit": "%",
            "basis_locator": "block-35",
        },
    }
    data.update(changes)
    return DisclosureClaim.model_validate(data)


def validate(claim, package):
    return validate_disclosure_claims([claim], blocks_for(package), packages=(package,))


def mutate_block(package, locator, **changes):
    data = package.model_dump(mode="json")
    for block in data["documents"][0]["blocks"]:
        if block["locator"] == locator:
            block.update(changes)
            return DisclosurePackage.model_validate(data)
    raise AssertionError(locator)


def test_recorded_q3_ai_arr_has_exact_period_definition_and_growth_basis():
    package = recorded_package()
    claim = recorded_claim(package)
    result = validate(claim, package)
    assert result.rejected == ()
    assert result.warnings == ()
    assert result.claims == (claim,)
    assert claim.definition.startswith("We calculate AI Customer ARR")
    assert claim.comparison.value == 288
    report = "Research\n```disclosures\n" + json.dumps([claim.model_dump(mode="json")]) + "\n```"
    assert parse_disclosure_report(report, blocks_for(package), packages=(package,)).claims == (claim,)


@pytest.mark.parametrize("marker", ["", "• ", "- ", "  •  "])
def test_reported_value_at_start_of_highlight_accepts_list_marker(marker):
    package = recorded_package()
    claim = recorded_claim(package)
    package = mutate_block(
        package, claim.locator,
        text=marker + "AI Customer ARR was $376 million, an increase of 288%.",
    )
    assert validate(claim, package).claims == (claim,)


@pytest.mark.parametrize("prefix", ["• Hypothetically, ", "• Prior quarter: ", "• Unaudited estimate: "])
def test_list_marker_does_not_hide_preceding_qualification(prefix):
    package = recorded_package()
    claim = recorded_claim(package)
    package = mutate_block(
        package, claim.locator,
        text=prefix + "AI Customer ARR was $376 million, an increase of 288%.",
    )
    assert not validate(claim, package).claims


@pytest.mark.parametrize(
    "changes",
    [
        {"period": "Third Quarter 2025"},
        {"period": "Fourth Quarter 2026"},
        {"metric": "AI product revenue"},
        {"value": "377"},
        {"definition": "AI Customer ARR is pure AI product revenue."},
        {"definition_locator": "block-98"},
        {"period_locator": "block-40"},
        {"comparison": {"quote": ", an increase of 288%", "value": "40", "unit": "%", "basis_locator": "block-35"}},
        {"comparison": {"quote": ", an increase of 288%", "value": "288", "unit": "%", "basis_locator": "block-36"}},
    ],
)
def test_recorded_claim_rejects_wrong_period_metric_value_definition_or_comparison(changes):
    package = recorded_package()
    assert not validate(recorded_claim(package, **changes), package).claims


@pytest.mark.parametrize("locator", ["block-11", "block-13", "block-35", "block-95"])
def test_truncated_context_or_claim_cannot_validate(locator):
    package = recorded_package()
    assert not validate(recorded_claim(package), mutate_block(package, locator, truncated=True)).claims


def test_missing_intervening_financial_highlight_block_does_not_extend_heading_scope():
    package = recorded_package()
    data = package.model_dump(mode="json")
    data["documents"][0]["blocks"] = [
        block for block in data["documents"][0]["blocks"] if block["locator"] != "block-12"
    ]
    assert not validate(recorded_claim(package), DisclosurePackage.model_validate(data)).claims


@pytest.mark.parametrize(
    "locator,old,new",
    [
        ("block-11", "Third Quarter 2026", "Third Quarter 2025"),
        ("block-13", "AI Customer ARR was $376 million", "AI product revenue was $376 million"),
        ("block-13", "AI Customer ARR was $376 million, an increase of 288%", "In the prior quarter, AI Customer ARR was $376 million, an increase of 288%"),
        ("block-13", ", an increase of 288%", ", an increase of 40%"),
        ("block-35", "year-over-year", "quarter-over-quarter"),
        ("block-94", "AI Customer ARR", "Annual Run-Rate Revenue"),
        ("block-95", "We calculate AI Customer ARR", "We calculate AI product revenue"),
    ],
)
def test_mutated_source_context_is_rejected(locator, old, new):
    package = recorded_package()
    block = next(b for b in package.documents[0].blocks if b.locator == locator)
    assert old in block.text
    changed = mutate_block(package, locator, text=block.text.replace(old, new, 1))
    assert not validate(recorded_claim(package), changed).claims


@pytest.mark.parametrize("mutation", ["after_cutoff", "wrong_issuer"])
def test_document_identity_and_cutoff_must_hold(mutation):
    package = recorded_package()
    data = package.model_dump(mode="json")
    if mutation == "after_cutoff":
        data["as_of"] = "2026-11-02"
    else:
        data["documents"][0]["filing"]["cik"] = "0001234567"
    assert not validate(recorded_claim(package), DisclosurePackage.model_validate(data)).claims


def test_second_issuer_uses_same_literal_context_contract():
    url = "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001/release.htm"
    source_id = "sec-document-" + hashlib.sha256(url.encode()).hexdigest()
    text = (
        "Third Quarter 2026 Financial Highlights(1):",
        "Cloud Usage ARR was $50 million, an increase of 20%.",
        "(1)All growth rates are year-over-year unless otherwise specified.",
        "Cloud Usage ARR",
        "We calculate Cloud Usage ARR by annualizing usage revenue for the latest quarter.",
    )
    document = {
        "source_id": source_id,
        "filing": {
            "cik": "0001234567", "accession": "0001234567-26-000001", "form": "8-K",
            "filed_date": "2026-11-03", "report_date": "2026-09-30",
            "primary_document": "release.htm", "items": "2.02", "url": url,
        },
        "url": url, "retrieved_at": "2026-11-04T00:00:00Z",
        "content_hash": hashlib.sha256("\n".join(text).encode()).hexdigest(),
        "blocks": [
            {"locator": f"block-{i}", "section": "Document", "text": value}
            for i, value in enumerate(text, 1)
        ],
    }
    package = DisclosurePackage.model_validate({
        "cik": "0001234567", "as_of": "2026-11-04", "documents": [document],
        "selected_accessions": [document["filing"]["accession"]],
    })
    claim = DisclosureClaim.model_validate({
        "source_id": source_id, "locator": "block-2", "metric": "Cloud Usage ARR",
        "value": "50", "unit": "million", "period": "Third Quarter 2026",
        "kind": "historical", "quote": "Cloud Usage ARR was $50 million",
        "period_locator": "block-1", "definition": text[4], "definition_locator": "block-5",
        "comparison": {"quote": ", an increase of 20%", "value": "20", "unit": "%", "basis_locator": "block-3"},
    })
    assert validate(claim, package).claims == (claim,)


def test_definition_cannot_be_borrowed_from_a_different_document():
    package = recorded_package()
    claim = recorded_claim(package)
    data = package.model_dump(mode="json")
    original = data["documents"][0]
    definition_blocks = [
        block for block in original["blocks"] if block["locator"] in {"block-94", "block-95"}
    ]
    original["blocks"] = [
        block for block in original["blocks"] if block["locator"] not in {"block-94", "block-95"}
    ]
    other = copy.deepcopy(original)
    other["url"] = other["url"].replace("a2026-q3dopressrelease.htm", "other-exhibit.htm")
    other["source_id"] = "sec-document-" + hashlib.sha256(other["url"].encode()).hexdigest()
    other["content_hash"] = hashlib.sha256(
        "\n".join(block["text"] for block in definition_blocks).encode()
    ).hexdigest()
    other["blocks"] = definition_blocks
    data["documents"].append(other)
    assert not validate(claim, DisclosurePackage.model_validate(data)).claims


def test_definition_requires_its_metric_heading():
    package = recorded_package()
    claim = recorded_claim(package)
    data = package.model_dump(mode="json")
    data["documents"][0]["blocks"] = [
        block for block in data["documents"][0]["blocks"] if block["locator"] != "block-94"
    ]
    assert not validate(claim, DisclosurePackage.model_validate(data)).claims

@pytest.mark.parametrize("prefix", [
    "In the prior quarter, ",
    "In 2025, ",
    "In a hypothetical scenario, ",
])
def test_context_cannot_discard_a_qualifier_in_the_preceding_sentence(prefix):
    package = recorded_package()
    block = next(b for b in package.documents[0].blocks if b.locator == "block-13")
    changed = mutate_block(package, "block-13", text=prefix + block.text)
    assert not validate(recorded_claim(package), changed).claims


def test_comparison_cannot_override_year_over_year_with_quarter_over_quarter_suffix():
    package = recorded_package()
    block = next(b for b in package.documents[0].blocks if b.locator == "block-13")
    changed = mutate_block(package, "block-13",
                           text=block.text.replace("an increase of 288%.", "an increase of 288% quarter-over-quarter."))
    assert not validate(recorded_claim(package), changed).claims


def test_comparison_note_scope_cannot_skip_omitted_source_blocks():
    package = recorded_package()
    data = package.model_dump(mode="json")
    data["documents"][0]["blocks"] = [b for b in data["documents"][0]["blocks"] if b["locator"] != "block-34"]
    assert not validate(recorded_claim(package), DisclosurePackage.model_validate(data)).claims


def test_comparison_note_cannot_skip_an_earlier_conflicting_same_number():
    package = recorded_package()
    changed = mutate_block(package, "block-34", text="(1)Growth rates are quarter-over-quarter.")
    assert not validate(recorded_claim(package), changed).claims

def test_source_metric_cannot_be_narrowed_from_ai_customer_arr_to_total_arr():
    package = recorded_package()
    definition = next(b.text for b in package.documents[0].blocks if b.locator == "block-93")
    claim = recorded_claim(package, metric="ARR", quote="ARR was $376 million",
                           definition=definition, definition_locator="block-93")
    assert not validate(claim, package).claims


@pytest.mark.parametrize("replacement", [
    "No, AI Customer ARR was $376 million, an increase of 288%.",
    "AI Customer ARR was $376 million is a false claim.",
    "AI Customer ARR was $376 million excluding cloud spending.",
])
def test_context_value_quote_cannot_drop_subject_or_material_clause_qualifications(replacement):
    package = recorded_package()
    block = next(b for b in package.documents[0].blocks if b.locator == "block-13")
    changed = mutate_block(package, "block-13",
                           text=block.text.replace("AI Customer ARR was $376 million, an increase of 288%.", replacement))
    assert not validate(recorded_claim(package, comparison=None), changed).claims

def test_definition_only_context_cannot_drop_ai_customer_metric_qualifier():
    package = recorded_package()
    block = next(b for b in package.documents[0].blocks if b.locator == "block-13")
    changed = mutate_block(package, "block-13", text=block.text.replace(
        "AI Customer ARR was $376 million, an increase of 288%.",
        "AI Customer ARR was $376 million at September 30, 2026."))
    definition = next(b.text for b in package.documents[0].blocks if b.locator == "block-93")
    claim = recorded_claim(changed, metric="ARR",
        quote="ARR was $376 million at September 30, 2026",
        period="September 30, 2026", period_locator=None, comparison=None,
        definition=definition, definition_locator="block-93")
    assert not validate(claim, changed).claims

def test_definition_name_cannot_be_extended_beyond_claimed_metric():
    package = recorded_package()
    definition = next(b.text for b in package.documents[0].blocks if b.locator == "block-95")
    changed_text = definition.replace("We calculate AI Customer ARR by", "We calculate AI Customer ARR Plus by")
    changed = mutate_block(package, "block-95", text=changed_text)
    assert not validate(recorded_claim(changed), changed).claims

@pytest.mark.parametrize("position", ["before", "after"])
def test_local_growth_basis_override_cannot_be_labeled_year_over_year(position):
    package = recorded_package()
    block = next(b for b in package.documents[0].blocks if b.locator == "block-13")
    text = ("All following growth rates are quarter-over-quarter. " + block.text
            if position == "before" else block.text + " This growth rate is quarter-over-quarter.")
    assert not validate(recorded_claim(package), mutate_block(package, "block-13", text=text)).claims


def test_context_document_url_must_match_issuer_accession_and_source_identity():
    package = recorded_package()
    data = package.model_dump(mode="json")
    data["documents"][0]["url"] = data["documents"][0]["url"].replace("/data/1582961/", "/data/1234567/")
    assert not validate(recorded_claim(package), DisclosurePackage.model_validate(data)).claims

def test_context_requires_original_documents_not_only_a_flat_quote_map():
    package = recorded_package()
    result = validate_disclosure_claims([recorded_claim(package)], blocks_for(package))
    assert not result.claims and result.rejected


def test_historical_highlights_heading_cannot_be_used_for_guidance():
    package = recorded_package()
    assert not validate(recorded_claim(package, kind="guidance"), package).claims


def test_analyst_and_canonical_gate_preserve_context_and_render_definition():
    from langchain_core.messages import ToolMessage

    from tradingagents.agents.analysts.fundamentals_analyst import _disclosures
    from tradingagents.agents.evidence_validation import assess_financial_package
    from tradingagents.dataflows.financial_evidence import EvidencePackage

    package = recorded_package()
    claim = recorded_claim(package)
    fence = chr(96) * 3
    report = fence + "disclosures\n" + json.dumps([claim.model_dump(mode="json")]) + "\n" + fence
    state = {
        "trade_date": str(package.as_of),
        "fundamentals_report": report,
        "messages": [ToolMessage(content=package.model_dump_json(),
                                 name="get_filing_evidence", tool_call_id="recorded")],
    }
    analyst = _disclosures(state, report)
    assert analyst["extraction"]["claims"][0]["period_locator"] == "block-11"
    assert analyst["extraction"]["claims"][0]["comparison"]["basis_locator"] == "block-35"
    # No synthetic core statements are smuggled into this recorded-release proof:
    # KPI extraction can pass while the missing financial package still gets REVIEW.
    result = assess_financial_package(
        state, EvidencePackage(cik=package.cik, as_of=package.as_of), package)
    assert result["final_rating"] == "REVIEW"
    accepted = result["disclosure_evidence"]["extraction"]["claims"]
    ai_arr = [item for item in accepted if item["metric"] == "AI Customer ARR"]
    assert len(ai_arr) == 1
    assert ai_arr[0]["period_locator"] == "block-11"
    assert ai_arr[0]["definition"] == claim.definition
    assert ai_arr[0]["comparison"]["basis_locator"] == "block-35"
    context = result["canonical_financial_context"]
    for text in (claim.definition, "Third Quarter 2026", "288%", "year-over-year",
                 "block-11", "block-13", "block-35", "block-95"):
        assert text in context
    assert "No comparator amount inferred" in context

def test_context_definition_cannot_be_an_unrelated_substring_of_value_block():
    package = recorded_package()
    claim = recorded_claim(package, definition="Annual Run-Rate Revenue", definition_locator=None)
    assert not validate(claim, package).claims


def test_omitted_context_definition_remains_a_visible_optional_warning():
    package = recorded_package()
    claim = recorded_claim(package, definition=None, definition_locator=None)
    result = validate(claim, package)
    assert result.claims == (claim,)
    assert any("definition not extracted" in warning for warning in result.warnings)

def test_recorded_release_headline_guidance_remains_a_distinct_dated_range():
    package = recorded_package()
    claim = DisclosureClaim(
        source_id=package.documents[0].source_id, locator="block-4",
        metric="exit revenue growth outlook", value="44", upper_value="45",
        unit="%", period="Q4 2026", kind="guidance",
        quote="Q4 2026 exit revenue growth outlook to 44-45%",
    )
    result = validate(claim, package)
    assert result.claims == (claim,)
    assert result.claims[0].kind == "guidance"
    assert "2027" not in result.claims[0].quote
