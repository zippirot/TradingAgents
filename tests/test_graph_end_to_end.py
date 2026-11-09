"""The whole graph, end to end, with scripted models and no network.

Every tool-using analyst calls each of its tools once through the vendor router,
the debates and managers run, and the decision is parsed and logged. This pins
the wiring: a restructure that drops a node, a tool or an edge fails here.
"""

from __future__ import annotations

import copy
import json
import time

import pandas as pd
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import Field

from tradingagents.agents import context, schemas
from tradingagents.agents.analysts import sentiment_analyst
from tradingagents.dataflows import router
from tradingagents.dataflows.vendors.yahoo import market as yahoo_market, snapshot
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph import trading_graph

TRADE_DATE = "2026-01-09"

# Enough for every free-text reader: the PM's labelled rating and the trader's
# closing proposal line.
TEXT = "Report.\n\n**Rating**: Overweight\n\nFINAL TRANSACTION PROPOSAL: **BUY**"

STRUCTURED = {
    schemas.ResearchPlan: schemas.ResearchPlan(
        recommendation=schemas.PortfolioRating.OVERWEIGHT, rationale="r", strategic_actions="a"),
    schemas.TraderProposal: schemas.TraderProposal(action=schemas.TraderAction.BUY, reasoning="r"),
    # The thesis quotes another party's rating; the decision is still the PM's own.
    schemas.PortfolioDecision: schemas.PortfolioDecision(
        rating=schemas.PortfolioRating.OVERWEIGHT, executive_summary="s",
        investment_thesis="Street consensus rating: Buy (28 of 35 analysts)."),
    schemas.SentimentReport: schemas.SentimentReport(
        overall_band=schemas.SentimentBand.NEUTRAL, overall_score=5.0, confidence="low", narrative="n"),
}

STRUCTURED[schemas.RequiredHorizonPortfolioDecision] = schemas.RequiredHorizonPortfolioDecision(
    **{**STRUCTURED[schemas.PortfolioDecision].model_dump(), "time_horizon": "3–6 months"}
)

ARGS = {"symbol": "NVDA", "ticker": "NVDA", "curr_date": TRADE_DATE, "start_date": "2026-01-02",
        "end_date": TRADE_DATE, "indicator": "rsi", "topic": "Fed rate cut", "freq": "quarterly"}


class ScriptedModel(BaseChatModel):
    """Calls every bound tool once, then answers with TEXT."""

    structured: bool = False
    tools: tuple = ()
    calls: list = Field(default_factory=list)   # shared across bound copies
    threads: set = Field(default_factory=set)   # threads that served a tool-bound call
    fail_at: int | None = None                  # raise on this call, once

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self.model_copy(update={"tools": tuple(tools)})

    def with_structured_output(self, schema, **kwargs):
        if not self.structured:
            raise NotImplementedError
        return RunnableLambda(lambda _: self._count() or STRUCTURED[schema])

    def _count(self) -> None:
        self.calls.append(1)
        if len(self.calls) == self.fail_at:
            raise RuntimeError("provider unavailable")

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self._count()
        if self.tools:
            import threading
            import time
            self.threads.add(threading.current_thread().name)
            time.sleep(0.05)   # long enough for concurrent analysts to overlap
        if self.tools and not isinstance(messages[-1], ToolMessage):
            calls = [{"name": t.name, "id": f"call_{i}",
                      "args": {k: v for k, v in ARGS.items()
                               if k in t.tool_call_schema.model_json_schema()["properties"]}}
                     for i, t in enumerate(self.tools)]
            message = AIMessage(content="", tool_calls=calls)
        else:
            message = AIMessage(content=TEXT)
        return ChatResult(generations=[ChatGeneration(message=message)])


class _Client:
    def __init__(self, model):
        self.model = model

    def get_llm(self):
        return self.model


