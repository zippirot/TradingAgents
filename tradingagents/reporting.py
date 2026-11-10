"""Reusable report-tree writer shared by the CLI and the programmatic API.

Writes a run's per-section markdown (analysts, research, trading, risk,
portfolio) plus a consolidated ``complete_report.md`` under ``save_path``. The
CLI and ``TradingAgentsGraph.save_reports`` both call this, so a headless / API
run produces the same on-disk report tree a CLI run does.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from tradingagents.agents.audit_pass import prepare_audit_dispositions, render_advisory_audit
from tradingagents.agents.decision_context import render_condition_summary
from tradingagents.agents.evidence_presentation import (
    analyst_prose,
    evidence_references,
    fact_reference_labels,
)
from tradingagents.agents.output_validation import enforce_publication
from tradingagents.agents.rating import run_rating
from tradingagents.agents.schemas import label_legacy_trader_price
from tradingagents.agents.valuation_comparison import display_value
from tradingagents.dataflows.files import locked, replace_file

UNVALIDATED_RESEARCH_NOTICE_SENTENCES = (
    "The following is model-authored research, not validated instructions.",
    "Its numbers, targets, allocations and execution proposals are unverified claims.",
    "The canonical rating, evidence scope, target result and sizing limits remain authoritative.",
)
UNVALIDATED_RESEARCH_NOTICE = " ".join(UNVALIDATED_RESEARCH_NOTICE_SENTENCES)


def is_application_policy_notice(text):
    """Only exact generated software framing lies outside company-fact scope."""
    return isinstance(text, str) and text.strip() in (
        *UNVALIDATED_RESEARCH_NOTICE_SENTENCES, UNVALIDATED_RESEARCH_NOTICE,
        "### Unvalidated model research\n\n" + UNVALIDATED_RESEARCH_NOTICE,
    )


def render_token_usage(metrics: dict | None) -> str:
    """One bounded usage footer; counts are observations, never billing estimates."""
    scope_note = (" These counts cover the research graph only; editorial summary generation, "
                  "if present, is recorded separately in executive_summary.json.")
    data = metrics if isinstance(metrics, dict) else {}
    values = [data.get("input_tokens"), data.get("output_tokens")]
    scope = data.get("token_usage_scope")
    if scope not in {"complete_observed", "partial_observed"} or any(type(v) is not int or v < 0 for v in values):
        return "Token usage: unavailable (usage was not recorded completely enough to total)." + scope_note
    label = "complete observed" if scope == "complete_observed" else "partial observed"
    return (f"Token usage: {values[0]:,} input / {values[1]:,} output ({label}). "
            "Provider-internal retries may not report usage; these counts are not a billing total." + scope_note)


def analyst_names(keys) -> list[str]:
    """The analysts as users select them: the sentiment analyst's key is "social"."""
    return ["sentiment" if key == "social" else key for key in keys or []]


