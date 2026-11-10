"""The disclosure extraction prompt carries one worked record per kind (step test T6)."""

import json
import re

import pytest

from tradingagents.agents.analysts.fundamentals_analyst import DISCLOSURE_EXTRACTION


@pytest.mark.unit
def test_each_kind_has_one_worked_record_with_its_period_source():
    records = [json.loads(match) for match in re.findall(r"Record: (\{.*?\})\.", DISCLOSURE_EXTRACTION)]
    assert sorted(record["kind"] for record in records) == ["ambition", "guidance", "historical"]
    for record in records:
        period_in_quote = record["period"] in record["quote"]
        # A period absent from the quote is supplied through its heading block.
        assert period_in_quote or record["period_locator"], record
        assert record["comparator"] == ("at_least" if record["kind"] == "ambition" else "exact")