@pytest.fixture
def offline(monkeypatch, tmp_path):
    """Every vendor answers offline; returns the set of router methods called."""
    # These graph/stream/recovery fixtures supply generic vendor strings, not
    # SEC financial evidence. Their directional path leaves fundamentals unselected.
    from tradingagents.dataflows.vendors import sec_documents, sec_edgar
    monkeypatch.setattr(sec_edgar, "cik_for", lambda ticker: None)
    monkeypatch.setattr(sec_documents, "cik_for", lambda ticker: None)
    from tradingagents.dataflows.vendors.yahoo import price_observation
    monkeypatch.setattr(price_observation, "get_price_observation",
                        lambda *a, **k: {"status": "unavailable", "reason": "Legacy graph fixture has no dated price"})
    called: set[str] = set()
    for method, vendors in router.VENDOR_METHODS.items():
        for vendor in vendors:
            monkeypatch.setitem(vendors, vendor,
                                lambda *a, _m=method, **k: called.add(_m) or f"{_m} data")
    prices = pd.DataFrame({
        "Date": pd.bdate_range(end=TRADE_DATE, periods=60),
        "Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1_000_000,
    })
    monkeypatch.setattr(snapshot, "load_ohlcv",
                        lambda *a, **k: called.add("ohlcv") or prices.copy())
    monkeypatch.setattr(sentiment_analyst, "fetch_stocktwits_messages", lambda *a, **k: "no posts")
    monkeypatch.setattr(sentiment_analyst, "fetch_reddit_posts", lambda *a, **k: "no posts")
    monkeypatch.setattr(yahoo_market.yf, "Ticker", lambda s: type("T", (), {"info": {"longName": "NVIDIA"}})())
    context._identity.cache_clear()
    return called


def _graph(tmp_path, monkeypatch, model, debug=False, *, selected_analysts=("market", "social", "news"), **config):
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg.update(results_dir=str(tmp_path / "results"), data_cache_dir=str(tmp_path / "cache"),
               memory_log_path=str(tmp_path / "log.md"), **config)
    monkeypatch.setattr(trading_graph, "create_tier_client", lambda config, tier, **k: _Client(model))
    return trading_graph.TradingAgentsGraph(config=cfg, debug=debug, selected_analysts=selected_analysts)


@pytest.mark.unit
@pytest.mark.parametrize("structured", [False, True], ids=["free-text", "structured"])
def test_a_full_run_reaches_a_logged_decision(tmp_path, monkeypatch, offline, structured):
    graph = _graph(tmp_path, monkeypatch, ScriptedModel(structured=structured))

    state, signal = graph.propagate("NVDA", TRADE_DATE)

    assert signal == state["final_rating"] == "Overweight"
    assert state["evidence_quality"]["scope"] == "not_applicable"
    for key in ("market_report", "sentiment_report", "news_report",
                "investment_plan", "trader_investment_plan", "final_trade_decision"):
        assert state[key].strip(), key
    tool_methods = {"get_stock_data", "get_indicators", "get_news", "get_global_news",
                    "get_macro_indicators", "get_prediction_markets",
                    "ohlcv"}
    assert offline == tool_methods
    assert state["news_coverage"]["independent_news"]["status"] == "available"
    assert state["news_coverage"]["optional_macro"]["status"] == "available"
    assert [e["rating"] for e in graph.memory_log.load_entries()] == ["Overweight"]


@pytest.mark.unit
@pytest.mark.parametrize("finish_location", ["response_metadata", "generation_info"])
def test_truncated_analyst_report_reaches_next_research_prompt(tmp_path, monkeypatch, offline, finish_location):
    class TruncatedAnalystModel(ScriptedModel):
        prompts: list = Field(default_factory=list)

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            self.prompts.append(str(messages))
            result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            if self.tools and isinstance(messages[-1], ToolMessage):
                if finish_location == "generation_info":
                    result.generations[0].generation_info = {"finish_reason": "length"}
                else:
                    result.generations[0].message.response_metadata["finish_reason"] = "length"
            return result

    model = TruncatedAnalystModel(structured=True)
    state, _ = _graph(tmp_path, monkeypatch, model).propagate("NVDA", TRADE_DATE)
    assert "Model output truncated by provider" in state["market_report"]
    assert any("Model output truncated by provider" in prompt for prompt in model.prompts)
    truncated = [row for row in state["operational_observations"].values()
                 if row["code"] == "model_output_truncated"]
    assert truncated and all(row.get("count", 1) == 1 for row in truncated)


@pytest.mark.unit
def test_an_interrupted_run_resumes_from_its_checkpoint(tmp_path, monkeypatch, offline):
    model = ScriptedModel(fail_at=10)            # past the analysts, before the decision
    graph = _graph(tmp_path, monkeypatch, model, checkpoint_enabled=True)
    with pytest.raises(RuntimeError, match="provider unavailable"):
        graph.propagate("NVDA", TRADE_DATE)
    calls_before = len(model.calls)

    _, signal = graph.propagate("NVDA", TRADE_DATE)

    assert signal == "Overweight"
    resumed_calls = len(model.calls) - calls_before
    full_run = ScriptedModel()
    _graph(tmp_path / "fresh", monkeypatch, full_run).propagate("NVDA", TRADE_DATE)
    # The resumed run makes only the calls the interrupted one had not completed.
    assert resumed_calls == len(full_run.calls) - (model.fail_at - 1)