def _header(ticker: str, final_state: dict, settings: dict | None, *, metadata_only: bool = False) -> str:
    """The report's title and what produced it: analysis date, version, models, analysts, vendors."""
    lines = [] if metadata_only else [f"# Trading Analysis Report: {_plain_markdown(ticker)}", ""]
    if final_state.get("trade_date") and not metadata_only:
        lines.append(f"- Analysis date: {_plain_markdown(final_state['trade_date'])}")
    if final_state.get("final_trade_decision"):
        lines.append(f"- Rating: {_plain_markdown(run_rating(final_state))}")
        if final_state.get("decision_context") and not metadata_only:
            lines += ["", render_condition_summary(final_state["decision_context"]), ""]
    if not final_state.get("evidence_quality"):
        lines.append("- Evidence: Legacy export — financial evidence unvalidated")
    publication = final_state.get("publication_record")
    if publication:
        lines.append(f"- Decision ID: {_plain_markdown(publication['decision_id'])}")
        lines.append(f"- First published: {_plain_markdown(publication['published_at'])}")
    label = "Export generated" if publication else "Generated"
    lines.append(f"- {label}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if final_state.get("report_view_note"):
        lines.append("- Export view: " + _plain_markdown(final_state["report_view_note"]))
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
        lines.append(f"- TradingAgents {_plain_markdown(s('version', '?'))}: {_plain_markdown(models)}")
        if s("source_hash"):
            lines.append(f"- Source hash: {_plain_markdown(s('source_hash'))}")
        for key, label in (("openai_reasoning_effort", "OpenAI/OpenRouter reasoning effort"),
                           ("anthropic_effort", "Anthropic effort"),
                           ("google_thinking_level", "Google thinking level")):
            if s(key):
                lines.append(f"- {label}: {_plain_markdown(s(key))}")
        lines.append(
            f"- Analysts: {_plain_markdown(', '.join(analyst_names(s('analysts'))))}; "
            f"research debate rounds {_plain_markdown(s('max_debate_rounds', '?'))}, "
            f"risk debate rounds {_plain_markdown(s('max_risk_discuss_rounds', '?'))}"
        )
        vendors = {**(s("data_vendors") or {}), **(s("tool_vendors") or {})}
        if vendors:
            lines.append("- Data vendors: " + _plain_markdown(", ".join(f"{k} {v}" for k, v in vendors.items())))
    if final_state.get("memory_note"):
        lines.append(f"- Memory log: {_plain_markdown(final_state['memory_note'])}")
    return "\n".join(lines) + "\n\n"


# The report's display order: (name, folder, [(agent, file, state path)]).
_SECTIONS = (
    (
        "Final Portfolio Decision",
        "5_portfolio",
        (("Portfolio Manager", "decision.md", ("final_trade_decision",)),),
    ),
    (
        "Analyst Team Reports",
        "1_analysts",
        (
            ("Market Analyst", "market.md", ("market_report",)),
            ("Sentiment Analyst", "sentiment.md", ("sentiment_report",)),
            ("News Analyst", "news.md", ("news_report",)),
            ("Fundamentals Analyst", "fundamentals.md", ("fundamentals_report",)),
        ),
    ),
    (
        "Research Team Decision",
        "2_research",
        (
            ("Bull Researcher", "bull.md", ("investment_debate_state", "bull_history")),
            ("Bear Researcher", "bear.md", ("investment_debate_state", "bear_history")),
            ("Research Manager", "manager.md", ("investment_plan",)),
        ),
    ),
    (
        "Trading Team Plan",
        "3_trading",
        (("Trader", "trader.md", ("trader_investment_plan",)),),
    ),
    (
        "Risk Management Team Decision",
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
)

_ROMAN = ("I", "II", "III", "IV", "V", "VI")
_DESCRIPTIONS = {
    "5_portfolio": "Rating, rationale, valuation, scenarios, and reconsideration conditions",
    "1_analysts": "Market, sentiment, news, and fundamentals",
    "2_research": "Bull and bear cases and the research conclusion",
    "3_trading": "Proposed action, timing, and exposure",
    "4_risk": "Aggressive, conservative, and neutral perspectives",
    "6_evidence": "Checks, calculations, references, and limitations",
}


def report_sections(final_state: dict, parts=None):
    """One ordered section model for both exports and summary input."""
    by_folder = {folder: written for _, folder, written in
                 (_report_parts(final_state) if parts is None else parts) if written}
    if "6_evidence" not in by_folder:
        by_folder["6_evidence"] = [("Evidence Summary", "summary.md", evidence_appendix(final_state))]
    headings = [(heading, folder) for heading, folder, _ in _SECTIONS] + [("Evidence and Quality", "6_evidence")]
    present = [(heading, folder) for heading, folder in headings if folder in by_folder]
    return [(f"{_ROMAN[index]}. {heading}", folder, by_folder[folder])
            for index, (heading, folder) in enumerate(present)]


def historical_anchors(parts):
    """Map section identity to its old positional HTML/Markdown anchor."""
    legacy_order = {"1_analysts": 1, "2_research": 2, "3_trading": 3,
                    "4_risk": 4, "5_portfolio": 5, "6_evidence": 6}
    return {folder: f"s{index}" for index, (_heading, folder, _written) in
            enumerate(sorted(parts, key=lambda part: legacy_order[part[1]]), 1)}


def _report_parts(final_state: dict) -> list[tuple[str, str, list[tuple[str, str, str]]]]:
    """The sections with something to say: (heading, folder, [(agent, file, text)])."""
    parts = []
    for heading, folder, agents in _SECTIONS:
        written = []
        if folder == '4_risk' and (final_state.get('risk_debate_state') or {}).get('history'):
            parts.append((heading, folder, [('Risk debate in speaking order', 'debate.md', final_state['risk_debate_state']['history'])]))
            continue
        for agent, filename, path in agents:
            value = final_state
            for key in path:
                value = (value or {}).get(key)
            if value:
                if path == ("final_trade_decision",) and final_state.get("document_followups"):
                    from tradingagents.agents.document_questions import render_document_followups

                    value += "\n\n" + render_document_followups(final_state, value)
                written.append((agent, filename, value))
        if folder == "5_portfolio" and final_state.get("mechanical_valuation_grid"):
            from tradingagents.agents.mechanical_valuation import render_mechanical_valuation_grid
            grid_text = render_mechanical_valuation_grid(final_state["mechanical_valuation_grid"])
            if grid_text:
                written.append(("Mechanical sensitivity", "mechanical_grid.md", grid_text))
        if written:
            parts.append((heading, folder, written))
    return parts


def summary_input_for_report(prepared_state: dict, settings: dict | None = None, parts=None):
    """Build the same summary context used at finalization and during offline export."""

    from tradingagents.report_summary import build_summary_input

    retained = prepared_state.get("run_settings")
    source_parts = report_sections(prepared_state) if parts is None else parts
    return build_summary_input(prepared_state, retained if isinstance(retained, dict) else settings,
                               source_parts)


def _plain_markdown(value: str) -> str:
    """Keep editorial text as prose, even if a saved record contains Markdown."""
    plain = str(value).replace("\r", " ").replace("\n", " ").replace("&", "&amp;")
    plain = plain.replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*\[\]])", r"\\\1", plain)


