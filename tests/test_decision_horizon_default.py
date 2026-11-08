"""Configured holding periods remain separate from forecasts and rating authority."""
from tests.test_portfolio_valuation import decision, invoke, state
from tradingagents.agents.decision_context import decision_horizon
from tradingagents.default_config import build_default_config


def horizon(**fields):
    result, _ = invoke(decision(**fields), state() | {"run_settings": {"decision_horizon_months": 6}})
    return decision_horizon(result)


def test_decision_horizon_default_six_months():
    assert build_default_config()["decision_horizon_months"] == 6
    assert horizon()["text"] == "6 months (configured default)"


def test_pm_override_requires_reason_and_missing_remains_incomplete():
    assert horizon(time_horizon="12 months")["text"].startswith("6 months (configured default")
    assert "without a reason" in horizon(time_horizon="12 months")["authority"]
    assert horizon(time_horizon="12 months", horizon_reason="Catalyst settles next year")["text"] == "12 months (PM override: Catalyst settles next year)"
    assert horizon(time_horizon=None)["status"] == "incomplete"
    assert horizon(time_horizon="forecast FY2027")["status"] == "incomplete"


def test_horizon_env_override(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_DECISION_HORIZON_MONTHS", "9")
    assert build_default_config()["decision_horizon_months"] == 9
