from typing import Annotated

from langgraph.graph import MessagesState
from typing_extensions import TypedDict


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
    run_id: Annotated[str, "Invocation identity preserved across checkpoint resume"]
    evaluation_mode: Annotated[str, "Explicit prospective publication or historical simulation"]
    run_settings: Annotated[dict, "Allowlisted invocation settings retained across resume"]
    publication_versions: Annotated[dict, "Invocation source/prompt fingerprints"]
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
    filing_fact_extraction: Annotated[dict, "Verified filing cells and table coverage"]
    financial_evidence: Annotated[dict, "Canonical immutable source facts for this run"]
    financial_calculations: Annotated[list, "Deterministic accounting checks and calculated values"]
    financial_claim_validation: Annotated[dict, "Canonical fact claims and original unvalidated research"]
    evidence_quality: Annotated[dict, "Authoritative evidence status and check-level reasons"]
    canonical_financial_context: Annotated[str, "Deterministic financial context for downstream agents"]

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
    final_trade_decision: Annotated[str, "Final decision from the Portfolio Manager"]
    unvalidated_outputs: Annotated[dict, "Original model outputs retained for diagnosis, not verified publication"]
    target_validation: Annotated[dict, "Deterministic valuation result and omission reasons"]
    final_rating: Annotated[str, "The Portfolio Manager's 5-tier rating, or REVIEW when it has none"]
    past_context: Annotated[str, "Memory log context for the Portfolio Manager (same-ticker decisions + cross-ticker lessons), written by the Memory Log step"]
    memory_note: Annotated[str, "What the Memory Log step could not settle or read this run, for the report; empty when all went well"]
    portfolio_context: Annotated[str, "Caller-supplied holdings and cash, rendered at run start; empty when not provided"]