def _summary_companion(saved_record, projection: dict) -> dict:
    """Keep a bounded original record when valid, without accepting extra fields."""
    from tradingagents.report_summary import SCHEMA_VERSION

    def projected_record():
        return {"schema_version": SCHEMA_VERSION, "status": projection["status"],
                "source_input_digest": projection["source_input_digest"],
                "process": projection["process"], "sentences": projection["sentences"],
                "error_category": projection.get("reason")}

    # An invalid current completed record can contain protected prose supplied
    # by an old model response. Keep only the verified fallback projection.
    if (isinstance(saved_record, dict) and saved_record.get("status") == "completed"
            and saved_record.get("source_input_digest") == projection.get("source_input_digest")
            and projection.get("status") != "completed"):
        return projected_record()
    if (isinstance(saved_record, dict) and saved_record.get("schema_version") == SCHEMA_VERSION
            and saved_record.get("status") in {"completed", "unavailable", "review"}
            and isinstance(saved_record.get("source_input_digest"), str)
            and re.fullmatch(r"[0-9a-f]{64}", saved_record["source_input_digest"])
            and isinstance(saved_record.get("process"), str)
            and len(saved_record["process"]) <= 3000
            and isinstance(saved_record.get("sentences"), list)
            and (5 <= len(saved_record["sentences"]) <= 12
                 if saved_record.get("status") == "completed" else not saved_record["sentences"])
            and all(isinstance(s, str) and len(s) <= 500 for s in saved_record["sentences"])):
        items = saved_record.get("body_items")
        if saved_record["status"] == "completed" and (not isinstance(items, list)
                or not 3 <= len(items) <= 10
                or any(not isinstance(item, dict) or not isinstance(item.get("text"), str)
                       or len(item["text"]) > 500 or not isinstance(item.get("sections"), list)
                       or not item["sections"] or len(item["sections"]) > 6
                       or any(not isinstance(section, str) or section not in _DESCRIPTIONS
                              for section in item["sections"]) for item in items)):
            return projected_record()
        clean = {key: saved_record[key] for key in
                 ("schema_version", "status", "source_input_digest", "process", "sentences")}
        if isinstance(items, list) and len(items) <= 10:
            clean["body_items"] = [
                {"text": item["text"], "sections": item["sections"]}
                for item in items
                if isinstance(item, dict) and isinstance(item.get("text"), str)
                and len(item["text"]) <= 500 and isinstance(item.get("sections"), list)
                and len(item["sections"]) <= 6
                and all(isinstance(section, str) and section in _DESCRIPTIONS
                        for section in item["sections"])
            ]
        model = saved_record.get("generation_model")
        if model is None or isinstance(model, str) and len(model) <= 100:
            clean["generation_model"] = model
        truncation = saved_record.get("truncation")
        if isinstance(truncation, dict):
            clean["truncation"] = {key: value for key, value in truncation.items()
                                   if key in _DESCRIPTIONS and type(value) is bool}
        error = saved_record.get("error_category")
        if error is None or isinstance(error, str) and len(error) <= 80:
            clean["error_category"] = error
        elapsed = saved_record.get("elapsed_ms")
        if type(elapsed) in {int, float} and 0 <= elapsed <= 3_600_000:
            clean["elapsed_ms"] = elapsed
        return clean
    return projected_record()


