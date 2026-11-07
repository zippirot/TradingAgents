from typing import Annotated, NotRequired

from langgraph.graph import MessagesState
from typing_extensions import TypedDict

from tradingagents.agents.document_access import merge_search_traces
from tradingagents.operational_audit import merge_observations


# Researcher team state
class InvestDebateState(TypedDict):
    bull_history: Annotated[
        str, "Bullish Conversation history"
    ]
    bear_history: Annotated[
        str, "Bearish Conversation history"
    ]
    history: Annotated[str, "Conversation history"]
    current_response: Annotated[str, "Latest response"]
    count: Annotated[int, "Length of the current conversation"]
    document_questions: NotRequired[dict]


# Risk management team state
class RiskDebateState(TypedDict):
    aggressive_history: Annotated[
        str, "Aggressive Agent's Conversation history"
    ]
    conservative_history: Annotated[
        str, "Conservative Agent's Conversation history"
    ]
    neutral_history: Annotated[
        str, "Neutral Agent's Conversation history"
    ]
    history: Annotated[str, "Conversation history"]
    latest_speaker: Annotated[str, "Analyst that spoke last"]
    current_aggressive_response: Annotated[
        str, "Latest response by the aggressive analyst"
    ]
    current_conservative_response: Annotated[
        str, "Latest response by the conservative analyst"
    ]
    current_neutral_response: Annotated[
        str, "Latest response by the neutral analyst"
    ]
    count: Annotated[int, "Length of the current conversation"]


