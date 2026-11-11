"""A block cut short by the excerpt budget is the same block as its full view, not a conflict (plan L6).

Baseline 2026-11-11: CAT, PANW, JNJ, LRCX, INTC and CSCO failed source_integrity with "conflicting document
metadata: block text or attributes" because the bounded view truncated a block the full view held whole.
"""
import copy

import pytest

from tests.test_shared_source_brief import rpo_source_state
from tradingagents.dataflows.disclosure_context import collapse_quote_packages


def _views(monkeypatch):
    package = rpo_source_state(monkeypatch)["disclosure_evidence"]["packages"][0]
    full, bounded = copy.deepcopy(package), copy.deepcopy(package)
    index = next(i for i, block in enumerate(full["documents"][0]["blocks"]) if len(block["text"]) > 40)
    return full, bounded, index


def test_a_truncated_prefix_merges_into_the_full_block(monkeypatch):
    full, bounded, index = _views(monkeypatch)
    whole = full["documents"][0]["blocks"][index]
    whole["truncated"] = False
    cut = bounded["documents"][0]["blocks"][index]
    cut["text"], cut["truncated"] = whole["text"][:20], True
    for order in ((bounded, full), (full, bounded)):
        merged = collapse_quote_packages(order)[0]
        block = next(b for b in merged.documents[0].blocks if b.locator == whole["locator"])
        assert block.text == whole["text"] and block.truncated is False


def test_text_that_is_not_a_prefix_or_any_other_difference_is_still_a_conflict(monkeypatch):
    full, bounded, index = _views(monkeypatch)
    whole = full["documents"][0]["blocks"][index]
    whole["truncated"] = False
    cut = bounded["documents"][0]["blocks"][index]
    cut["text"], cut["truncated"] = "A different sentence entirely.", True
    with pytest.raises(ValueError, match="block text or attributes"):
        collapse_quote_packages((bounded, full))
    # A shorter text that does not say it was truncated is a different block, not a cut one.
    cut["text"], cut["truncated"] = whole["text"][:20], False
    with pytest.raises(ValueError, match="block text or attributes"):
        collapse_quote_packages((bounded, full))
    # Same words, another attribute changed.
    full2, bounded2, index2 = _views(monkeypatch)
    other = next(key for key in bounded2["documents"][0]["blocks"][index2] if key not in ("text", "truncated", "locator"))
    value = bounded2["documents"][0]["blocks"][index2][other]
    bounded2["documents"][0]["blocks"][index2][other] = (not value) if isinstance(value, bool) else f"{value}x"
    with pytest.raises(ValueError):
        collapse_quote_packages((bounded2, full2))