def _summary_markdown(summary: dict) -> str:
    if summary.get("_ground_truth_text"):
        return summary["_ground_truth_text"]
    process = _plain_markdown(summary.get("process") or "")
    decision = _plain_markdown(" ".join(summary.get("sentences") or []))
    return f"## Executive summary\n\n{process}\n\n{decision}\n"


def _contents_markdown(parts) -> str:
    anchors = historical_anchors(parts)
    lines = ["## Table of contents", ""]
    for heading, folder, written in parts:
        lines.append(f"- [{heading}](#{anchors[folder]}) — {_DESCRIPTIONS[folder]}")
        for index, (agent, _filename, _text) in enumerate(written, 1):
            lines.append(f"  - [{agent}](#{anchors[folder]}-{index})")
    return "\n".join(lines) + "\n"


def stale_price_note(state) -> str:
    """One line when the price in use comes from an earlier session than the latest completed one."""
    price = state.get("price_observation") if isinstance(state, dict) else None
    fallback = price.get("price_fallback") if isinstance(price, dict) else None
    if not isinstance(fallback, dict):
        return ""
    latest, selected = fallback.get("latest_completed_session_date"), price.get("session_date")
    if not isinstance(latest, str) or not isinstance(selected, str) or latest == selected:
        return ""
    return (f"**Stale price:** the latest completed session {_plain_markdown(latest)} has no close from the data "
            f"source; all price and indicator figures use {_plain_markdown(selected)}.")


def position_sizing_note(state) -> str:
    """The 'Position and sizing' block when the run was given a portfolio value; otherwise nothing."""
    from tradingagents.portfolio import render_sizing, sizing_from_state

    if not isinstance(state, dict) or not state.get("final_rating"):
        return ""
    return "\n".join(render_sizing(sizing_from_state(state, final=True), final=True))


