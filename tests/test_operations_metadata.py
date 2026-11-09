"""Run usage and provenance are explicit, bounded, and retained in exports."""

import io

import pytest

from cli import updates
from cli.stats_handler import StatsCallbackHandler, render_usage_cost
from tradingagents import default_config, report_html, reporting


@pytest.mark.unit
def test_cost_line_prints_only_with_configured_prices():
    stats = {"tokens_in": 1_000_000, "tokens_out": 500_000,
             "token_usage_scope": "complete_observed"}
    assert render_usage_cost(stats, {}) == "Tokens: 1,000,000 in / 500,000 out (complete observed)"
    text = render_usage_cost(stats, {"input_cost_per_million": "2", "output_cost_per_million": "4"})
    assert "Tokens: 1,000,000 in / 500,000 out (complete observed)" in text
    assert "$4.000000" in text and "not a billing total" in text


@pytest.mark.unit
@pytest.mark.parametrize("prices", [
    {"input_cost_per_million": "2"},
    {"input_cost_per_million": "2", "output_cost_per_million": ""},
    {"input_cost_per_million": "-1", "output_cost_per_million": "4"},
    {"input_cost_per_million": "NaN", "output_cost_per_million": "4"},
    {"input_cost_per_million": "2", "output_cost_per_million": "Infinity"},
    {"input_cost_per_million": "1e999999999", "output_cost_per_million": "4"},
])
def test_invalid_or_incomplete_prices_do_not_produce_estimate(prices):
    text = render_usage_cost({"tokens_in": 3, "tokens_out": 2,
                              "token_usage_scope": "complete_observed"}, prices)
    assert "Tokens: 3 in / 2 out" in text and "$" not in text


@pytest.mark.unit
def test_partial_usage_estimate_names_observed_only_and_missing_usage_is_unavailable():
    prices = {"input_cost_per_million": "2", "output_cost_per_million": "4"}
    partial = render_usage_cost({"tokens_in": 3, "tokens_out": 2,
                                 "token_usage_scope": "partial_observed"}, prices)
    assert "partial observed" in partial and "observed tokens only" in partial
    assert "whole run" in partial
    unavailable = render_usage_cost({"tokens_in": 0, "tokens_out": 0,
                                     "token_usage_scope": "unavailable"}, prices)
    assert "unavailable" in unavailable and "0 in" not in unavailable and "$" not in unavailable


@pytest.mark.unit
def test_stats_scope_distinguishes_complete_partial_and_unavailable():
    stats = StatsCallbackHandler()
    assert stats.get_stats()["token_usage_scope"] == "unavailable"
    stats.on_llm_start({}, ["prompt"])
    stats.token_usage_calls = 1
    stats.tokens_in, stats.tokens_out = 3, 2
    assert stats.get_stats()["token_usage_scope"] == "complete_observed"
    stats.on_llm_start({}, ["second"])
    assert stats.get_stats()["token_usage_scope"] == "partial_observed"


@pytest.mark.unit
def test_price_env_config_defaults_to_empty_and_preserves_values(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_INPUT_COST_PER_MILLION", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_OUTPUT_COST_PER_MILLION", raising=False)
    config = default_config.build_default_config()
    assert config["input_cost_per_million"] == config["output_cost_per_million"] == ""
    monkeypatch.setenv("TRADINGAGENTS_INPUT_COST_PER_MILLION", "2.50")
    monkeypatch.setenv("TRADINGAGENTS_OUTPUT_COST_PER_MILLION", "8")
    config = default_config.build_default_config()
    assert (config["input_cost_per_million"], config["output_cost_per_million"]) == ("2.50", "8")


@pytest.mark.unit
@pytest.mark.parametrize("raw,expected", [("0", True), ("1", False), ("false", True), ("true", False)])
def test_no_update_check_zero_means_enabled(monkeypatch, raw, expected):
    monkeypatch.setattr("sys.stdin", io.StringIO())
    monkeypatch.setattr("sys.stdout", io.StringIO())
    monkeypatch.setattr(updates.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(updates.sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv(updates.OPT_OUT, raw)
    assert updates.enabled() is expected


@pytest.mark.unit
def test_report_uses_retained_source_hash_and_effort_in_both_formats():
    old = {"llm_provider": "openrouter", "deep_think_llm": "anthropic/claude",
           "quick_think_llm": "openai/gpt", "source_hash": "old-source-hash",
           "openai_reasoning_effort": "high", "anthropic_effort": "low",
           "google_thinking_level": "minimal"}
    current = {**old, "source_hash": "new-source-hash", "openai_reasoning_effort": "low"}
    state = {"run_settings": old}
    header = reporting._header("DOCN", state, state["run_settings"])
    page = report_html.render_report("DOCN", state, current)
    for output in (header, page):
        assert "old-source-hash" in output and "new-source-hash" not in output
        assert "high" in output and "minimal" in output
        assert "Git SHA" not in output