@pytest.mark.unit
def test_a_graph_reused_across_runs_keeps_no_run_state(tmp_path, monkeypatch, offline):
    """A backtest reuses one graph over its whole grid; holding every run's full
    state would grow without bound."""
    graph = _graph(tmp_path, monkeypatch, ScriptedModel())
    for trade_date in ("2026-01-08", TRADE_DATE):
        graph.propagate("NVDA", trade_date)

    held = [v for v in vars(graph).values() if isinstance(v, dict) and TRADE_DATE in v]
    assert held == []
    logs = list(tmp_path.glob("results/NVDA/TradingAgentsStrategy_logs/*.json"))
    assert len(logs) == 4  # One per-run archive and one latest file for each analysis date.
    for trade_date in ("2026-01-08", TRADE_DATE):
        latest = next(path for path in logs if path.name == f"full_states_log_{trade_date}.json")
        saved = json.loads(latest.read_text())
        archive = latest.with_name(f"full_states_log_{trade_date}_{saved['run_id'][:8]}.json")
        assert json.loads(archive.read_text()) == saved


@pytest.mark.unit
def test_the_analysts_run_at_the_same_time(tmp_path, monkeypatch, offline):
    model = ScriptedModel()
    graph = _graph(tmp_path, monkeypatch, model)

    assert not [n for n in graph.graph.get_graph().nodes if n.startswith("Msg Clear")]
    graph.propagate("NVDA", TRADE_DATE)

    assert len(model.threads) > 1


@pytest.mark.unit
def test_a_debug_run_prints_the_analysts_work_and_reaches_the_same_decision(tmp_path, monkeypatch, offline, capsys):
    """Debug mode streams the analysts' own graphs, so their tool calls still print."""
    graph = _graph(tmp_path, monkeypatch, ScriptedModel(), debug=True)

    state, signal = graph.propagate("NVDA", TRADE_DATE)

    assert signal == "Overweight"
    assert state["market_report"].strip() and state["news_report"].strip()
    printed = capsys.readouterr().out
    assert "get_stock_data" in printed and "get_news" in printed


@pytest.mark.unit
def test_each_report_streams_as_soon_as_its_analyst_files_it(tmp_path, monkeypatch, offline):
    """The main state takes the analysts' reports only when the slowest one is
    done; the CLI shows each report, and stops each clock, as it lands."""
    graph = _graph(tmp_path, monkeypatch, ScriptedModel())
    reports = ("market_report", "sentiment_report", "news_report")

    first = next(state for _, state in graph.stream_run(graph.create_run_state("NVDA", TRADE_DATE),
                                                        **graph.propagator.get_graph_args())
                 if state and any(state.get(k) for k in reports))

    assert sum(bool(first.get(k)) for k in reports) == 1


@pytest.mark.unit
def test_a_streamed_run_reads_its_own_graph_config(tmp_path, monkeypatch, offline):
    """The CLI streams the run; a process-wide config set elsewhere must not reach
    its tools, and the graph's config must not reach the caller between steps."""
    from tradingagents.dataflows.config import get_config, set_config

    graph = _graph(tmp_path, monkeypatch, ScriptedModel(), output_language="French")
    set_config({"output_language": "German"})
    seen = []
    monkeypatch.setitem(router.VENDOR_METHODS["get_stock_data"], "yfinance",
                        lambda *a, **k: seen.append(get_config()["output_language"]) or "prices")

    between = [get_config()["output_language"]
               for _ in graph.stream_run(graph.create_run_state("NVDA", TRADE_DATE), **graph.propagator.get_graph_args())]

    assert seen and set(seen) == {"French"}
    assert set(between) == {"German"}


class LoopingModel(ScriptedModel):
    """Calls a tool on every turn it is offered one (#1420)."""

    tool_turns: list = Field(default_factory=list)    # shared across bound copies
    last_turns: list = Field(default_factory=list)    # histories of the turns offered no tools

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if not self.tools:
            self.last_turns.append(messages)
            return super()._generate(messages, stop, run_manager, **kwargs)
        self.tool_turns.append(1)
        tool = self.tools[0]
        call = {"name": tool.name, "id": f"call_{len(self.tool_turns)}",
                "args": {k: v for k, v in ARGS.items()
                         if k in tool.tool_call_schema.model_json_schema()["properties"]}}
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[call]))])