def prepare_report_state(final_state: dict, *, publication_config: dict | None = None) -> dict:
    """Return readable research without changing canonical state or memory inputs.

    Python callers may pass the state returned by propagate() here for the
    same labeled research shown by CLI/Markdown/HTML. Use the original state for
    decision consumers; this copy is for presentation only.
    """
    prepared = _prepare_report_state(final_state, publication_config=publication_config)
    sizing = position_sizing_note(prepared)
    if sizing and isinstance(prepared.get("final_trade_decision"), str) and prepared["final_trade_decision"]:
        # Arithmetic on the reader's own file, shown with the decision and kept out of the published record.
        prepared["final_trade_decision"] = sizing + "\n\n" + prepared["final_trade_decision"]
    stale = stale_price_note(prepared)
    if stale:
        # Every price and indicator below is a session old; say so where the reader
        # starts, on the full, REVIEW and legacy presentations alike.
        for field in ("final_trade_decision", "market_report"):
            if isinstance(prepared.get(field), str) and prepared[field]:
                prepared[field] = stale + "\n\n" + prepared[field]
    return prepared


def _prepare_report_state(final_state: dict, *, publication_config: dict | None = None) -> dict:
    """Return readable research without changing canonical state or memory inputs.

    Python callers may pass the state returned by propagate() here for the
    same labeled research shown by CLI/Markdown/HTML. Use the original state for
    decision consumers; this copy is for presentation only.
    """
    prepared = {**final_state, **enforce_publication(final_state, publication_config=publication_config)}
    if (prepared.get("evidence_quality") or {}).get("status") == "insufficient":
        diagnostics = dict(prepared.get("unvalidated_outputs") or {})
        for field in ("market_report", "sentiment_report", "news_report", "fundamentals_report"):
            raw = prepared.get(field)
            if raw:
                diagnostics.setdefault(field, raw)
                prepared[field] = (
                    "Analyst narrative is unvalidated for this REVIEW run. "
                    "The original text is retained in diagnostics.json."
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
            "### Unvalidated model research\n\n" + UNVALIDATED_RESEARCH_NOTICE + "\n\n" + text
        )

    pm = originals.get('portfolio_manager') or {}
    if not pm.get('structured') and isinstance(originals.get('final_trade_decision'), str):
        # Older/free-text calls retain their argument in a labeled appendix.
        prepared['final_trade_decision'] += '\n\n' + research(originals['final_trade_decision'])

    for field in ("market_report", "sentiment_report", "news_report", "fundamentals_report",
                  "investment_plan", "trader_investment_plan"):
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
        canonical_text = (
            ("### Canonical evidence and decision limits\n\n" + canonical + "\n\n")
            if canonical else ""
        )
        prepared[field] = research(raw) + '\n\n' + canonical_text if field == 'investment_plan' else canonical_text + research(raw)
    for field in ("investment_debate_state", "risk_debate_state"):
        original = originals.get(field)
        if isinstance(original, dict):
            prepared[field] = {
                key: research(value) if isinstance(value, str) and value else value
                for key, value in original.items()
            }
            if field == "investment_debate_state":
                questions = (final_state.get(field) or {}).get("document_questions")
                if questions is not None:
                    prepared[field]["document_questions"] = questions
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
        "document_sources",
        "transcript_sources",
        "document_search_trace",
        "document_followups",
        "document_followup_judgments",
        "prompt_evidence_references",
        "shared_source_brief",
        "price_observation",
        "required_return",
        "valuation_price_comparison",
        "price_implied_valuation",
        "mechanical_valuation_grid",
        "decision_context",
        "event_comparison",
        "issuer_identity",
        "financial_evidence",
        "filing_evidence",
        "filing_fact_extraction",
        "filing_terms_evidence",
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
    inputs = final_state.get("portfolio_inputs")
    if isinstance(inputs, dict) and inputs.get("portfolio_value") is not None:
        # Model-written parts of the record from a run that was shown the caller's portfolio figures.
        from tradingagents.agents.evidence_presentation import without_portfolio_figures

        for name in ("thesis", "decision_context"):
            if name in snapshot:
                snapshot[name] = without_portfolio_figures(snapshot[name])
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


