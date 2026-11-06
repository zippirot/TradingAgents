from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from cli.stats_handler import StatsCallbackHandler
from tradingagents import reporting
from tradingagents.graph.trading_graph import TradingAgentsGraph


def response(usage=None):
    return LLMResult(generations=[[ChatGeneration(message=AIMessage(content="done", usage_metadata=usage))]])


def complete(counter, inp=11, out=7):
    counter.on_llm_start({}, ["prompt"])
    counter.on_llm_end(response({"input_tokens": inp, "output_tokens": out, "total_tokens": inp + out}))


def owner(counter):
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph._metrics_callback = counter
    graph._metrics_observer_id = "new-process"
    graph._metrics_start = graph._callback_calls()
    return graph


def test_callback_counts_observed_usage_separately_from_missing_usage():
    counter = StatsCallbackHandler()
    complete(counter)
    counter.on_llm_start({}, ["another"])
    counter.on_llm_end(response())
    stats = counter.get_stats()
    assert stats["tokens_in"] == 11
    assert stats["tokens_out"] == 7
    assert stats["token_usage_calls"] == 1
    assert stats["token_usage_missing"] == 1


def test_run_records_only_its_own_usage_and_coverage():
    counter = StatsCallbackHandler()
    complete(counter, 100, 50)
    graph = owner(counter)
    initial = graph._initial_run_metrics()
    complete(counter, 11, 7)
    metrics = graph._observe_run_metrics({"run_metrics": initial})
    assert metrics["input_tokens"] == 11
    assert metrics["output_tokens"] == 7
    assert metrics["token_usage_scope"] == "complete_observed"
    assert metrics["token_usage_observed_calls"] == 1
    assert metrics["token_usage_started_calls"] == 1
    assert "11 input" in reporting.render_token_usage(metrics)
    assert "7 output" in reporting.render_token_usage(metrics)


def test_failed_call_and_usage_less_response_are_not_zero_usage():
    counter = StatsCallbackHandler()
    graph = owner(counter)
    initial = graph._initial_run_metrics()
    counter.on_llm_start({}, ["failed"])
    counter.on_llm_error(RuntimeError("provider unavailable"), run_id="failed-request")
    counter.on_llm_start({}, ["missing"])
    counter.on_llm_end(response())
    metrics = graph._observe_run_metrics({"run_metrics": initial})
    assert metrics["input_tokens"] is None
    assert metrics["output_tokens"] is None
    assert metrics["token_usage_scope"] == "unavailable"
    assert "unavailable" in reporting.render_token_usage(metrics)


def test_a_retry_with_only_one_usage_receipt_is_partial():
    counter = StatsCallbackHandler()
    graph = owner(counter)
    initial = graph._initial_run_metrics()
    counter.on_llm_start({}, ["failed"])
    counter.on_llm_error(RuntimeError("timeout"), run_id="failed-request")
    complete(counter)
    metrics = graph._observe_run_metrics({"run_metrics": initial})
    assert metrics["input_tokens"] == 11
    assert metrics["output_tokens"] == 7
    assert metrics["token_usage_scope"] == "partial_observed"
    assert metrics["token_usage_observed_calls"] == 1
    assert metrics["token_usage_started_calls"] == 2


def test_resume_preserves_known_totals_but_never_restores_complete_scope():
    counter = StatsCallbackHandler()
    graph = owner(counter)
    graph._initial_run_metrics()
    previous = {
        "observer_id": "old-process", "model_calls": 2,
        "token_observer_id": "old-process", "token_usage_scope": "complete_observed",
        "input_tokens": 123, "output_tokens": 45,
        "token_usage_observed_calls": 2, "token_usage_started_calls": 2,
    }
    complete(counter, 10, 4)
    resumed = graph._observe_run_metrics({"run_metrics": previous})
    assert (resumed["input_tokens"], resumed["output_tokens"]) == (133, 49)
    assert resumed["token_usage_scope"] == "partial_observed"
    complete(counter, 5, 2)
    later = graph._observe_run_metrics({"run_metrics": resumed})
    assert (later["input_tokens"], later["output_tokens"]) == (138, 51)
    assert later["token_usage_scope"] == "partial_observed"


def test_legacy_metrics_show_unavailable_without_inventing_zero():
    text = reporting.render_token_usage({"model_calls": 31})
    assert "unavailable" in text
    assert "0 input" not in text

def test_graph_audit_uses_actual_zero_retry_sdk_without_changing_other_tiers(tmp_path):
    import copy

    from tradingagents.default_config import DEFAULT_CONFIG

    config = copy.deepcopy(DEFAULT_CONFIG)
    config.update(llm_provider="openrouter", quick_think_provider="openrouter",
                  deep_think_provider="openrouter", backend_url="https://openrouter.ai/api/v1",
                  quick_think_llm="anthropic/claude-opus-5.5", deep_think_llm="openai/gpt-6.1-terra-pro",
                  llm_max_retries=3, data_cache_dir=str(tmp_path / "cache"),
                  results_dir=str(tmp_path / "results"), memory_log_path=str(tmp_path / "memory.md"))
    graph = TradingAgentsGraph(selected_analysts=("market",), config=config)
    assert graph.audit_llm.root_client.max_retries == 0
    assert graph.audit_llm.root_async_client.max_retries == 0
    assert graph.deep_thinking_llm.root_client.max_retries == 3
    assert graph.quick_thinking_llm.root_client.max_retries == 3


def test_report_footers_retain_usage_without_putting_it_in_decisions(tmp_path):
    from tradingagents.report_html import render_report

    metrics = {"input_tokens": 123, "output_tokens": 45, "token_usage_scope": "partial_observed"}
    state = {"trade_date": "2026-11-06", "run_metrics": metrics}
    path = reporting.write_report_tree(state, "DOCN", tmp_path, html=True)
    assert "123 input / 45 output (partial observed)" in path.read_text()
    html = (tmp_path / "complete_report.html").read_text()
    assert "123 input / 45 output (partial observed)" in html
    assert "123 input" in render_report("DOCN", state, None, [])
    assert "final_trade_decision" not in state

def test_disclosure_report_counts_do_not_merge_duplicate_model_and_source_claims():
    state = {"disclosure_evidence": {"submission_counts": {
        "model_accepted": 1, "model_rejected": 17,
        "deterministic_accepted": 15, "deterministic_rejected": 0,
    }}}
    text = reporting.evidence_appendix(state)
    assert "Model submissions: 1 accepted, 17 rejected" in text
    assert "Deterministic discovery: 15 accepted, 0 rejected" in text
    assert "may overlap" in text

def test_report_pairs_audit_findings_with_separate_advisory_pm_responses():
    from tradingagents.agents.audit_pass import prepare_audit_dispositions

    state = {"company_of_interest": "DOCN", "trade_date": "2026-11-06",
             "advisory_audit": {"status": "completed with findings",
                               "findings": [{"role": "market_analyst", "quoted_claim": "Example",
                                             "issue_type": "contradiction", "evidence_label": None,
                                             "explanation": "Example advisory finding"}]}}
    ident = prepare_audit_dispositions(state)["findings"][0]["finding_id"]
    state["unvalidated_outputs"] = {"portfolio_manager": {"structured": {
        "audit_dispositions": [{"finding_id": ident, "disposition": "rejected",
                               "reason": "The earlier analyst had a different source scope."}]}}}
    text = reporting.evidence_appendix(state)
    assert "The earlier analyst had a different source scope." in text
    assert ident in text