@pytest.mark.unit
def test_an_analyst_that_keeps_calling_tools_writes_its_report_at_the_limit(tmp_path, monkeypatch, offline):
    """A model that does not stop calling tools must not end the run (#1420)."""
    model = LoopingModel(structured=True)
    graph = _graph(tmp_path, monkeypatch, model, max_tool_rounds=3)

    final_state, rating = graph.propagate("NVDA", TRADE_DATE)

    assert len(model.tool_turns) == 2 * 3   # two tool-using analysts, three rounds each
    for key in ("market_report", "news_report"):
        assert final_state["unvalidated_outputs"][key].endswith(TEXT)
        analyst = "market" if key == "market_report" else "news"
        assert final_state["unvalidated_outputs"][key].startswith(
            "Warning: requested tool calls supplied no support") is final_state[
                f"audit_{analyst}_tool_evidence"]["all_tools_failed"]
        assert final_state[key].startswith("**Unvalidated model narrative")
    assert rating == "Overweight"


@pytest.mark.unit
def test_the_last_turn_is_offered_no_tools_and_reads_its_tool_results_as_text(tmp_path, monkeypatch, offline):
    """Offered tools, a model may call one whatever it is told; a history holding
    tool calls may be refused by a provider when no tools are bound."""
    model = LoopingModel(structured=True)
    graph = _graph(tmp_path, monkeypatch, model, max_tool_rounds=2)

    graph.propagate("NVDA", TRADE_DATE)

    wrap_ups = [h for h in model.last_turns if isinstance(h[-1], HumanMessage) and "tool round" in h[-1].content]
    assert len(wrap_ups) == 2
    for history in wrap_ups:
        assert not any(isinstance(m, ToolMessage) or getattr(m, "tool_calls", None) for m in history)
        assert any("returned]" in str(m.content) for m in history)
        assert "tool rounds are spent" in history[0].content   # the system prompt lists no tools


@pytest.mark.unit
def test_a_tool_limit_the_recursion_limit_cannot_hold_is_refused(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="max_tool_rounds"):
        _graph(tmp_path, monkeypatch, ScriptedModel(), max_tool_rounds=60, max_recur_limit=100)


class TimedModel(ScriptedModel):
    """ScriptedModel that records each call's graph step, prompt and timing."""

    seen: list = Field(default_factory=list)    # shared across bound copies

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        step = (run_manager.metadata or {}).get("langgraph_node") if run_manager else None
        started = time.monotonic()
        if step in {"Market Analyst", "agent"} or step == "Memory Log":
            time.sleep(0.2)                     # long enough to see what overlaps
        result = super()._generate(messages, stop, run_manager, **kwargs)
        prompt = "\n".join(str(m.content) for m in messages)
        self.seen.append((step, prompt, started, time.monotonic()))
        return result


@pytest.mark.unit
def test_past_decisions_settle_alongside_the_analysts(tmp_path, monkeypatch, offline):
    from tradingagents.memory import settlement

    model = TimedModel()
    graph = _graph(tmp_path, monkeypatch, model)
    graph.memory_log.store_decision("NVDA", "2025-12-31", "Rating: Buy\n\nBuy NVDA.")
    closes = pd.Series([100.0 + i for i in range(10)], index=pd.bdate_range("2026-01-02", periods=10))
    monkeypatch.setattr(settlement, "get_closes", lambda *a, **k: closes)

    graph.propagate("NVDA", TRADE_DATE)

    reflections = [c for c in model.seen if c[0] == "Memory Log"]
    assert len(reflections) == 1                # settled once, inside the run
    analyst_turns = [c for c in model.seen if c[0] == "agent"]
    assert reflections[0][2] < max(c[3] for c in analyst_turns), "settled before the analysts, not alongside"
    settled = next(e for e in graph.memory_log.load_entries() if e["date"] == "2025-12-31")
    assert not settled["pending"]
    lessons = graph.memory_log.get_past_context("NVDA", as_of=TRADE_DATE)
    assert lessons
    pm_prompt = next(c[1] for c in model.seen if c[0] == "Portfolio Manager")
    # This reflection was persisted during the present run, long after the
    # historical analysis date. It cannot become hindsight context.
    assert lessons not in pm_prompt


@pytest.mark.unit
def test_a_settlement_failure_is_noted_and_the_run_goes_on(tmp_path, monkeypatch, offline):
    """The analysts have spent their tokens by the time the join waits on settlement."""
    from tradingagents.reporting import write_report_tree

    graph = _graph(tmp_path, monkeypatch, ScriptedModel(structured=True))

    def locked():
        raise OSError("memory log is locked")

    monkeypatch.setattr(graph, "settle_all_pending", locked)
    final_state, rating = graph.propagate("NVDA", TRADE_DATE)

    assert rating == "Overweight"
    assert "could not be settled" in final_state["memory_note"]
    report = write_report_tree(final_state, "NVDA", tmp_path / "report").read_text()
    assert "Memory log: Past decisions could not be settled" in report