def _prompt_only_references(final_state: dict, canonical_labels: dict) -> list[str]:
    references = final_state.get("prompt_evidence_references")
    evidence = final_state.get("financial_evidence")
    if not isinstance(references, dict) or not isinstance(evidence, dict):
        return []
    facts = {f.get("fact_id"): f for f in evidence.get("facts") or () if isinstance(f, dict)}
    rows = []
    for fact_id, label in references.items():
        fact = facts.get(fact_id)
        if fact is None or fact.get("value") is None or fact_id in canonical_labels or not re.fullmatch(r"F\d+", str(label)):
            continue
        start, end = fact.get("period_start"), fact.get("period_end")
        period = f"{start} to {end}" if start else f"as of {end}"
        rows.append((int(label[1:]), f"- {label}: {_markdown_cell(fact.get('metric'))}; {period}; "
                                     f"{_markdown_cell(fact.get('value'))} {_markdown_cell(fact.get('unit'))}; fact_id {fact_id}"))
    return [row for _, row in sorted(rows)]


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
    from tradingagents.agents.document_access import render_document_searches

    searches = render_document_searches(final_state)
    if searches:
        lines += [searches, ""]
    from tradingagents.agents.transcript_access import render_transcript_status

    transcript_status = render_transcript_status(final_state)
    if transcript_status:
        lines += [transcript_status, ""]
    disclosure = final_state.get("disclosure_evidence")
    counts = disclosure.get("submission_counts") if isinstance(disclosure, dict) else None
    if isinstance(counts, dict):
        def count(key):
            value = counts.get(key)
            return str(value) if type(value) is int and value >= 0 else "unavailable"
        lines += ["#### Disclosure extraction",
                  f"Model submissions: {count('model_accepted')} accepted, {count('model_rejected')} rejected.",
                  f"Deterministic discovery: {count('deterministic_accepted')} accepted, {count('deterministic_rejected')} rejected.",
                  "Accepted sets may overlap; raw rejected records and source locators remain in evidence.json.", ""]
    from tradingagents.agents.filing_terms import render_filing_terms

    terms = render_filing_terms(final_state)
    if terms:
        lines += ["#### Source-bound instrument terms and commitments", "", terms, ""]
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
            result = display_value(value, calculation.get("unit"))
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
    prompt_only = _prompt_only_references(final_state, labels)
    if prompt_only:
        lines += ["", "#### Prompt-only references", "",
                  "Facts the analysts saw in the shared source brief but which are outside the canonical appendix.", "",
                  *prompt_only]
    if "advisory_audit" in final_state:
        lines += ["", render_advisory_audit(final_state["advisory_audit"],
                                            dispositions=prepare_audit_dispositions(final_state))]
    if final_state.get("outcome_summary"):
        lines += ["", final_state["outcome_summary"]]
    return "\n".join(lines).strip()


def _write_json(path: Path, value: dict) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n"
    replace_file(
        path, lambda temporary: Path(temporary).write_text(payload, encoding="utf-8"), strict=True
    )


def _write_text(path: Path, payload: str) -> None:
    """Replace an export strictly and confirm the actual bytes on disk."""
    replace_file(path, lambda temporary: Path(temporary).write_text(payload, encoding="utf-8"), strict=True)
    if path.read_text(encoding="utf-8") != payload:
        raise OSError(f"Export verification failed: {path.name}")


def _operational_assessment(original: dict, summary: dict, integrity: str):
    from tradingagents import operational_audit as audit

    source = dict(original)
    source["executive_summary"] = summary
    return audit.assess_audit(source, integrity=integrity)


def _unavailable_assessment(reason: str) -> dict:
    from tradingagents.operational_audit import DEFINITIONS, INPUT_NAMES

    return {"score": None, "name": DEFINITIONS[None][0], "definition": DEFINITIONS[None][1],
            "consequence": reason, "inputs": dict.fromkeys(INPUT_NAMES, "unknown")}


