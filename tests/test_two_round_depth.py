"""Two-round selection is explicit and preserves the user's remembered choice."""
from types import SimpleNamespace

import pytest

from cli import prefs, prompts
from cli.models import AssetType
from tradingagents.graph.conditional_logic import ConditionalLogic


@pytest.mark.parametrize("depth", [1, 2, 3, 5])
def test_depth_menu_and_preferences_preserve_selected_depth(monkeypatch, tmp_path, depth):
    path = tmp_path / "preferences.json"
    monkeypatch.setenv("TRADINGAGENTS_PREFS_PATH", str(path))
    prefs.save_last_run({"research_depth": depth})
    before = path.read_bytes()
    captured = {}

    def select(_title, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(ask=lambda: depth)

    monkeypatch.setattr(prompts.questionary, "select", select)
    assert prompts.select_research_depth(default=depth) == depth
    assert [option.value for option in captured["choices"]] == [1, 2, 3, 5]
    assert prefs.sanitize(prefs.load_last_run(), AssetType.STOCK)["research_depth"] == depth
    assert path.read_bytes() == before


@pytest.mark.parametrize("depth", [1, 2, 3, 5])
def test_each_depth_has_complete_research_and_risk_cycles(depth):
    logic = ConditionalLogic(depth, depth)
    research = {"investment_debate_state": {"count": 0, "current_response": ""}}
    risk = {"risk_debate_state": {"count": 0, "latest_speaker": ""}}
    research_roles, risk_roles = [], []
    while (role := logic.should_continue_debate(research)) != "Research Manager":
        research_roles.append(role)
        research["investment_debate_state"]["count"] += 1
        research["investment_debate_state"]["current_response"] = role
    while (role := logic.should_continue_risk_analysis(risk)) != "Portfolio Manager":
        risk_roles.append(role)
        risk["risk_debate_state"]["count"] += 1
        risk["risk_debate_state"]["latest_speaker"] = role
    assert research_roles == ["Bull Researcher", "Bear Researcher"] * depth
    assert risk_roles == ["Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"] * depth