@pytest.mark.unit
def test_the_run_settles_other_tickers_due_decisions_too(tmp_path, monkeypatch, offline):
    """A ticker a scheduler stopped analysing still gets its decisions settled (#1445)."""
    from tradingagents.memory import settlement

    graph = _graph(tmp_path, monkeypatch, ScriptedModel(structured=True))
    graph.memory_log.store_decision("MSFT", "2026-01-02", "Rating: Buy\n\nBuy MSFT.")
    closes = pd.Series([100.0 + i for i in range(10)], index=pd.bdate_range("2026-01-02", periods=10))
    monkeypatch.setattr(settlement, "get_closes", lambda *a, **k: closes)

    graph.propagate("NVDA", TRADE_DATE)

    msft = next(e for e in graph.memory_log.load_entries() if e["ticker"] == "MSFT")
    assert not msft["pending"]


@pytest.mark.unit
def test_the_memory_step_reads_lessons_as_of_the_trade_date_and_settles_once(tmp_path, monkeypatch, offline):
    """A past-dated run reads only lessons known by its date (#1251); a resumed run
    that re-runs the step settles nothing twice."""
    from tradingagents.memory import settlement

    graph = _graph(tmp_path, monkeypatch, ScriptedModel(structured=True))
    graph.memory_log.store_decision("NVDA", "2025-12-31", "Rating: Buy\n\nBuy NVDA.")
    closes = pd.Series([100.0 + i for i in range(10)], index=pd.bdate_range("2026-01-02", periods=10))
    monkeypatch.setattr(settlement, "get_closes", lambda *a, **k: closes)
    asked = []
    real = graph.memory_log.get_past_context
    monkeypatch.setattr(graph.memory_log, "get_past_context",
                        lambda ticker, as_of=None, **k: asked.append(as_of) or real(ticker, as_of=as_of, **k))
    state = {"company_of_interest": "NVDA", "trade_date": "2026-01-20"}

    graph._memory_step(state)
    log_after_first = (tmp_path / "log.md").read_text()
    graph._memory_step(state)

    assert asked == ["2026-01-21T06:59:59.999999+00:00"] * 2
    assert (tmp_path / "log.md").read_text() == log_after_first


def test_critical_source_failure_saves_readable_review_state(tmp_path, monkeypatch, offline):
    import json

    from tradingagents.dataflows.errors import VendorUnavailableError
    from tradingagents.dataflows.vendors import sec_edgar

    def unavailable(ticker):
        raise VendorUnavailableError("SEC source unavailable in controlled proof dummy-secret-987")

    monkeypatch.setattr(sec_edgar, "cik_for", unavailable)
    graph = _graph(tmp_path, monkeypatch, ScriptedModel(),
                   selected_analysts=("market", "social", "news", "fundamentals"))
    state, signal = graph.propagate("NVDA", TRADE_DATE)
    assert signal == "REVIEW"
    assert state["investment_plan"] == state["trader_investment_plan"] == ""
    assert "SEC unavailable" in state["final_trade_decision"]
    assert "dummy-secret-987" not in str(state)
    path = tmp_path / "results/NVDA/TradingAgentsStrategy_logs" / f"full_states_log_{TRADE_DATE}.json"
    saved = json.loads(path.read_text())
    assert "dummy-secret-987" not in str(saved)
    assert saved["final_rating"] == "REVIEW"
    assert saved["fundamentals_report"]
    assert saved["investment_debate_state"]["history"] == ""


def test_shared_scenarios_precede_debate_and_preserve_call_count(tmp_path, monkeypatch, offline):
    from tests.test_shared_valuation import state as scenario_state
    from tests.test_valuation import pe_request
    from tradingagents.graph import setup

    evidence = scenario_state([{"name": "Shared graph case", "request": pe_request()}])
    seen = []
    original_bull = setup.create_bull_researcher

    def bull_factory(llm):
        node = original_bull(llm)

        def checked(state):
            seen.append(copy.deepcopy(state["shared_valuation_scenarios"]))
            return node(state)
        return checked

    monkeypatch.setattr(setup, "create_bull_researcher", bull_factory)
    monkeypatch.setattr(setup, "create_evidence_gate", lambda selected: lambda state: {
        key: value for key, value in evidence.items()
        if key in {"financial_evidence", "financial_claim_validation", "evidence_quality"}
    })
    model = ScriptedModel(structured=True)
    graph = _graph(tmp_path, monkeypatch, model)
    final, _ = graph.propagate("DOCN", evidence["trade_date"])
    assert seen and seen[0]["rows"][0]["result"]["target"] == "40"
    assert all(record == seen[0] for record in seen)
    assert final["shared_valuation_scenarios"]["rows"] == seen[0]["rows"]
    assert final["target_validation"]["target"] is None
    count = len(model.calls)

    # Same graph/agents with no optional scenarios should make exactly as many calls.
    evidence["financial_claim_validation"]["raw_report"] = "No scenario proposals"
    seen.clear()
    baseline_model = ScriptedModel(structured=True)
    baseline = _graph(tmp_path / "without", monkeypatch, baseline_model)
    missing, _ = baseline.propagate("DOCN", evidence["trade_date"])
    assert missing["shared_valuation_scenarios"]["status"] == "unavailable"
    assert len(baseline_model.calls) == count


