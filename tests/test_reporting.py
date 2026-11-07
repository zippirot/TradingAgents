"""Report parity: the shared writer produces the report tree for the CLI and the
programmatic API alike (#1037)."""

import json
import re
from html import unescape
from types import SimpleNamespace

import pytest

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import write_report_tree


def _state():
    return {
        "market_report": "MKT",
        "news_report": "NEWS",
        "investment_debate_state": {"bull_history": "BULL"},
        "investment_plan": "RM PLAN",
        "trader_investment_plan": "TRADE",
        "risk_debate_state": {"neutral_history": "NEUTRAL"},
        "final_trade_decision": "PM DECISION",
    }


SETTINGS = {"version": "0.5.2", "llm_provider": "openai", "deep_think_llm": "gpt-6-sol",
            "quick_think_llm": "gpt-6-luna", "analysts": ["market", "news"], "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 2, "data_vendors": {"core_stock_apis": "yfinance"}}


@pytest.mark.unit
def test_write_report_tree_creates_files(tmp_path):
    out = write_report_tree(_state(), "AAPL", tmp_path)
    assert out.name == "complete_report.md"
    assert (tmp_path / "1_analysts" / "market.md").read_text() == "MKT"
    assert (tmp_path / "1_analysts" / "news.md").read_text() == "NEWS"
    assert (tmp_path / "2_research" / "manager.md").read_text() == "RM PLAN"
    assert (tmp_path / "3_trading" / "trader.md").read_text() == "TRADE"
    decision = (tmp_path / "5_portfolio" / "decision.md").read_text()
    assert decision.startswith("PM DECISION")
    assert "What the price implies" in decision and "Legacy evidence was not validated" in decision
    complete = out.read_text()
    assert "Trading Analysis Report: AAPL" in complete
    assert "MKT" in complete and "PM DECISION" in complete


@pytest.mark.unit
def test_save_reports_explicit_path(tmp_path):
    graph = SimpleNamespace(run_settings=lambda: SETTINGS)
    out = TradingAgentsGraph.save_reports(graph, _state(), "AAPL", save_path=tmp_path)
    assert (tmp_path / "complete_report.md").exists()
    assert out == tmp_path / "complete_report.md"


@pytest.mark.unit
def test_save_reports_defaults_under_results_dir(tmp_path):
    graph = object.__new__(TradingAgentsGraph)
    graph.config = {"results_dir": str(tmp_path)}
    graph.run_settings = lambda: SETTINGS
    out = graph.save_reports(_state(), "AAPL")
    assert out.exists()
    assert out.parent.parent.name == "reports"  # results_dir/reports/AAPL_<stamp>/...
    assert out.parent.name.startswith("AAPL_")



@pytest.mark.unit
def test_the_report_names_the_analysis_date_and_what_produced_it(tmp_path):
    state = dict(_state(), trade_date="2026-09-23")

    header = write_report_tree(state, "NVDA", tmp_path, settings=SETTINGS).read_text()

    assert "Analysis date: 2026-09-23" in header
    assert "TradingAgents 0.5.2" in header
    assert "openai, deep gpt-6-sol, quick gpt-6-luna" in header
    assert "Analysts: market, news" in header
    assert "research debate rounds 1, risk debate rounds 2" in header
    assert "core_stock_apis yfinance" in header


@pytest.mark.unit
def test_run_settings_record_the_run_without_endpoints_or_paths():
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = object.__new__(TradingAgentsGraph)
    graph.selected_analysts = ("market", "news")
    graph.config = {"llm_provider": "openai", "deep_think_llm": "gpt-6-sol", "quick_think_llm": "gpt-6-luna",
                    "max_debate_rounds": 1, "max_risk_discuss_rounds": 1, "output_language": "English",
                    "data_vendors": {"core_stock_apis": "yfinance"}, "tool_vendors": {},
                    "backend_url": "https://user:secret@relay.example/v1", "results_dir": "/home/me/results"}

    settings = graph.run_settings()

    assert settings["analysts"] == ["market", "news"]
    assert settings["deep_think_llm"] == "gpt-6-sol"
    assert "secret" not in str(settings) and "/home/me" not in str(settings)


@pytest.mark.unit
def test_a_partial_settings_dict_still_writes_the_report(tmp_path):
    out = write_report_tree(_state(), "AAPL", tmp_path, settings={"llm_provider": "openai"})
    assert "openai" in out.read_text()


@pytest.mark.unit
def test_run_settings_name_the_version_of_the_running_code():
    import tradingagents
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = object.__new__(TradingAgentsGraph)
    graph.selected_analysts, graph.config = ("market",), {}
    assert graph.run_settings()["version"] == tradingagents.__version__


@pytest.mark.unit
@pytest.mark.parametrize("decision, rating", [
    ("**Rating**: Overweight\n\nAdd on weakness.", "Overweight"),
    ("Add on weakness.", "REVIEW"),           # no readable rating is said, not left out
])
def test_the_report_header_names_the_rating(tmp_path, decision, rating):
    state = dict(_state(), final_trade_decision=decision)

    header = write_report_tree(state, "NVDA", tmp_path, settings=SETTINGS).read_text()

    assert f"- Rating: {rating}" in header


@pytest.mark.unit
def test_the_header_names_the_analysts_as_users_select_them(tmp_path):
    settings = {**SETTINGS, "analysts": ["market", "social", "news"]}

    write_report_tree(_state(), "NVDA", tmp_path, settings=settings, html=True)

    markdown = (tmp_path / "complete_report.md").read_text(encoding="utf-8")
    assert "market, sentiment, news" in markdown and "social" not in markdown
    page = (tmp_path / "complete_report.html").read_text(encoding="utf-8")
    fields = re.findall(r'<span class="field">([^<]*)</span>', page)
    assert {"market", "sentiment", "news"} <= set(fields) and "social" not in page


@pytest.mark.unit
def test_opening_and_contents_put_decision_first_without_losing_payloads(tmp_path):
    state = dict(_state(), trade_date="2026-11-06")
    write_report_tree(state, "DOCN", tmp_path, settings=SETTINGS)
    report = (tmp_path / "complete_report.md").read_text()
    headings = re.findall(r"^## ([IVX]+\. .+)$", report, flags=re.M)
    assert headings == [
        "I. Final Portfolio Decision", "II. Analyst Team Reports",
        "III. Research Team Decision", "IV. Trading Team Plan",
        "V. Risk Management Team Decision", "VI. Evidence and Quality",
    ]
    assert report.index("# Trading Analysis Report") < report.index("Analysis date: 2026-11-06")
    assert report.index("## Executive summary") < report.index("## Table of contents")
    assert report.index("## Table of contents") < report.index("- Rating:")
    for payload in ("MKT", "NEWS", "BULL", "RM PLAN", "TRADE", "NEUTRAL", "PM DECISION"):
        assert payload in report
    assert (tmp_path / "5_portfolio" / "decision.md").read_text().startswith("PM DECISION")


@pytest.mark.unit
def test_partial_report_retains_historical_positional_anchors(tmp_path):
    # Before reordering, this partial report had analysts=s1, portfolio=s2,
    # evidence=s3. Its saved links remain usable after decision-first display.
    state = {"market_report": "MARKET", "final_trade_decision": "Rating: Hold. Maintain exposure."}
    write_report_tree(state, "DOCN", tmp_path)
    markdown = (tmp_path / "complete_report.md").read_text()
    html = (tmp_path / "complete_report.html").read_text()
    assert markdown.index('<a id="s2"></a>') < markdown.index('<a id="s1"></a>') < markdown.index('<a id="s3"></a>')
    assert html.index('<section id="s2">') < html.index('<section id="s1">') < html.index('<section id="s3">')
    assert 'href="#s2"' in html and 'href="#s1"' in html and 'href="#s3"' in html
    assert 'href="#s2-1"' in html and 'id="s2-1"' in html


@pytest.mark.unit
def test_stale_summary_is_not_displayed_but_its_bounded_record_is_kept(tmp_path):
    stale = {
        "schema_version": 1, "status": "completed", "source_input_digest": "a" * 64,
        "process": "Old process.", "sentences": ["Old rating explanation.", "Old market view.",
            "Old research view.", "Old portfolio view.", "Old evidence limit."],
        "body_items": [
            {"text": "Old market view.", "sections": ["1_analysts"]},
            {"text": "Old research view.", "sections": ["2_research"]},
            {"text": "Old portfolio view.", "sections": ["5_portfolio"]},
        ], "generation_model": "old-model", "truncation": {},
        "error_category": None, "elapsed_ms": 7, "api_key": "must-not-export",
    }
    state = dict(_state(), final_trade_decision="Rating: Hold. Maintain exposure.", executive_summary=stale)
    write_report_tree(state, "DOCN", tmp_path)
    markdown = (tmp_path / "complete_report.md").read_text()
    html = (tmp_path / "complete_report.html").read_text()
    companion = json.loads((tmp_path / "executive_summary.json").read_text())
    assert "Old rating explanation" not in markdown and "Old rating explanation" not in html
    assert "retained summary is stale" in markdown and "retained summary is stale" in html
    assert companion["source_input_digest"] == "a" * 64
    assert companion["sentences"][0] == "Old rating explanation."
    assert "api_key" not in companion and "must-not-export" not in str(companion)


@pytest.mark.unit
def test_retained_run_settings_win_over_export_call_settings(tmp_path):
    state = dict(_state(), run_settings={**SETTINGS, "deep_think_llm": "retained-model"})
    write_report_tree(state, "DOCN", tmp_path, settings={**SETTINGS, "deep_think_llm": "wrong-model"})
    markdown = (tmp_path / "complete_report.md").read_text()
    html = (tmp_path / "complete_report.html").read_text()
    assert "retained-model" in markdown and "retained-model" in html
    assert "wrong-model" not in markdown and "wrong-model" not in html


@pytest.mark.unit
def test_contents_links_target_emitted_sections_and_agents(tmp_path):
    write_report_tree(_state(), "DOCN", tmp_path)
    markdown = (tmp_path / "complete_report.md").read_text()
    html = (tmp_path / "complete_report.html").read_text()
    for target in re.findall(r"\]\(#(s\d+(?:-\d+)?)\)", markdown):
        assert f'<a id="{target}"></a>' in markdown
        assert f'id="{target}"' in html
    nav = html[html.index('<nav class="contents"'):html.index("</nav>")]
    for target in re.findall(r'href="#(s\d+(?:-\d+)?)"', nav):
        assert f'id="{target}"' in html


@pytest.mark.unit
def test_token_footer_names_research_scope_in_both_exports(tmp_path):
    metrics = {"input_tokens": 123, "output_tokens": 45, "token_usage_scope": "complete_observed"}
    write_report_tree(dict(_state(), run_metrics=metrics), "DOCN", tmp_path)
    markdown = (tmp_path / "complete_report.md").read_text()
    html = (tmp_path / "complete_report.html").read_text()
    for text in (markdown, html):
        assert "123 input / 45 output (complete observed)" in text
        assert "These counts cover the research graph only" in text
        assert "editorial summary generation" in text


@pytest.mark.unit
def test_custom_language_companion_round_trips_without_extra_fields(tmp_path):
    from tests.test_report_summary import FakeLLM, valid_payload
    from tradingagents.report_summary import generate_summary, resolve_summary
    from tradingagents.reporting import prepare_report_state, summary_input_for_report

    settings = {**SETTINGS, "output_language": "Italian"}
    state = dict(_state(), final_trade_decision="Rating: Underweight. Reduce exposure.")
    payload = valid_payload()
    framing = {
        "process": "Sono stati completati i rapporti degli analisti. La decisione finale è stata presa dopo il dibattito e i controlli.",
        "rating_definition": "Underweight significa ridurre l'esposizione sotto l'allocazione normale.",
        "evidence_limit": "Le prove sono limitate; non esiste un obiettivo finale di prezzo supportato e gli scenari sono condizionali.",
    }
    payload["framing"] = framing
    context = summary_input_for_report(prepare_report_state(state), settings)
    record = generate_summary(context, FakeLLM(payload))
    assert record["status"] == "completed"
    state["executive_summary"] = {**record, "api_key": "must-not-export"}
    write_report_tree(state, "DOCN", tmp_path, settings=settings)
    companion = json.loads((tmp_path / "executive_summary.json").read_text())
    # The export retains valid saved framing while removing unknown fields.
    assert companion["framing"] == framing
    assert "must-not-export" not in str(companion)
    shown = resolve_summary(context, companion)
    assert shown["status"] == "completed"
    markdown = (tmp_path / "complete_report.md").read_text()
    html = (tmp_path / "complete_report.html").read_text()
    assert framing["process"] in markdown and framing["process"] in html
    assert framing["rating_definition"] in markdown and framing["rating_definition"] in unescape(html)
    malformed = dict(state, executive_summary={**record, "framing": {**framing, "api_key": "nested-secret"}})
    write_report_tree(malformed, "DOCN", tmp_path / "malformed", settings=settings)
    sidecar = (tmp_path / "malformed" / "executive_summary.json").read_text()
    assert "nested-secret" not in sidecar
