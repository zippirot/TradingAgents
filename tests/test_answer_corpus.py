"""Every saved model answer of a kind is run through today's code before a handoff fix is called done."""
import json

from scripts import answer_corpus
from tests.test_case_valuation import revenue_case
from tests.test_replay_runs import _saved
from tests.test_shared_valuation import state


def _shares_only_run(tmp_path, cases):
    saved = state(cases)
    saved.update(run_id="22222222-bbbb", shared_valuation_scenarios={"status": "unavailable", "requests": cases})
    folder = tmp_path / "logs" / "DOCN" / "TradingAgentsStrategy_logs"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "full_states_log_2026-10-19_22222222.json").write_text(json.dumps(saved))
    return tmp_path / "logs"


def test_saved_cases_are_collected_with_their_run_and_accepted_on_current_code(tmp_path):
    logs = _saved(tmp_path)
    assert answer_corpus.collect(logs, tmp_path / "out")["valuation_cases"] == 1
    entry = json.loads((tmp_path / "out" / "valuation_cases.json").read_text())[0]
    assert entry["run_id"] == "11111111-aaaa" and entry["date"] == "2026-10-19" and entry["answer"][0]["name"] == "Base"
    result = answer_corpus.check("valuation_cases", logs)
    assert (result["answers"], result["accepted"], result["rejected"]) == (1, 1, 0)


def test_a_rejected_answer_reports_its_reason(tmp_path):
    broken = revenue_case()
    del broken["request"]["multiple"]
    result = answer_corpus.check("valuation_cases", _shares_only_run(tmp_path, [broken]))
    assert result["accepted"] == 0 and result["rejected"] == 1
    assert any("multiple" in reason for reason in result["reasons"])


def test_a_re_export_of_one_run_is_one_answer(tmp_path):
    logs = _saved(tmp_path)
    _saved(tmp_path, name="full_states_log_2026-10-19.json")
    assert answer_corpus.check("valuation_cases", logs)["answers"] == 1


def test_a_trader_proposal_without_one_action_is_rejected_and_one_with_it_is_read(tmp_path):
    logs = _saved(tmp_path)
    path = next((logs / "DOCN" / "TradingAgentsStrategy_logs").glob("*.json"))
    saved = json.loads(path.read_text())
    saved.update(trader_investment_plan="**Action**: Buy\n\n**Reasoning**: x",
                 investment_plan="**Recommendation**: Overweight")
    path.write_text(json.dumps(saved))
    assert answer_corpus.check("trader_proposals", logs)["accepted"] == 1
    saved["trader_investment_plan"] = "**Action**: Buy\n**Action**: Sell"
    path.write_text(json.dumps(saved))
    assert answer_corpus.check("trader_proposals", logs)["rejected"] == 1