def test_shared_scenarios_survive_checkpoint_without_recalculation(tmp_path, monkeypatch, offline):
    import json

    from tests.test_shared_valuation import state as scenario_state
    from tests.test_valuation import pe_request
    from tradingagents.graph import setup
    from tradingagents.graph.checkpointer import thread_id

    evidence = scenario_state([{"name": "Recovered case", "request": pe_request()}])
    original_bull = setup.create_bull_researcher
    seen, gate_calls = [], []

    def gate(state):
        gate_calls.append(1)
        return {key: value for key, value in evidence.items()
                if key in {"financial_evidence", "financial_claim_validation", "evidence_quality"}}

    def bull_factory(llm):
        node = original_bull(llm)

        def interrupted(state):
            seen.append(copy.deepcopy(state["shared_valuation_scenarios"]))
            if len(seen) == 1:
                raise RuntimeError("controlled post-evidence interruption")
            return node(state)
        return interrupted

    monkeypatch.setattr(setup, "create_evidence_gate", lambda selected: gate)
    monkeypatch.setattr(setup, "create_bull_researcher", bull_factory)
    graph = _graph(tmp_path, monkeypatch, ScriptedModel(structured=True), checkpoint_enabled=True)
    signature = graph._run_signature("stock")
    assert "shared_valuation=7" in signature
    legacy = signature.replace("|shared_valuation=7", "")
    assert legacy != signature
    assert thread_id("DOCN", evidence["trade_date"], legacy) != thread_id("DOCN", evidence["trade_date"], signature)
    with pytest.raises(RuntimeError, match="controlled post-evidence"):
        graph.propagate("DOCN", evidence["trade_date"])
    final, _ = graph.propagate("DOCN", evidence["trade_date"])
    assert len(gate_calls) == 1
    assert seen[0]["rows"] and all(record == seen[0] for record in seen)
    assert final["shared_valuation_scenarios"] == seen[0]
    path = next((tmp_path / "results/DOCN/TradingAgentsStrategy_logs").glob("full_states_log_*.json"))
    assert json.loads(path.read_text())["shared_valuation_scenarios"] == seen[0]


@pytest.mark.parametrize("interrupt_role", ["research", "trader"])
def test_revision_checkpoint_preserves_exact_cases_before_and_after_manager(
    tmp_path, monkeypatch, offline, interrupt_role
):
    from tests.test_case_valuation import revenue_case
    from tests.test_shared_valuation import state as scenario_state
    from tradingagents.graph import setup

    original = revenue_case()
    revised = copy.deepcopy(original)
    revised["request"]["multiple"] = "4"
    evidence = scenario_state([original])
    monkeypatch.setattr(setup, "create_evidence_gate", lambda selected: lambda state: {
        k: evidence[k] for k in ("financial_evidence", "financial_claim_validation", "evidence_quality")})
    monkeypatch.setitem(STRUCTURED, schemas.ResearchPlan, STRUCTURED[schemas.ResearchPlan].model_copy(
        update={"revised_cases": [revised]}))
    original_manager, original_trader = setup.create_research_manager, setup.create_trader
    completed_manager = []
    interrupted = []

    def wrap(factory, role):
        def factory_with_interrupt(llm):
            node = factory(llm)

            def run(state):
                if role == interrupt_role and not interrupted:
                    interrupted.append(copy.deepcopy(state["shared_valuation_scenarios"]))
                    raise RuntimeError("controlled revision checkpoint interruption")
                if role == "trader":
                    assert state["shared_valuation_scenarios"]["rows"][0]["version"] == 2
                update = node(state)
                if role == "research":
                    completed_manager.append(copy.deepcopy(update["shared_valuation_scenarios"]))
                return update
            return run
        return factory_with_interrupt

    monkeypatch.setattr(setup, "create_research_manager", wrap(original_manager, "research"))
    monkeypatch.setattr(setup, "create_trader", wrap(original_trader, "trader"))
    graph = _graph(tmp_path, monkeypatch, ScriptedModel(structured=True), checkpoint_enabled=True)
    with pytest.raises(RuntimeError, match="controlled revision"):
        graph.propagate("DOCN", evidence["trade_date"])
    final, _ = graph.propagate("DOCN", evidence["trade_date"])
    assert interrupted[0]["rows"][0]["version"] == (1 if interrupt_role == "research" else 2)
    assert len(completed_manager) == 1
    assert final["shared_valuation_scenarios"] == completed_manager[0]
    assert completed_manager[0]["revision_status"] == "accepted"
    assert completed_manager[0]["rows"][0]["result"]["target"] != completed_manager[0]["analyst_rows"][0]["result"]["target"]


