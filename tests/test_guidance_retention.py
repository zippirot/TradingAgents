"""Guidance blocks stay contiguous when a filing reaches its text budget."""

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from tradingagents.dataflows.vendors.sec_documents import extract_sections

FIXTURES = Path(__file__).parent / "fixtures" / "docn_2026_11_07"
RELEASES = (
    "sec-e5702f82329f857c41a948e957efbcda16c5eaa9132004baec404bfd8669e076.json.gz",
    "sec-c4060c33f967164d4f79d532579b43ef655ce3156265c711ceaf4b4105c1c6b3.json.gz",
)


def _release(path):
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    decoded = gzip.decompress((FIXTURES / path).read_bytes())
    assert hashlib.sha256(decoded).hexdigest() == manifest["source_files"][path]["decoded_sha256"]
    source = json.loads(decoded)
    assert hashlib.sha256(source["text"].encode()).hexdigest() == source["content_hash"]
    return source["text"]


@pytest.mark.parametrize("path", RELEASES)
def test_outlook_run_survives_text_limit(path):
    blocks, _, gaps = extract_sections(_release(path), max_chars=36000, prioritize_guidance=True)
    by_locator = {block.locator: block for block in blocks}
    assert all(f"block-{number}" in by_locator for number in range(39, 53))
    assert all(not by_locator[f"block-{number}"].truncated for number in range(39, 53))
    outlook = " ".join(by_locator[f"block-{number}"].text for number in range(39, 53))
    assert "128 to 129 million shares" in outlook
    assert "122 to 123 million shares" in outlook
    assert "Adjusted EBITDA margin of 42% to 43%" in outlook
    assert "Adjusted EBITDA margin of 41% to 42%" in outlook
    assert "20% to 22% of revenue" in outlook
    assert not any("Financial Outlook" in gap for gap in gaps)


@pytest.mark.parametrize("heading_html", ("<p>Financial Outlook:</p>", "<h2>Financial Outlook</h2>"))
@pytest.mark.parametrize("prioritize_guidance", (False, True))
def test_dropped_run_records_named_gap(heading_html, prioritize_guidance):
    html = heading_html + (
        "<p>DigitalOcean is providing guidance for the fourth quarter:</p>"
        "<p>•Adjusted EBITDA margin of 42% to 43%.</p>"
        "<p>•Fully diluted weighted average shares of 128 to 129 million.</p>"
        "<p>Conference Call Information:</p>"
        "<p>" + "Other filing text. " * 50 + "</p>"
    )
    full, _, _ = extract_sections(html, max_chars=10000, prioritize_guidance=True)
    run = {block.locator for block in full[:4]}
    assert sum(len(block.text) for block in full[:4]) > 100
    bounded, _, gaps = extract_sections(html, max_chars=100, prioritize_guidance=prioritize_guidance)
    assert not run.intersection(block.locator for block in bounded)
    assert sum("Financial Outlook" in gap for gap in gaps) == 1


def test_adjacent_guidance_headings_and_bullets_are_one_run():
    html = (
        "<p>Financial Outlook:</p>"
        "<p>Fourth Quarter Guidance:</p>"
        "<p>•Adjusted EBITDA Margin:</p>"
        "<p>42% to 43%.</p>"
        "<p>Full Year Guidance:</p>"
        "<p>•Adjusted Free Cash Flow Margin:</p>"
        "<p>20% to 22% of revenue.</p>"
        "<p>Conference Call Information:</p>"
        "<p>" + "Other filing text. " * 50 + "</p>"
    )
    full, _, _ = extract_sections(html, max_chars=10000)
    run = {block.locator for block in full[:7]}
    assert sum(len(block.text) for block in full[:7]) > 100
    bounded, _, gaps = extract_sections(html, max_chars=100)
    assert not run.intersection(block.locator for block in bounded)
    assert sum("Financial Outlook" in gap for gap in gaps) == 1
