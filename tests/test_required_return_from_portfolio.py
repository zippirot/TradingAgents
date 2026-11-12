"""The return you require is your own setting, so it can be set in the portfolio file.

Asked by the user 2026-11-12. The app's default is the 10-year Treasury yield plus 5 points, and that one
figure moves every rating. The portfolio file already holds the other personal settings (standard weight,
loss budget, what each rating means), so the premium above the Treasury yield can be set there too.

Boundary: a file without the setting changes nothing, and the report says where the premium came from.
"""
from decimal import Decimal

import pytest

from tradingagents.agents.required_return import (
    premium_for_run,
    render_required_return,
    required_return_record,
)
from tradingagents.portfolio import PortfolioContext

POINT = {"date": "2026-11-09", "value": "4.88"}


def test_the_portfolio_file_can_set_the_premium_and_it_changes_the_fingerprint():
    plain = PortfolioContext.model_validate({"positions": [{"ticker": "DOCN", "quantity": 10}]})
    own = PortfolioContext.model_validate({"positions": [{"ticker": "DOCN", "quantity": 10}], "required_return_premium": 0.03})
    assert own.inputs()["required_return_premium"] == 0.03 and plain.inputs()["required_return_premium"] is None
    assert own.fingerprint() != plain.fingerprint()
    for bad in (-0.01, 0.31):
        with pytest.raises(ValueError):
            PortfolioContext.model_validate({"positions": [], "required_return_premium": bad})


def test_a_run_uses_the_files_premium_when_set_and_the_config_default_otherwise():
    config = {"required_return_premium": 0.05}
    assert premium_for_run(config, {"required_return_premium": 0.03}) == (Decimal("0.03"), "portfolio file")
    assert premium_for_run(config, {"required_return_premium": None}) == (Decimal("0.05"), "app setting")
    assert premium_for_run(config, None) == (Decimal("0.05"), "app setting")
    assert premium_for_run(config, {"required_return_premium": 0.9})[0] is None       # unusable is not silently replaced


def test_the_report_says_where_the_premium_came_from():
    record = required_return_record(POINT, Decimal("0.03"), "2026-11-12", premium_source="portfolio file")
    text = render_required_return(record)
    assert "Required return 7.88% a year" in text and "premium of 3.00 points" in text and "set in your portfolio file" in text
    default = render_required_return(required_return_record(POINT, Decimal("0.05"), "2026-11-12"))
    assert "9.88%" in default and "portfolio file" not in default