@pytest.mark.parametrize("entry", ["cli", "python"])
def test_public_entry_points_export_the_completed_summary(tmp_path, monkeypatch, offline, entry):
    """Both the merged CLI stream and propagate carry editorial text through the real writer."""
    import json

    import cli.run as cli_run
    from tradingagents.report_summary import SummaryOutput

    from .test_cli_memory_log import _run_cli

    response = {"sentences": [
        {"text": "The analysts contributed market and company research.", "sections": ["1_analysts"]},
        {"text": "The research debate informed the trading proposal.", "sections": ["2_research", "3_trading"]},
        {"text": "The risk discussion informed the final portfolio decision.", "sections": ["4_risk", "5_portfolio"]},
        {"text": "Evidence coverage limits the valuation assessment.", "sections": ["6_evidence"]},
    ]}
    monkeypatch.setitem(STRUCTURED, SummaryOutput, response)
    graph = _graph(tmp_path, monkeypatch, ScriptedModel(structured=True))
    dest = tmp_path / "report"
    if entry == "cli":
        def save(state, app, ticker, **choices):
            app.save_reports(state, ticker, dest)

        monkeypatch.setattr(cli_run, "_offer_reports", save)
        _run_cli(monkeypatch, tmp_path, graph)
    else:
        state, _ = graph.propagate("NVDA", TRADE_DATE)
        graph.save_reports(state, "NVDA", dest)
    record = json.loads((dest / "executive_summary.json").read_text())
    assert record["status"] == "completed"
    for extension in ("md", "html"):
        output = (dest / f"complete_report.{extension}").read_text()
        assert all(item["text"] in output for item in response["sentences"])


class AuditWiringModel(ScriptedModel):
    """Identify audit-stage calls without pretending to adjudicate fixture facts."""
    audit_prompts: list = Field(default_factory=list)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        import json

        prompt = messages[-1].content if messages else ''
        if isinstance(prompt, str) and '\nREPORT CHUNK:\n' in prompt and '\nSUPPLIED SOURCES' in prompt:
            self._count()
            self.audit_prompts.append(prompt)
            chunk = json.loads(prompt.split('REPORT CHUNK:\n', 1)[1].split('\nSUPPLIED SOURCES', 1)[0])
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=json.dumps({
                'no_material_claims': False, 'claims': [{'quoted_claim': chunk['text'], 'outcome': 'hypothesis',
                    'decision_material': False, 'explanation': 'Scripted entrypoint wiring fixture only.', 'evidence': []}]})))])
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


