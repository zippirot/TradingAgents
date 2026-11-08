"""Complete supported source sentences retain qualifications and original input."""
from decimal import Decimal

import pytest

from tests.test_disclosure_context import blocks_for, recorded_package
from tradingagents.dataflows.disclosure_evidence import DisclosureClaim, validate_disclosure_claims


@pytest.mark.parametrize('locator,metric,value,upper,unit,period,kind,period_locator,comparator', [
    ('block-46', 'Total revenue', '1.208', '1.211', 'billion', 'full year 2026', 'guidance', 'block-45', 'exact'),
    ('block-41', 'Total revenue', '348', '351', 'million', 'fourth quarter ending December 31, 2026', 'guidance', 'block-40', 'exact'),
    ('block-4', 'revenue growth', '60', None, '%', '2027', 'guidance', None, 'at_least'),
    ('block-12', 'Revenue', '321', None, 'million', 'Third Quarter 2026', 'historical', 'block-11', 'exact'),
    ('block-17', 'Adjusted operating income', '74', None, 'million', 'Third Quarter 2026', 'historical', 'block-11', 'exact'),
    ('block-48', 'Adjusted free cash flow margin', '20', '22', '%', 'full year 2026', 'guidance', 'block-45', 'exact'),
])
def test_complete_supported_sentence_is_accepted_without_rewriting_submission(
        locator, metric, value, upper, unit, period, kind, period_locator, comparator):
    package = recorded_package()
    doc = package.documents[0]
    quote = next(b.text.lstrip('•- ').strip() for b in doc.blocks if b.locator == locator)
    claim = DisclosureClaim(source_id=doc.source_id, locator=locator, metric=metric, value=value,
                            upper_value=upper, unit=unit, period=period, kind=kind, quote=quote,
                            period_locator=period_locator, comparator=comparator)
    result = validate_disclosure_claims([claim], blocks_for(package), packages=(package, package))
    assert result.claims == (claim,)
    assert result.claims[0].quote == quote and result.claims[0].value_quote is None
    assert not result.rejected
    wrong = claim.model_copy(update={'value': Decimal('999')})
    assert not validate_disclosure_claims([wrong], blocks_for(package), packages=(package,)).claims
