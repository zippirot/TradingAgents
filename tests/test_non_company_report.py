"""A report on an asset that is not a company says so once, and prints no company-only blocks.

Seen 2026-11-13 on the first BTC-USD run: the decision card printed a raw library error ("1 validation error for
EvidencePackage ... pydantic.dev"), and "unavailable" lines for revenue guidance, vendor consensus, price-implied
revenue multiples and SEC document search, none of which can exist for bitcoin.

Boundary: only when the run's asset type is not "stock". A stock run is rendered exactly as before, including
its own "unavailable" lines, which there mean something was looked for and not found.
"""
from tradingagents.agents.decision_context import NOT_A_COMPANY, validate_final_case
from tradingagents.agents.document_access import render_document_searches
from tradingagents.agents.output_validation import valuation_section_for

CRYPTO = {"asset_type": "crypto", "company_of_interest": "BTC-USD", "trade_date": "2026-11-13", "financial_evidence": None}


def test_the_target_reason_is_a_plain_sentence_not_a_library_error():
    result = validate_final_case(CRYPTO, None)
    assert result.status == "unsupported" and list(result.reasons) == [NOT_A_COMPANY]
    stock = validate_final_case({**CRYPTO, "asset_type": "stock"}, None)
    assert stock.status == "unsupported" and list(stock.reasons) != [NOT_A_COMPANY]


def test_the_valuation_section_is_one_line_for_a_non_company_and_untouched_for_a_stock():
    built = "### What the price implies\n\nUnavailable: x"
    text = valuation_section_for(CRYPTO, built)
    assert "not a company" in text and "price action, news and sentiment" in text and "What the price implies" not in text
    assert valuation_section_for({"asset_type": "stock"}, built) == built
    assert valuation_section_for({}, built) == built


def test_no_document_search_block_for_a_non_company():
    state = {**CRYPTO, "document_sources": {"status": "unavailable", "reason": "SEC document search applies only to stock issuers"}}
    assert render_document_searches(state) == ""