@pytest.mark.parametrize('entry', ['cli', 'python'])
@pytest.mark.parametrize('enabled', [False, True], ids=['audit-no', 'audit-yes'])
@pytest.mark.parametrize('save', [False, True], ids=['no-save', 'save'])
def test_public_entrypoints_finalize_optional_audit_without_extra_disabled_calls(
    tmp_path, monkeypatch, offline, entry, enabled, save,
):
    """Normal graph/CLI finalization and export, with no provider or network calls."""
    import json
    import socket
    from io import StringIO
    from types import SimpleNamespace

    from rich.console import Console

    import cli.display as display
    import cli.run as cli_run
    from cli.models import AnalystType
    from tests.test_cli_config_precedence import SELECTIONS
    from tests.test_cli_memory_log import _FakeBuffer, _NullLive
    from tradingagents.report_summary import SummaryOutput

    network = []
    def forbid_network(*args, **kwargs):
        network.append(True)
        raise AssertionError('Network forbidden in scripted entrypoint fixture')
    monkeypatch.setattr(socket.socket, 'connect', forbid_network)
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'preferences'))
    monkeypatch.setenv('LANGCHAIN_TRACING_V2', 'false')
    monkeypatch.setenv('LANGSMITH_TRACING', 'false')
    for key in ('TRADINGAGENTS_MAX_DEBATE_ROUNDS', 'TRADINGAGENTS_MAX_RISK_ROUNDS'):
        monkeypatch.delenv(key, raising=False)
    summary = {'sentences': [
        {'text': 'The analysts contributed market and company research.', 'sections': ['1_analysts']},
        {'text': 'The research debate informed the trading proposal.', 'sections': ['2_research', '3_trading']},
        {'text': 'The risk discussion informed the final decision.', 'sections': ['4_risk', '5_portfolio']},
        {'text': 'Evidence coverage limits the valuation assessment.', 'sections': ['6_evidence']},
    ]}
    monkeypatch.setitem(STRUCTURED, SummaryOutput, summary)
    model = AuditWiringModel(structured=True)
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg.update(results_dir=str(tmp_path / 'results'), data_cache_dir=str(tmp_path / 'cache'),
               memory_log_path=str(tmp_path / 'memory.md'), checkpoint_enabled=False,
               max_debate_rounds=1, max_risk_discuss_rounds=1, ground_truth_audit=enabled)
    monkeypatch.setattr(trading_graph, 'create_tier_client', lambda config, tier, **kwargs: _Client(model))
    output = StringIO()
    console = Console(file=output, width=160)
    monkeypatch.setattr(cli_run, 'console', console)
    monkeypatch.setattr(display, 'console', console)
    if entry == 'python':
        graph = trading_graph.TradingAgentsGraph(config=cfg, selected_analysts=('market', 'social', 'news'))
        state, signal = graph.propagate('NVDA', TRADE_DATE)
        assert signal == state['final_rating'] == 'Overweight'
        display.display_complete_report(state)
        if save:
            graph.save_reports(state, 'NVDA', tmp_path / 'report')
    else:
        monkeypatch.setattr(cli_run, 'DEFAULT_CONFIG', cfg)
        monkeypatch.setattr(cli_run, 'sys', SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True)))
        monkeypatch.setattr(cli_run, 'get_user_selections', lambda flags=None: {
            **SELECTIONS, 'research_depth': 1, 'ticker': 'NVDA', 'analysis_date': TRADE_DATE,
            'asset_type': 'stock', 'analysts': [AnalystType.MARKET, AnalystType.SOCIAL, AnalystType.NEWS],
            'ground_truth_audit': enabled})
        monkeypatch.setattr(cli_run, 'message_buffer', _FakeBuffer())
        monkeypatch.setattr(cli_run, 'Live', _NullLive)
        monkeypatch.setattr(cli_run, 'create_layout', lambda: None)
        monkeypatch.setattr(cli_run, 'update_display', lambda *args, **kwargs: None)
        # Real run_analysis, config construction, stream, finalizer, engine,
        # publication/state writer, offer_reports and final display remain intact.
        cli_run.run_analysis(flags={'save': save, 'show': True, 'html': True, 'ground_truth_audit': enabled})
        state = json.loads(next(tmp_path.rglob(f'full_states_log_{TRADE_DATE}.json')).read_text())
        graph = None
    logs = list(tmp_path.rglob('full_states_log_*.json'))
    assert len(logs) == 2
    dated = next(path for path in logs if path.name == f'full_states_log_{TRADE_DATE}.json')
    archived = next(path for path in logs if path != dated)
    assert archived.name == f'full_states_log_{TRADE_DATE}_{state["run_id"][:8]}.json'
    assert archived.read_bytes() == dated.read_bytes()
    logged = json.loads(archived.read_text())
    assert bool(state.get('ground_truth_audit')) is enabled
    assert bool(logged.get('ground_truth_audit')) is enabled
    audits = len(model.audit_prompts)
    # The unchanged scripted graph plus summary makes sixteen baseline calls.
    assert len(model.calls) - audits == 16
    if enabled:
        assert audits > 0
        assert state['ground_truth_execution']['requests'] == audits
        assert 'Ground Truth Audit' in output.getvalue()
        assert state['executive_summary']['status'] == 'completed'
    else:
        assert audits == 0
    reports = list(tmp_path.rglob('complete_report.md'))
    assert bool(reports) is save
    if save:
        assert len(reports) == 1
        text = reports[0].read_text()
        html = reports[0].with_suffix('.html').read_text()
        assert ('Ground Truth Audit' in text) is enabled
        assert ('Ground Truth Audit' in html) is enabled
        if enabled:
            companion = next(reports[0].parent.glob('ground_truth_audit-*.md'))
            assert 'Full Ground Truth Audit' in companion.read_text()
        # The writer is shared by both entrypoints, and re-export stays offline.
        from tradingagents.reporting import write_report_tree
        write_report_tree(state, 'NVDA', tmp_path / 'offline-reexport')
        assert len(model.audit_prompts) == audits
    assert not network
