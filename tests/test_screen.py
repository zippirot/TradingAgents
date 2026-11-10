"""The company screen runs the required source checks only and never raises for one bad company."""
import os

from tradingagents import screen
from tradingagents.agents import evidence_validation


def _gate(statuses):
    def create(selected):
        assert selected == ["fundamentals"]

        def gate(state):
            if state["company_of_interest"] == "BOOM":
                raise RuntimeError("SEC unreachable")
            status = statuses[state["company_of_interest"]]
            return {"evidence_quality": {"checks": [
                {"code": code, "status": status.get(code, "pass"), "message": f"{code} message"}
                for code in evidence_validation.REQUIRED_FINANCIAL_CHECKS if code != "balance_sheet" or "drop" not in status]}}
        return gate
    return create


def test_a_company_passes_when_every_required_source_check_passes(monkeypatch):
    monkeypatch.setattr(evidence_validation, "create_evidence_gate", _gate({
        "DOCN": {"material_claims": "unavailable"}, "MSFT": {"obligation_perimeter": "unavailable"},
        "CAT": {"drop": True}}))
    assert "material_claims" not in screen.source_checks() and len(screen.source_checks()) >= 5
    good, large, missing, broken = (screen.screen(t, "2026-11-10") for t in ("docn", "MSFT", "CAT", "BOOM"))
    assert good["passes"] and good["ticker"] == "DOCN" and good["reasons"] == []
    assert not large["passes"] and large["reasons"] == ["obligation_perimeter: unavailable: obligation_perimeter message"]
    assert not missing["passes"] and missing["checks"]["balance_sheet"] == "unavailable"
    assert not broken["passes"] and broken["reasons"] == ["could not be assessed: RuntimeError: SEC unreachable"]
    text = screen.render([good, large, broken])
    assert "DOCN | can be analysed |" in text and "MSFT | stops before the debate |" in text
    assert "1 of 3 pass." in text


def test_the_command_drops_model_keys_and_lists_each_ticker_once(monkeypatch, capsys):
    monkeypatch.setattr(evidence_validation, "create_evidence_gate", _gate({"DOCN": {}}))
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    assert screen.main(["DOCN", "docn", "--date", "2026-11-10"]) == 0
    assert "OPENROUTER_API_KEY" not in os.environ
    assert capsys.readouterr().out.count("DOCN |") == 1
