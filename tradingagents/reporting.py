"""Reusable report-tree writer shared by the CLI and the programmatic API.

Writes a run's per-section markdown (analysts, research, trading, risk,
portfolio) plus a consolidated ``complete_report.md`` under ``save_path``. The
CLI and ``TradingAgentsGraph.save_reports`` both call this, so a headless / API
run produces the same on-disk report tree a CLI run does.
"""

import json
from datetime import datetime
from pathlib import Path

from tradingagents.agents.audit_pass import render_advisory_audit
from tradingagents.agents.decision_context import render_condition_summary
from tradingagents.agents.evidence_presentation import (
    analyst_prose,
    evidence_references,
    fact_reference_labels,
)
from tradingagents.agents.output_validation import enforce_publication
from tradingagents.agents.rating import run_rating
from tradingagents.agents.schemas import label_legacy_trader_price
from tradingagents.agents.valuation_comparison import display_number
from tradingagents.dataflows.files import replace_file


def analyst_names(keys) -> list[str]:
    """The analysts as users select them: the sentiment analyst's key is "social"."""
    return ["sentiment" if key == "social" else key for key in keys or []]


def _header(ticker: str, final_state: dict, settings: dict | None) -> str:
    """The report's title and what produced it: analysis date, version, models, analysts, vendors."""
    lines = [f"# Trading Analysis Report: {ticker}", ""]
    if final_state.get("trade_date"):
        lines.append(f"- Analysis date: {final_state['trade_date']}")
    if final_state.get("final_trade_decision"):
        lines.append(f"- Rating: {run_rating(final_state)}")
        if final_state.get("decision_context"):
            lines += ["", render_condition_summary(final_state["decision_context"]), ""]
    if not final_state.get("evidence_quality"):
        lines.append("- Evidence: Legacy export — financial evidence unvalidated")
    publication = final_state.get("publication_record")
    if publication:
        lines.append(f"- Decision ID: {publication['decision_id']}")
        lines.append(f"- First published: {publication['published_at']}")
    label = "Export generated" if publication else "Generated"
    lines.append(f"- {label}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if final_state.get("report_view_note"):
        lines.append("- Export view: " + final_state["report_view_note"])
    elif publication:
        lines.append("- Historical publication identity not verified against a configured store; current validated projection.")
    if settings:
        s = settings.get
        deep_provider = s("deep_think_provider") or s("llm_provider", "?")
        quick_provider = s("quick_think_provider") or s("llm_provider", "?")
        if deep_provider == quick_provider:
            models = f"{deep_provider}, deep {s('deep_think_llm', '?')}, quick {s('quick_think_llm', '?')}"
        else:  # each tier on its own provider (#1440)
            models = (
                f"deep {deep_provider} {s('deep_think_llm', '?')}, "
                f"quick {quick_provider} {s('quick_think_llm', '?')}"
            )
        lines.append(f"- TradingAgents {s('version', '?')}: {models}")
        lines.append(
            f"- Analysts: {', '.join(analyst_names(s('analysts')))}; "
            f"research debate rounds {s('max_debate_rounds', '?')}, "
            f"risk debate rounds {s('max_risk_discuss_rounds', '?')}"
        )
        vendors = {**(s("data_vendors") or {}), **(s("tool_vendors") or {})}
        if vendors:
            lines.append("- Data vendors: " + ", ".join(f"{k} {v}" for k, v in vendors.items()))
    if final_state.get("memory_note"):
        lines.append(f"- Memory log: {final_state['memory_note']}")
    return "\n".join(lines) + "\n\n"


# The report's sections in order: (heading, folder, [(agent, file, state path)]).
_SECTIONS = (
    (
        "I. Analyst Team Reports",
        "1_analysts",
        (
            ("Market Analyst", "market.md", ("market_report",)),
            ("Sentiment Analyst", "sentiment.md", ("sentiment_report",)),
            ("News Analyst", "news.md", ("news_report",)),
            ("Fundamentals Analyst", "fundamentals.md", ("fundamentals_report",)),
        ),
    ),
    (
        "II. Research Team Decision",
        "2_research",
        (
            ("Bull Researcher", "bull.md", ("investment_debate_state", "bull_history")),
            ("Bear Researcher", "bear.md", ("investment_debate_state", "bear_history")),
            ("Research Manager", "manager.md", ("investment_plan",)),
        ),
    ),
    (
        "III. Trading Team Plan",
        "3_trading",
        (("Trader", "trader.md", ("trader_investment_plan",)),),
    ),
    (
        "IV. Risk Management Team Decision",
        "4_risk",
        (
            ("Aggressive Analyst", "aggressive.md", ("risk_debate_state", "aggressive_history")),
            (
                "Conservative Analyst",
                "conservative.md",
                ("risk_debate_state", "conservative_history"),
            ),
            ("Neutral Analyst", "neutral.md", ("risk_debate_state", "neutral_history")),
        ),
    ),
    (
        "V. Portfolio Manager Decision",
        "5_portfolio",
        (("Portfolio Manager", "decision.md", ("final_trade_decision",)),),
    ),
)


def _report_parts(final_state: dict) -> list[tuple[str, str, list[tuple[str, str, str]]]]:
    """The sections with something to say: (heading, folder, [(agent, file, text)])."""
    parts = []
    for heading, folder, agents in _SECTIONS:
        written = []
        for agent, filename, path in agents:
            value = final_state
            for key in path:
                value = (value or {}).get(key)
            if value:
                written.append((agent, filename, value))
        if folder == "5_portfolio" and final_state.get("mechanical_valuation_grid"):
            from tradingagents.agents.mechanical_valuation import render_mechanical_valuation_grid
            grid_text = render_mechanical_valuation_grid(final_state["mechanical_valuation_grid"])
            if grid_text:
                written.insert(0, ("Mechanical sensitivity", "mechanical_grid.md", grid_text))
        if written:
            parts.append((heading, folder, written))
    return parts


def prepare_report_state(final_state: dict) -> dict:
    """Return readable research without changing canonical state or memory inputs.

    Python callers may pass the state returned by propagate() here for the
    same labeled research shown by CLI/Markdown/HTML. Use the original state for
    decision consumers; this copy is for presentation only.
    """
    prepared = {**final_state, **enforce_publication(final_state)}
    if (prepared.get("evidence_quality") or {}).get("status") == "insufficient":
        diagnostics = dict(prepared.get("unvalidated_outputs") or {})
        for field in ("market_report", "sentiment_report", "news_report", "fundamentals_report"):
            raw = prepared.get(field)
            if raw:
                diagnostics.setdefault(field, raw)
                prepared[field] = (
                    "Analyst narrative is unvalidated for this REVIEW run. "
                    "The original text is retained in evidence.json diagnostics."
                )
        if diagnostics:
            prepared["unvalidated_outputs"] = diagnostics
        if isinstance(prepared.get("trader_investment_plan"), str):
            prepared["trader_investment_plan"] = label_legacy_trader_price(prepared["trader_investment_plan"])
        return prepared
    if not prepared.get("evidence_quality"):
        # New export commentary is presentation-only: never rewrite an old
        # decision or introduce a current assessment into publication/memory state.
        original = prepared.get("final_trade_decision")
        reason = "Legacy evidence was not validated; current source-only assessment unavailable."
        if isinstance(original, str) and original.strip() and reason not in original:
            from tradingagents.agents.valuation_comparison import render_price_implied_valuation

            section = render_price_implied_valuation({"status": "unavailable", "reason": reason})
            if "### What the price implies" in original:
                section = section.replace("### What the price implies", "### Current price-implied assessment", 1)
            prepared["final_trade_decision"] = original + "\n\n" + section
        if isinstance(prepared.get("trader_investment_plan"), str):
            prepared["trader_investment_plan"] = label_legacy_trader_price(prepared["trader_investment_plan"])
        return prepared
    originals = prepared.get("unvalidated_outputs") or {}

    def research(text):
        return (
            "### Unvalidated model research\n\n"
            "The following is model-authored research, not validated instructions. "
            "Its numbers, targets, allocations and execution proposals are unverified claims. "
            "The canonical rating, evidence scope, target result and sizing limits remain authoritative.\n\n"
            + text
        )

    for field in ("market_report", "sentiment_report", "news_report", "fundamentals_report",
                  "investment_plan", "trader_investment_plan", "final_trade_decision"):
        raw = originals.get(field)
        if field == "fundamentals_report":
            validation = prepared.get("financial_claim_validation") or {}
            if isinstance(validation, dict) and isinstance(validation.get("raw_report"), str):
                raw = validation["raw_report"] or raw
            if isinstance(raw, str):
                raw = analyst_prose(raw)
        if not isinstance(raw, str) or not raw:
            continue
        canonical = prepared.get(field) or ""
        if field in ("market_report", "sentiment_report", "news_report") or field == "fundamentals_report" and not prepared.get("canonical_financial_context"):
            canonical = ""
        prepared[field] = (
            ("### Canonical evidence and decision limits\n\n" + canonical + "\n\n")
            if canonical else ""
        ) + research(raw)
    for field in ("investment_debate_state", "risk_debate_state"):
        original = originals.get(field)
        if isinstance(original, dict):
            prepared[field] = {
                key: research(value) if isinstance(value, str) and value else value
                for key, value in original.items()
            }
    scenarios = prepared.get("shared_valuation_scenarios")
    if scenarios:
        from tradingagents.agents.shared_valuation import render_shared_valuation

        table = render_shared_valuation(scenarios)
        if table:
            prepared["fundamentals_report"] = table + "\n\n" + (prepared.get("fundamentals_report") or "")
    if isinstance(prepared.get("trader_investment_plan"), str):
        prepared["trader_investment_plan"] = label_legacy_trader_price(prepared["trader_investment_plan"])
    return prepared


def evidence_quality_snapshot(final_state: dict) -> dict:
    """Retain the gate verdict or label a newly exported legacy run explicitly."""
    return final_state.get("evidence_quality") or {
        "schema_version": 1,
        "scope": "legacy export",
        "status": "unvalidated",
        "checks": [],
        "warnings": ["Legacy export — financial evidence was not validated"],
    }


def evidence_snapshot(final_state: dict) -> dict:
    """Persist canonical source packages separately from raw model diagnostics."""
    names = (
        "thesis",
        "advisory_audit",
        "audit_market_tool_evidence",
        "audit_social_tool_evidence",
        "audit_news_tool_evidence",
        "audit_fundamentals_tool_evidence",
        "run_metrics",
        "valuation_reference",
        "valuation_reference_brief",
        "vendor_expectations",
        "evidence_acquisition",
        "shared_source_brief",
        "price_observation",
        "valuation_price_comparison",
        "price_implied_valuation",
        "mechanical_valuation_grid",
        "decision_context",
        "event_comparison",
        "issuer_identity",
        "financial_evidence",
        "filing_evidence",
        "filing_fact_extraction",
        "financial_calculations",
        "disclosure_evidence",
        "target_validation",
        "shared_valuation_scenarios",
        "canonical_financial_context",
        "issuer_event_evidence",
        "news_coverage",
    )
    snapshot = {
        "schema_version": 1,
        "quality_status": evidence_quality_snapshot(final_state)["status"],
    }
    snapshot.update({name: final_state[name] for name in names if name in final_state})
    diagnostics = {
        name: final_state[name]
        for name in ("financial_claim_validation", "unvalidated_outputs")
        if name in final_state
    }
    if diagnostics:
        snapshot["raw_diagnostics"] = diagnostics
    return snapshot


def _markdown_cell(value) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def evidence_appendix(final_state: dict) -> str:
    """Deterministic coverage and arithmetic; model prose remains unvalidated."""
    quality = evidence_quality_snapshot(final_state)
    canonical = final_state.get("canonical_financial_context") or ""
    labels = fact_reference_labels(canonical)
    lines = [
        f"Evidence status: **{_markdown_cell(quality.get('status', 'unvalidated'))}**. "
        "Checks apply to cited source values and calculations; narrative interpretations are not all verified.",
        "",
    ]
    if quality.get("scope") == "legacy export":
        lines += ["Legacy export — financial evidence unvalidated.", ""]
    checks = quality.get("checks") or []
    if checks:
        lines += ["#### Evidence checks", "", "Check | Status | Finding", "--- | --- | ---"]
        lines += [
            f"{_markdown_cell(c.get('code'))} | {_markdown_cell(c.get('status'))} | {_markdown_cell(c.get('message'))}"
            for c in checks
        ]
        lines.append("")
    calculations = final_state.get("financial_calculations") or []
    if calculations:
        lines += [
            "#### Canonical calculations",
            "",
            "Method | Status | Result | Inputs | Finding",
            "--- | --- | --- | --- | ---",
        ]
        for calculation in calculations:
            value = calculation.get("result")
            result = (
                "unavailable"
                if value is None
                else f"{display_number(value)} {calculation.get('unit') or ''}".strip()
            )
            lines.append(
                " | ".join(
                    _markdown_cell(x)
                    for x in (
                        calculation.get("method"),
                        calculation.get("status"),
                        result,
                        ", ".join(labels.get(ident, ident) for ident in calculation.get("input_fact_ids") or ()),
                        calculation.get("message"),
                    )
                )
            )
        lines.append("")
    warnings = quality.get("warnings") or []
    if warnings:
        lines += ["#### Warnings and gaps", ""]
        lines += [f"- {_markdown_cell(w)}" for w in warnings]
    references = evidence_references(canonical)
    if references:
        lines += ["", references]
    if "advisory_audit" in final_state:
        lines += ["", render_advisory_audit(final_state["advisory_audit"])]
    if final_state.get("outcome_summary"):
        lines += ["", final_state["outcome_summary"]]
    return "\n".join(lines).strip()


def _write_json(path: Path, value: dict) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n"
    replace_file(
        path, lambda temporary: Path(temporary).write_text(payload, encoding="utf-8"), strict=True
    )


def verified_publication(config: dict, state: dict, ticker: str, asof: str):
    """Verify an existing disk publication against the complete original state.

    Missing records return None for ordinary new-run validation. Serialized
    publication markers never establish authority; corruption/mismatch raises.
    """
    from tradingagents.memory import publication

    if not state.get('run_id'):
        return None
    try:
        record = publication.load_record(config, state['run_id'])
    except FileNotFoundError:
        return None
    snapshot = publication.load_evidence(config, record)
    # Existing-record publish performs the full payload comparison, including
    # the full decision hash when the stored readable excerpt was truncated.
    checked = publication.publish(config, state, ticker, asof)
    return checked, snapshot


def write_report_tree(
    final_state: dict, ticker: str, save_path, settings: dict | None = None, html: bool = True,
    *, publication_config: dict | None = None,
) -> Path:
    """Save a completed run's reports to ``save_path``; return the complete-report path.

    ``settings`` (``TradingAgentsGraph.run_settings()``) adds what produced the run
    to the report's header. ``html`` also writes ``complete_report.html``, one
    self-contained page of the same report (#1419).
    """
    frozen = (verified_publication(publication_config, final_state, ticker, final_state.get("trade_date"))
              if publication_config is not None else None)
    if publication_config is not None and final_state.get("publication_record") and frozen is None:
        raise ValueError("Claimed historical publication is missing from the configured store")
    original_quality = evidence_quality_snapshot(final_state)
    original_diagnostics = evidence_snapshot(final_state).get("raw_diagnostics", {})
    final_state = prepare_report_state(final_state)
    if frozen is not None:
        record, original_snapshot = frozen
        final_state["publication_record"] = {key: record[key] for key in ("decision_id", "published_at", "record_sha256")}
        final_state["report_view_note"] = ("Current validated presentation of a verified immutable publication. "
            "Display and current validation may differ from the original; evidence.json retains its original immutable snapshot. "
            "For this export, diagnostic references in the research text refer to companion diagnostics.json.")
    elif final_state.get("publication_record"):
        final_state["report_view_note"] = ("Historical publication identity not verified against a configured store. "
            "This export is a current validated projection, not an immutable publication snapshot.")
    save_path = Path(save_path)
    save_path.mkdir(parents=True, exist_ok=True)
    _write_json(save_path / "quality.json", original_quality if frozen else evidence_quality_snapshot(final_state))
    _write_json(save_path / "evidence.json", original_snapshot if frozen else evidence_snapshot(final_state))
    if frozen:
        _write_json(save_path / "diagnostics.json", original_diagnostics)
    parts = _report_parts(final_state)
    if frozen:
        parts = [(heading, folder, [(agent, filename, text.replace("evidence.json diagnostics", "diagnostics.json"))
                                   for agent, filename, text in written])
                 for heading, folder, written in parts]
    parts.append(
        (
            "VI. Evidence and Quality",
            "6_evidence",
            [("Evidence Summary", "summary.md", evidence_appendix(final_state))],
        )
    )
    sections = []
    for heading, folder, written in parts:
        (save_path / folder).mkdir(exist_ok=True)
        for _agent, filename, text in written:
            (save_path / folder / filename).write_text(text, encoding="utf-8")
        content = "\n\n".join(f"### {agent}\n{text}" for agent, _filename, text in written)
        sections.append(f"## {heading}\n\n{content}")

    (save_path / "complete_report.md").write_text(
        _header(ticker, final_state, settings) + "\n\n".join(sections), encoding="utf-8"
    )
    if html:
        from tradingagents.report_html import render_report

        (save_path / "complete_report.html").write_text(
            render_report(ticker, final_state, settings, parts, diagnostics_sidecar=bool(frozen)), encoding="utf-8"
        )
    return save_path / "complete_report.md"