def _audit_filename(save_path: Path, content: str) -> Path:
    """Never replace a different audit already linked from an older report."""
    import hashlib

    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    for name in ("operational_audit.md", f"operational_audit-{digest[:16]}.md",
                 f"operational_audit-{digest}.md"):
        candidate = save_path / name
        if not candidate.exists() or candidate.read_text(encoding="utf-8") == content:
            return candidate
    raise OSError("Operational audit filename collision")


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
    save_path = Path(save_path)
    save_path.mkdir(parents=True, exist_ok=True)
    with locked(save_path / ".report-export"):
        return _write_report_tree_locked(final_state, ticker, save_path, settings, html,
                                         publication_config=publication_config)


def _write_report_tree_locked(
    final_state: dict, ticker: str, save_path: Path, settings: dict | None, html: bool,
    *, publication_config: dict | None,
) -> Path:
    """Build and publish one report while holding its destination lock."""
    original_state = final_state
    frozen = (verified_publication(publication_config, final_state, ticker, final_state.get("trade_date"))
              if publication_config is not None else None)
    if publication_config is not None and final_state.get("publication_record") and frozen is None:
        raise ValueError("Claimed historical publication is missing from the configured store")
    original_quality = evidence_quality_snapshot(final_state)
    original_diagnostics = evidence_snapshot(final_state).get("raw_diagnostics", {})
    final_state = prepare_report_state(final_state, publication_config=publication_config)
    if frozen is not None:
        record, original_snapshot = frozen
        final_state["publication_record"] = {key: record[key] for key in ("decision_id", "published_at", "record_sha256")}
        final_state["report_view_note"] = ("Current validated presentation of a verified immutable publication. "
            "Display and current validation may differ from the original; evidence.json retains its original immutable snapshot. "
            "For this export, diagnostic references in the research text refer to companion diagnostics.json.")
        if 'pm_executive_summary' not in record:
            final_state['report_view_note'] += ' Historical publication did not separately bind PM summary, thesis or stated conditions; displayed retained PM prose is unvalidated and unbound by that original record.'
    elif final_state.get("publication_record"):
        final_state["report_view_note"] = ("Historical publication identity not verified against a configured store. "
            "This export is a current validated projection, not an immutable publication snapshot.")
    _write_json(save_path / "quality.json", original_quality if frozen else evidence_quality_snapshot(final_state))
    _write_json(save_path / "evidence.json", original_snapshot if frozen else evidence_snapshot(final_state))
    preserve_diagnostics = frozen or (final_state.get("publication_record") and (
        (final_state.get("run_settings") or {}).get("ground_truth_audit") is True
        or final_state.get("ground_truth_audit")))
    _write_json(save_path / "diagnostics.json", original_diagnostics if preserve_diagnostics else
                evidence_snapshot(final_state).get("raw_diagnostics", {}))
    display_settings = (final_state.get("run_settings") if isinstance(final_state.get("run_settings"), dict)
                        else settings)
    parts = report_sections(final_state)
    from tradingagents.report_summary import resolve_summary

    summary = resolve_summary(summary_input_for_report(final_state, display_settings, parts),
                              final_state.get("executive_summary"))
    _write_json(save_path / "executive_summary.json",
                _summary_companion(final_state.get("executive_summary"), summary))
    if frozen:
        parts = [(heading, folder, [(agent, filename, text.replace("evidence.json diagnostics", "diagnostics.json"))
                                   for agent, filename, text in written])
                 for heading, folder, written in parts]
    from tradingagents.ground_truth_display import project_report

    parts, summary, ground_truth_text, ground_truth_record = project_report(final_state, parts, summary)
    if ground_truth_record is not None:
        # The companion is content-addressed so a reused folder retains old links.
        import hashlib

        audit_name = "ground_truth_audit-" + hashlib.sha256(ground_truth_text.encode()).hexdigest()[:20] + ".md"
        from tradingagents.ground_truth_display import audit_assessment

        try:
            _write_text(save_path / audit_name, ground_truth_text)
        except OSError:
            unavailable = {**ground_truth_record, "status": "unavailable",
                           "reason": "The Ground Truth Audit detail could not be saved for this export."}
            ground_truth_text = audit_assessment(unavailable, final_state)
        else:
            ground_truth_text = audit_assessment(ground_truth_record, final_state)
            ground_truth_text += f"\n\n[Full Ground Truth Audit](./{audit_name})\n"
    anchors = historical_anchors(parts)
    risk = final_state.get('risk_debate_state') or {}
    if risk.get('history'):
        risk_path = save_path / '4_risk'
        risk_path.mkdir(exist_ok=True)
        for key, filename in (('aggressive_history', 'aggressive.md'), ('conservative_history', 'conservative.md'), ('neutral_history', 'neutral.md')):
            if risk.get(key):
                (risk_path / filename).write_text(risk[key], encoding='utf-8')
    sections = []
    for heading, folder, written in parts:
        (save_path / folder).mkdir(exist_ok=True)
        for _agent, filename, text in written:
            (save_path / folder / filename).write_text(text, encoding="utf-8")
        content = "\n\n".join(f'<a id="{anchors[folder]}-{index}"></a>\n### {agent}\n{text}'
                                for index, (agent, _filename, text) in enumerate(written, 1))
        sections.append(f'<a id="{anchors[folder]}"></a>\n## {heading}\n\n{content}')

    markdown_base = (
        f"# Trading Analysis Report: {_plain_markdown(ticker)}\n\n"
        + (f"- Analysis date: {_plain_markdown(final_state['trade_date'])}\n\n"
           if final_state.get("trade_date") else "")
        + ground_truth_text + "\n" + (stale_price_note(final_state) + "\n\n" if stale_price_note(final_state) else "")
        + (position_sizing_note(final_state) + "\n\n" if position_sizing_note(final_state) else "")
        + _summary_markdown(summary) + "\n" + _contents_markdown(parts) + "\n"
        + _header(ticker, final_state, display_settings, metadata_only=True) + "\n\n".join(sections)
        + "\n\n---\n\n" + render_token_usage(final_state.get("run_metrics")) + "\n"
    )
    # Assess the original run record after the prepared presentation is known.
    # A claimed historical publication needs the configured store to establish
    # its identity, even if the report can still be exported without one.
    integrity = "unverified" if original_state.get("publication_record") and not frozen else "verified"
    from tradingagents import operational_audit as audit

    audit_path = None
    try:
        assessment = _operational_assessment(original_state, summary, integrity)
        audit_text = audit.render_audit(assessment)
        destination = _audit_filename(save_path, audit_text)
        if not destination.exists():
            _write_text(destination, audit_text)
        elif destination.read_text(encoding="utf-8") != audit_text:
            raise OSError("Operational audit content changed during export")
        audit_path = f"./{destination.name}"
    except Exception:
        assessment = _unavailable_assessment("The operational audit could not be completed for this export.")
    footer = audit.render_assessment(assessment, audit_path)
    markdown = markdown_base.rstrip() + "\n\n---\n\n" + footer + "\n"
    _write_text(save_path / "complete_report.md", markdown)
    if html:
        from tradingagents.report_html import _render_prepared_report

        page = _render_prepared_report(ticker, final_state, display_settings, parts, summary,
                                       diagnostics_sidecar=bool(frozen), assessment=assessment,
                                       audit_path=audit_path, ground_truth_text=ground_truth_text)
        _write_text(save_path / "complete_report.html", page)
    # A report is successful only when its final contents and linked companion
    # still match the bytes constructed from this prepared presentation.
    if audit_path and (save_path / audit_path).read_text(encoding="utf-8") != audit_text:
        raise OSError("Operational audit changed during export")
    return save_path / "complete_report.md"