class AgentState(MessagesState):
    operational_observations: Annotated[dict, merge_observations]
    analysis_clock: Annotated[dict, "Resolved IANA analysis timezone and UTC known-at cutoff"]
    run_id: Annotated[str, "Invocation identity preserved across checkpoint resume"]
    evaluation_mode: Annotated[str, "Explicit prospective publication or historical simulation"]
    run_settings: Annotated[dict, "Allowlisted invocation settings retained across resume"]
    publication_versions: Annotated[dict, "Invocation source/prompt fingerprints"]
    prior_thesis: Annotated[dict | None, "Latest known published advisory thesis, independent of settlement"]
    thesis_context: Annotated[str, "Observed prior advisory conditions for all decision roles"]
    thesis_candidate: Annotated[dict | None, "Unvalidated model proposal retained before canonical publication"]
    thesis: Annotated[dict, "Finalized advisory thesis; never automatic rating authority"]
    thesis_version_id: Annotated[str, "Stable thesis version linked to publication"]
    issuer_identity: Annotated[dict, "SEC-map ticker/CIK binding verified by evidence gate"]
    event_comparison: Annotated[dict, "Verified event guidance and aligned provider price windows"]
    decision_context: Annotated[dict, "Canonical research decision card with labeled model opinions"]
    valuation_price_comparison: Annotated[dict, "Replayed dated valuation and reverse sensitivity"]
    price_implied_valuation: Annotated[dict, "Independent source-only price-implied valuation"]
    mechanical_valuation_grid: Annotated[dict, "Recomputed source-based B1 sensitivity; never a forecast or rating authority"]
    market_observation_cutoff: Annotated[str, "Retained UTC market observation instant, fixed across tools and resume"]
    price_observation: Annotated[dict, "Provider-sourced dated completed-session close; never model prose"]
    outcome_summary: Annotated[str, "Known-at horizon measurements; never inferred research evidence"]
    publication_record: Annotated[dict, "Immutable publication identity and first publication time"]
    company_of_interest: Annotated[str, "Company that we are interested in trading"]
    asset_type: Annotated[str, "Asset type under analysis such as stock or crypto"]
    instrument_context: Annotated[str, "Deterministic ticker identity resolved at run start"]
    trade_date: Annotated[str, "The analysis date; data is served as of it"]

    # research step
    market_report: Annotated[str, "Report from the Market Analyst"]
    sentiment_report: Annotated[str, "Report from the Sentiment Analyst"]
    news_report: Annotated[str, "Report from the News Analyst on company and world news"]
    news_coverage: Annotated[dict, "Coverage from actual private news tool results"]
    issuer_event_evidence: Annotated[dict, "Post-analyst issuer metadata supplement; not independent news"]
    fundamentals_report: Annotated[str, "Report from the Fundamentals Analyst"]

    disclosure_evidence: Annotated[dict, "Dated filing excerpts, grounded extraction and retrieval gaps; not a coverage guarantee"]

    filing_evidence: Annotated[dict, "Canonical dated filing documents for this run"]
    transcript_sources: Annotated[dict, "Pinned vendor transcript and SEC call date; unverified wording"]
    document_sources: Annotated[dict, "Immutable full filing corpus; untrusted source text, not accepted facts"]
    document_search_trace: Annotated[dict, merge_search_traces]
    document_search_role: Annotated[str, "Private analyst subgraph role, never model supplied"]
    document_followups: Annotated[dict, "Retained deterministic post-debate source lookups; unvalidated interpretation"]
    filing_terms_evidence: Annotated[dict, "Pre-analyst typed note and lease records bound to full source corpus"]
    filing_fact_extraction: Annotated[dict, "Verified filing cells and table coverage"]
    evidence_acquisition: Annotated[dict, "Retained pre-analyst source vintage and scope; not final evidence authority"]
    shared_source_brief: Annotated[str, "Bounded common primary-source brief consumed by every analyst"]
    financial_evidence: Annotated[dict, "Canonical immutable source facts for this run"]
    financial_calculations: Annotated[list, "Deterministic accounting checks and calculated values"]
    financial_claim_validation: Annotated[dict, "Canonical fact claims and original unvalidated research"]
    evidence_quality: Annotated[dict, "Authoritative evidence status and check-level reasons"]
    canonical_financial_context: Annotated[str, "Deterministic financial context for downstream agents"]

    valuation_reference: Annotated[dict, "Deterministic dated valuation reference points, not fair value"]
    valuation_reference_brief: Annotated[str, "Bounded shared valuation reference context"]
    vendor_expectations: Annotated[dict, "Dated provider guidance and consensus observation"]
    shared_valuation_scenarios: Annotated[dict, "Optional conditional pre-debate calculations; never the final target"]

    # researcher team discussion step
    investment_debate_state: Annotated[
        InvestDebateState, "Current state of the debate on if to invest or not"
    ]
    investment_plan: Annotated[str, "Investment plan from the Research Manager"]

    trader_investment_plan: Annotated[str, "Transaction proposal from the Trader"]

    # risk management team discussion step
    risk_debate_state: Annotated[
        RiskDebateState, "Current state of the debate on evaluating risk"
    ]
    audit_market_tool_evidence: Annotated[dict, "Bounded actual market tool outputs for advisory review, unverified"]
    audit_social_tool_evidence: Annotated[dict, "Bounded actual sentiment inputs for advisory review, unverified"]
    audit_news_tool_evidence: Annotated[dict, "Bounded actual news tool outputs for advisory review, unverified"]
    audit_fundamentals_tool_evidence: Annotated[dict, "Bounded actual fundamentals tool outputs for advisory review, unverified"]
    advisory_audit: Annotated[dict, "Bounded advisory review before the Portfolio Manager; no rating or evidence authority"]
    run_metrics: Annotated[dict, "Observed model calls and debate length with completeness scope"]
    final_trade_decision: Annotated[str, "Final decision from the Portfolio Manager"]
    unvalidated_outputs: Annotated[dict, "Original model outputs retained for diagnosis, not verified publication"]
    target_validation: Annotated[dict, "Deterministic valuation result and omission reasons"]
    final_rating: Annotated[str, "The Portfolio Manager's 5-tier rating, or REVIEW when it has none"]
    past_context: Annotated[str, "Memory log context for the Portfolio Manager (same-ticker decisions + cross-ticker lessons), written by the Memory Log step"]
    memory_note: Annotated[str, "What the Memory Log step could not settle or read this run, for the report; empty when all went well"]
    portfolio_context: Annotated[str, "Caller-supplied holdings and cash, rendered at run start; empty when not provided"]
