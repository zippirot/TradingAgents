"""Pydantic schemas used by agents that produce structured output.

The framework's primary artifact is still prose: each agent's natural-language
reasoning is what users read in the saved markdown reports and what the
downstream agents read as context.  Structured output is layered onto the
three decision-making agents (Research Manager, Trader, Portfolio Manager)
so that:

- Their outputs follow consistent section headers across runs and providers
- Each provider's native structured-output mode is used (json_schema for
  OpenAI/xAI, response_schema for Gemini, tool-use for Anthropic)
- Schema field descriptions become the model's output instructions, freeing
  the prompt body to focus on context and the rating-scale guidance
- A render helper turns the parsed Pydantic instance back into the same
  markdown shape the rest of the system already consumes, so display,
  memory log, and saved reports keep working unchanged
"""

from __future__ import annotations

import re
from copy import deepcopy
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    Field,
    PrivateAttr,
    TypeAdapter,
    ValidationError,
    WithJsonSchema,
    field_validator,
    model_validator,
)

from tradingagents.agents.valuation import EVRevenueTarget, PETarget, TargetResult
from tradingagents.agents.valuation_cases import CaseSelection
from tradingagents.memory.thesis import ThesisCondition

# LLMs sometimes write a placeholder string ("None", "N/A", ...) into an optional
# numeric field instead of omitting it. Coerce those to None so the structured
# call validates instead of erroring (#1058). Pydantic still parses real numeric
# strings ("189.5") to float.
_NULLISH_FLOAT = {"", "none", "n/a", "na", "null", "nil", "-", "tbd", "unknown"}


def _coerce_optional_float(value):
    """Normalise an LLM-written optional numeric field before validation.

    Three shapes show up in practice: a placeholder string ("None", "N/A") in
    place of an omitted value (#1058); a percentage where a price was asked for
    ("15%", #1288); and a human-formatted price ("$1,234.50"). A percentage
    cannot be salvaged into an absolute level -- reading "15%" as 15 would put a
    stop at $15 on a $600 stock -- so it is dropped like a placeholder, leaving
    one bad field to null out instead of failing the whole proposal. A formatted
    price is reduced to its number.

    Anything that is not a single number is dropped the same way. A range
    ("150-160") or a hedge ("around 150") would otherwise reach pydantic, fail
    validation, and discard the whole decision, losing every field the model got
    right along with the price.
    """
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.lower() in _NULLISH_FLOAT or text.endswith("%"):
        return None
    cleaned = text.replace(",", "").lstrip("$€£¥").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Shared rating types
# ---------------------------------------------------------------------------


class PortfolioRating(StrEnum):
    """5-tier rating used by the Research Manager and Portfolio Manager."""

    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"


class TraderAction(StrEnum):
    """3-tier transaction direction used by the Trader.

    The Trader's job is to translate the Research Manager's investment plan
    into a concrete transaction proposal: should the desk execute a Buy, a
    Sell, or sit on Hold this round.  Position sizing and the nuanced
    Overweight / Underweight calls happen later at the Portfolio Manager.
    """

    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"


# ---------------------------------------------------------------------------
# Research Manager
# ---------------------------------------------------------------------------


class DocumentFollowupJudgment(BaseModel):
    """Unvalidated RM interpretation; never a deterministic retrieval result."""

    question_id: str = Field(min_length=1, max_length=32)
    classification: Literal['answered', 'partially_answered', 'unanswered']
    explanation: str = Field(min_length=1, max_length=2000,
        description='For answered/partial: what the passage establishes, figure and source reference, and effect on the bull/bear point. For unanswered: what remains unknown. Unvalidated research judgment.')


class ResearchPlan(BaseModel):
    """Structured investment plan produced by the Research Manager.

    Hand-off to the Trader: the recommendation pins the directional view,
    the rationale captures which side of the bull/bear debate carried the
    argument, and the strategic actions translate that into concrete
    instructions the trader can execute against.
    """

    followup_judgments: list[DocumentFollowupJudgment] = Field(default_factory=list, max_length=4,
        description='One unvalidated interpretation per actual document follow-up question_id; keep retrieval status separate from the answer judgment.')
    revised_cases: Annotated[Any, WithJsonSchema({"anyOf": [
        {"type": "array", "maxItems": 3, "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "request": {"type": "object"}},
            "required": ["name", "request"], "additionalProperties": False}}, {"type": "null"}]})] = Field(default=None, description="Optional one complete replacement valuation_scenarios list; preserve unchanged case names to retain identity. Omit if no revision.")
    recommendation: PortfolioRating = Field(
        description=(
            "The investment recommendation. Exactly one of Buy / Overweight / "
            "Hold / Underweight / Sell. Conflicting arguments alone are not a "
            "reason to Hold: commit to the stronger side, sized by how "
            "decisively it wins. Choose Hold only when the evidence is still "
            "balanced after weighing, or too thin to support a call."
        ),
    )
    rationale: str = Field(
        description=(
            "Conversational summary of the key points from both sides of the "
            "debate, ending with which arguments led to the recommendation. "
            "Speak naturally, as if to a teammate."
        ),
    )
    strategic_actions: str = Field(
        description=(
            "Concrete steps for the trader to implement the recommendation, "
            "including sizing guidance relative to a standard allocation. The "
            "research team does not see the caller's holdings; the trader and "
            "portfolio manager apply the actual position."
        ),
    )


def render_research_plan(plan: ResearchPlan) -> str:
    """Render a ResearchPlan to markdown for storage and the trader's prompt context."""
    lines = [
        f"**Recommendation**: {plan.recommendation.value}",
        "",
        f"**Rationale**: {plan.rationale}",
        "",
        f"**Strategic Actions**: {plan.strategic_actions}",
    ]
    if plan.followup_judgments:
        lines.extend(['', '**Document follow-up judgments (unvalidated)**'])
        lines.extend(f'- {row.question_id}: {row.classification.replace("_", " ")} — {row.explanation}'
                     for row in plan.followup_judgments)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Trader
# ---------------------------------------------------------------------------


class TraderProposal(BaseModel):
    """Structured transaction proposal produced by the Trader.

    The trader reads the Research Manager's investment plan and the analyst
    reports, then turns them into a concrete transaction: what action to
    take, the reasoning that justifies it, and the practical levels for
    entry, stop-loss, and sizing.
    """

    action: TraderAction = Field(
        description="The transaction direction. Exactly one of Buy / Hold / Sell.",
    )
    reasoning: str = Field(
        description=(
            "The case for this action, anchored in the analysts' reports and "
            "the research plan. Two to four sentences."
        ),
    )
    purchase_entry_price: float | None = Field(default=None, description="Optional Buy purchase entry price in quote currency; omit for Hold or Sell.")
    reference_sale_level: float | None = Field(default=None, description="Optional Sell advisory reference level in quote currency; not an order, quote or quantity.")
    _entry_price: float | None = PrivateAttr(default=None)
    stop_loss: float | None = Field(
        default=None,
        description=(
            "Optional Buy-only stop-loss as an absolute price in the instrument's quote "
            "currency (e.g. 172.0), never a percentage. Convert a percentage "
            "distance to the price level it implies, or omit it."
        ),
    )
    advisory_invalidation_level: float | None = Field(
        default=None,
        description="Optional Sell thesis reconsideration level only; never an execution stop or instruction to open a short. Omit unsupported levels.",
    )
    position_sizing: str | None = Field(
        default=None,
        description=(
            "Optional qualitative sizing guidance in words, e.g. 'modest trim, keep a core "
            "position'. Holdings and loss budget are unknown: no percentages, fractions, "
            "share counts or currency amounts."
        ),
    )

    @field_validator("purchase_entry_price", "reference_sale_level", "stop_loss", "advisory_invalidation_level", mode="before")
    @classmethod
    def _nullish_float_to_none(cls, v):
        return _coerce_optional_float(v)

    @model_validator(mode="wrap")
    @classmethod
    def _legacy_entry_adapter(cls, value, handler):
        proposal = handler(value)
        if isinstance(value, dict) and "entry_price" in value:
            proposal._entry_price = _coerce_optional_float(value["entry_price"])
        return proposal

    @property
    def entry_price(self) -> float | None:
        return self._entry_price

    @model_validator(mode="after")
    def _action_levels(self):
        if self.action is not TraderAction.BUY:
            self.purchase_entry_price = None
        if self.action is not TraderAction.SELL:
            self.reference_sale_level = None
        if self.action is TraderAction.SELL:
            if self.advisory_invalidation_level is None:
                self.advisory_invalidation_level = self.stop_loss
            self.stop_loss = None
        else:
            self.advisory_invalidation_level = None
        return self


_NUMERIC_SIZING = re.compile(
    r"\d\s*(?:%|percent\b|per cent\b|bps\b|bp\b|basis points?\b)"
    r"|[$€£]\s*\d|\b(?:USD|EUR|GBP|CAD)\s*\d"
    r"|(?<![\d/])\d\s*/\s*\d(?![\d/])"
    r"|\b(?:one|two|three)[\s-](?:half|halves|thirds?|quarters?|fifths?)\b|\b(?:by|in)\s+half\b"
    r"|\d[\d,.]*\s*(?:k|m|mm|thousand|million)?\s*(?:shares?|USD|dollars)\b"
    r"|\b(?:half|thirds?|quarters?)\s+(?:of\s+)?(?:the|your|its|a)\s+(?:\w+\s+)?"
    r"(?:position|holdings?|allocation|stake|exposure)\b",
    re.I,
)
SIZING_WITHHELD = (
    "Numeric sizing withheld: sizing is qualitative only without verified "
    "portfolio and loss-budget assumptions."
)


def qualitative_sizing(text: str | None) -> str | None:
    """Drop sizing sentences that state an allocation figure; holdings and loss budget are unknown."""
    if not isinstance(text, str) or not _NUMERIC_SIZING.search(text):
        return text
    kept = [sentence for sentence in re.split(r"(?<=[.!?])\s+", text.strip())
            if sentence and not _NUMERIC_SIZING.search(sentence)]
    return " ".join([*kept, SIZING_WITHHELD])


def render_trader_proposal(proposal: TraderProposal) -> str:
    """Render a TraderProposal to markdown.

    The trailing ``FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**`` line is
    preserved for backward compatibility with the analyst stop-signal text
    and any external code that greps for it.
    """
    parts = [
        f"**Action**: {proposal.action.value}",
        "",
        f"**Reasoning**: {proposal.reasoning}",
    ]
    # Named even when absent, so a reader can tell a level the trader chose not
    # to give from one the schema never asked for.
    for label, value in (
        ("Purchase Entry Price", proposal.purchase_entry_price),
        ("Reference Sale Level", proposal.reference_sale_level),
        ("Stop Loss", proposal.stop_loss),
        ("Position Sizing", qualitative_sizing(proposal.position_sizing)),
    ):
        if label == "Stop Loss" and proposal.action is TraderAction.SELL:
            # A Sell has no stop; its level is the advisory invalidation line below.
            continue
        parts.extend(["", f"**{label}**: {value if value is not None and value != '' else 'not provided'}"])
    if proposal.action is TraderAction.SELL:
        parts.extend(["", f"**Advisory Thesis Invalidation Level**: {proposal.advisory_invalidation_level if proposal.advisory_invalidation_level is not None else 'not provided'}"])
    if proposal.entry_price is not None:
        parts.extend(["", f"**Legacy Price Level (meaning unverified)**: {proposal.entry_price}"])
    if proposal.action is TraderAction.SELL:
        parts.extend(["", "Reference sale and thesis invalidation levels are advisory; neither is an execution stop, order, executable quote, share quantity, instruction about unknown holdings, or a short position proposal."])
    parts.extend([
        "",
        f"FINAL TRANSACTION PROPOSAL: **{proposal.action.value.upper()}**",
    ])
    return "\n".join(parts)


CARRIED_PLAN_HEADING = "**Carried from the Research Manager's plan (not restated by the Trader)**"


def label_legacy_trader_price(text: str) -> str:
    """Keep ambiguous legacy or action-inconsistent free-text levels out of canonical purchase fields."""
    # The carried Research Manager block is a copy; only the Trader's own text is relabelled.
    own, heading, carried = text.partition(CARRIED_PLAN_HEADING)
    body = own.rstrip() if heading else own
    return _label_trader_levels(body) + own[len(body):] + heading + carried


def _label_trader_levels(text: str) -> str:
    text = re.sub(
        r"(?im)^([ \t]*(?:[-*][ \t]+)?)(?:\*\*)?Entry Price(?:\*\*)?:",
        r"\1**Legacy Price Level (meaning unverified)**:", text,
    )
    actions = re.findall(r"(?im)^\s*(?:\*\*)?Action(?:\*\*)?:\s*(Buy|Hold|Sell)\b", text)
    actions += re.findall(r"(?im)^FINAL TRANSACTION PROPOSAL:\s*\*\*(BUY|HOLD|SELL)\*\*", text)
    if actions and all(action.casefold() == "buy" for action in actions):
        return text

    had_stop = bool(re.search(r"(?im)^\s*(?:\*\*)?Stop[ -]Loss", text))
    text = re.sub(
        r"(?im)^([ \t]*(?:[-*][ \t]+)?)(?:\*\*)?Stop[ -]Loss(?:\*\*)?:",
        r"\1**Advisory Thesis Invalidation Level (unvalidated)**:", text,
    )
    if had_stop and actions and all(action.casefold() == "sell" for action in actions):
        text += "\nThesis invalidation is advisory, not an execution stop or short position proposal; holdings may be unknown."

    def ambiguous_purchase(match):
        value = match.group(2)
        if value.strip().casefold() == "not provided":
            return match.group(0)
        return match.group(1) + "**Legacy Price Level (meaning unverified)**: " + value

    return re.sub(
        r"(?im)^([ \t]*(?:[-*][ \t]+)?)(?:\*\*)?Purchase Entry Price(?:\*\*)?:[ \t]*(.*)$",
        ambiguous_purchase, text,
    )


# ---------------------------------------------------------------------------
# Portfolio Manager
# ---------------------------------------------------------------------------


ValuationRequest = Annotated[CaseSelection | EVRevenueTarget | PETarget, Field(discriminator="method")]
_VALUATION_REQUEST = TypeAdapter(ValuationRequest)


class AdvisoryDisposition(BaseModel):
    condition_id: str = Field(min_length=1, max_length=128)
    disposition: Literal["kept", "overridden", "retired"]
    reason: str = Field(min_length=1, max_length=1000)


class ThesisProposal(BaseModel):
    """Optional research proposal; observations and publication stay deterministic."""
    rationale: str = Field(default="", max_length=3000)
    assumptions: list[str] = Field(default_factory=list, max_length=8)
    evidence_refs: list[str] = Field(default_factory=list, max_length=16)
    conditions: list[ThesisCondition] | None = Field(default=None, max_length=8,
        description="Advisory conditions of kind metric (default legacy shape: canonical metric/definition, period, comparison, threshold, unit, basis), price_level (positive completed-close threshold, comparator, instrument quote currency, expiry), or event (observable description, confirming evidence, expiry; no threshold/comparator). Every kind needs rationale and thesis_role. None retains prior conditions; [] explicitly retires them. These are research questions, never trading rules.")
    dispositions: list[AdvisoryDisposition] = Field(default_factory=list,
        description="For each prior condition ID, say kept, overridden or retired and why; do not hide a breach.")


_EVENT_CASE_WEIGHT = {"type": "object", "properties": {
    "case_id": {"type": "string"}, "version": {"type": "integer"}, "weight": {"type": "number"},
}, "required": ["case_id", "version", "weight"], "additionalProperties": False}


class PortfolioDecision(BaseModel):
    """Structured output produced by the Portfolio Manager.

    The model fills every field as part of its primary LLM call; no separate
    extraction pass is required. Field descriptions double as the model's
    output instructions, so the prompt body only needs to convey context and
    the rating-scale guidance.
    """

    rating: PortfolioRating = Field(
        description=(
            "The final position rating. Exactly one of Buy / Overweight / Hold / "
            "Underweight / Sell, picked based on the analysts' debate. "
            "Conflicting arguments alone are not a reason to Hold: commit to the "
            "stronger side, sized by how decisively it wins. Choose Hold only "
            "when the evidence is still balanced after weighing, or too thin to "
            "support a call."
        ),
    )
    executive_summary: str = Field(
        description=(
            "A concise action plan covering entry strategy, position sizing, "
            "key risk levels, and time horizon. Two to four sentences."
        ),
    )
    investment_thesis: str = Field(
        description=(
            "Detailed reasoning anchored in specific evidence from the analysts' "
            "debate. If prior lessons are referenced in the prompt context, "
            "incorporate them; otherwise rely solely on the current analysis."
        ),
    )
    price_target: float | None = Field(
        default=None,
        description="Legacy input retained for compatibility only; never an authoritative target. Use valuation_request with canonical fact IDs, or omit the target.",
    )
    no_case_reason: str | None = Field(default=None, max_length=1200, description="Brief reason when no supported case is adopted.")
    horizon_reason: str | None = Field(default=None, max_length=1200, description="Required nonblank reason for overriding the configured decision horizon; not a forecast period.")
    valuation_request: ValuationRequest | None = Field(
        default=None,
        description=(
            "Select an active case by method=case, exact case_id, version, and explicit rerating_assumption (none, or a justified dated link). "
            "Reference exact canonical financial fact IDs; make forecasts, multiples and subjective "
            "weights explicit. Never invent missing inputs. Management guidance/ambition needs "
            "a separately source-validated outlook reference; model assertions do not establish one."
        ),
    )
    thesis_candidate: ThesisProposal | None = Field(default=None,
        description="Persistent advisory thesis: material assumptions, exact evidence references, metric, completed-close price and observable event conditions, and reason for each prior disposition. Research proposals are not verified facts or automatic trading rules.")
    _unvalidated_thesis_candidate: object = PrivateAttr(default=None)
    _unvalidated_valuation_request: object = PrivateAttr(default=None)

    @model_validator(mode="wrap")
    @classmethod
    def _retain_valuation_request(cls, data, handler):
        original = data.get("valuation_request") if isinstance(data, dict) else getattr(data, "_unvalidated_valuation_request", None)
        thesis_original = data.get("thesis_candidate") if isinstance(data, dict) else getattr(data, "_unvalidated_thesis_candidate", None)
        result = handler(data)
        if isinstance(thesis_original, BaseModel):
            thesis_original = thesis_original.model_dump(mode="json")
        result._unvalidated_thesis_candidate = deepcopy(thesis_original)
        if isinstance(original, BaseModel):
            original = original.model_dump(mode="json")
        result._unvalidated_valuation_request = deepcopy(original)
        return result

    @field_validator("thesis_candidate", mode="before")
    @classmethod
    def _invalid_thesis_to_none(cls, value):
        if value is None:
            return None
        try:
            return ThesisProposal.model_validate(value)
        except (ValidationError, TypeError):
            return None

    @field_validator("valuation_request", mode="before")
    @classmethod
    def _invalid_valuation_to_none(cls, value):
        if value is None:
            return None
        try:
            return _VALUATION_REQUEST.validate_python(value)
        except (ValidationError, TypeError):
            # A broken optional target must not discard the valid rating and
            # trigger another provider call. The raw request remains diagnostic.
            return None

    time_horizon: str | None = Field(
        default=None,
        description="Optional recommended holding period, e.g. '3-6 months'.",
    )

    @field_validator("price_target", mode="before")
    @classmethod
    def _nullish_float_to_none(cls, v):
        return _coerce_optional_float(v)


class RequiredHorizonPortfolioDecision(PortfolioDecision):
    """Fresh-call contract; legacy records still use PortfolioDecision.

    A provider omission remains diagnostic rather than causing another model call
    or discarding its otherwise valid rating. Publication checks completeness.
    """
    audit_dispositions: Annotated[Any, WithJsonSchema({
        "anyOf": [
            {"type": "array", "items": {"type": "object", "properties": {
                "finding_id": {"type": "string"},
                "disposition": {"type": "string", "enum": ["accepted", "rejected"]},
                "reason": {"type": "string"},
            }, "required": ["finding_id", "disposition", "reason"], "additionalProperties": False}},
            {"type": "null"},
        ],
    })] = Field(
        default=None,
        description="Only when the audit completed with findings: one advisory response per finding, a list of {finding_id, disposition (accepted or rejected), reason (short, at most 500 characters)}. Use exact supplied stable IDs. Otherwise omit/null. Never a rating/evidence authority or publication gate. Invalid responses are retained for separate advisory validation, not a retry.",
    )

    scenario_view: Annotated[Any, WithJsonSchema({
        "anyOf": [
            {"type": "array", "items": {"type": "object", "properties": {
                "case_id": {"type": "string"},
                "version": {"type": "integer"},
                "disposition": {"type": "string", "enum": ["accepted", "rejected"]},
                "weight": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                "rejected_input": {"anyOf": [
                    {"type": "string", "enum": ["revenue_forecast", "multiple", "shares", "cash", "obligations", "funding"]},
                    {"type": "null"}]},
                "reason": {"type": "string"},
            }, "required": ["case_id", "version", "disposition", "weight", "rejected_input", "reason"],
                "additionalProperties": False}},
            {"type": "null"},
        ],
    })] = Field(
        default=None,
        description="When priced scenario cases are listed in the prompt: one entry per case with its exact case_id and version, disposition accepted or rejected, a short reason, a weight above 0 and at most 1 for an accepted case (accepted weights sum to 1; subjective, not measured probabilities) and, for a rejected case, the single input rejected in rejected_input. Null when no priced case is listed.",
    )
    rating_basis_reason: str | None = Field(
        default=None, max_length=1200,
        description="When the rating points against your accepted scenarios (their weighted value differs from the close by more than 10 percent the other way, or it returns more than the required return under a bearish rating or less under a bullish one): why the rating still stands, with figures.",
    )

    event_view: Annotated[Any, WithJsonSchema({
        "anyOf": [
            {"type": "array", "items": {"type": "object", "properties": {
                "condition_id": {"type": "string"},
                "expected_date": {"type": "string"},
                "favourable_when": {"type": "string", "enum": ["met", "not_met"]},
                "favourable_weights": {"type": "array", "items": _EVENT_CASE_WEIGHT},
                "adverse_weights": {"type": "array", "items": _EVENT_CASE_WEIGHT},
                "reason": {"type": "string"},
            }, "required": ["condition_id", "expected_date", "favourable_when", "favourable_weights",
                            "adverse_weights", "reason"], "additionalProperties": False}},
            {"type": "null"},
        ],
    })] = Field(
        default=None,
        description="When the prompt lists open advisory conditions for a six-month view from dated events and you accept two or more cases: one to three entries, each with the exact condition_id, the expected_date (YYYY-MM-DD, inside the horizon), favourable_when (met or not_met), the case weights you would hold after the favourable and after the adverse outcome (every accepted case once with its case_id and version, 0 allowed, each set summing to 1), and a short reason. Your scenario_view weights must lie between the two sets. Null otherwise. No probabilities.",
    )

    change_assessment: Annotated[Any, WithJsonSchema({
        "anyOf": [
            {"type": "object", "properties": {
                "status": {"type": "string", "enum": ["no_material_change", "strengthens", "weakens", "reverses"]},
                "reason": {"type": "string"},
            }, "required": ["status", "reason"], "additionalProperties": False},
            {"type": "null"},
        ],
    })] = Field(
        default=None,
        description="When a 'Since the last decision' list is in the prompt: what the listed changes mean for the earlier call, as status no_material_change, strengthens, weakens or reverses, with one sentence naming the change that matters. A rating different from the earlier one must be weakens or reverses. Null when no such list is supplied.",
    )

    time_horizon: str | None = Field(
        description="Required explicit decision horizon: positive days/weeks/months (including ranges), or an ISO date. Use the configured default supplied in the prompt unless overriding with a nonblank horizon_reason. Separate from the forecast period. If unknown, return null and the decision is incomplete.",
    )

    @model_validator(mode="before")
    @classmethod
    def _retain_missing_horizon(cls, value):
        if isinstance(value, dict) and "time_horizon" not in value:
            return {**value, "time_horizon": None}
        return value


def render_pm_decision(decision: PortfolioDecision, target_result: TargetResult | dict | None = None) -> str:
    """Render a PortfolioDecision back to the markdown shape the rest of the system expects.

    Memory log, CLI display, and saved report files all read this markdown,
    so the rendered output preserves the exact section headers (``**Rating**``,
    ``**Executive Summary**``, ``**Investment Thesis**``) that downstream
    parsers and the report writers already handle.
    """
    parts = [
        f"**Rating**: {decision.rating.value}",
        "",
        f"**Executive Summary**: {decision.executive_summary}",
        "",
        f"**Investment Thesis**: {decision.investment_thesis}",
    ]
    # Named even when absent: a missing line reads as a field nobody asked for,
    # so a reader cannot tell "no target" from "target not reported".
    parts.extend(["", render_target_result(target_result)])
    parts.extend(["", f"**Time Horizon**: {decision.time_horizon or 'incomplete — explicit decision horizon required'}"])
    return "\n".join(parts)


def _target_text(value) -> str:
    """Keep source/assumption text on one escaped line in deterministic output."""
    return " ".join(str(value).split()).replace("|", r"\|")


def render_target_result(result: TargetResult | dict | None) -> str:
    """Render a deterministic result supplied by a validating caller.

    This is presentation, not validation of an arbitrary dictionary. Direct
    publication boundaries must replay the saved request against canonical
    evidence before passing the result here.
    """
    from tradingagents.agents.valuation_comparison import display_number, display_value

    if isinstance(result, dict):
        try:
            result = TargetResult.model_validate({key: value for key, value in result.items() if key in TargetResult.model_fields})
        except ValidationError:
            result = None
    if result is None or result.status != "supported" or result.target is None:
        reasons = result.reasons if result is not None else ("No validated valuation bridge provided.",)
        text = "**Price Target**: not provided — " + " ".join(_target_text(reason) for reason in reasons)
        if result is not None and any(row.funding_gap for row in result.scenario_results):
            text += "\n\nUnfunded capital diagnostics; no conditional price or return is published.\n\n"
            text += "| Scenario | Capital date | Closing cash | Closing obligations | Common shares | Funding gap |\n| --- | --- | ---: | ---: | ---: | ---: |\n"
            for row in result.scenario_results:
                text += f"| {_target_text(row.name)} | {row.capital_date} | {display_number(row.closing_cash)} | {display_number(row.closing_obligations)} | {display_number(row.shares_outstanding)} | {display_number(row.funding_gap)} |\n"
                text += "\n".join("- Unvalidated funding assumption: " + _target_text(item) for item in row.funding_assumptions) + "\n"
        return text
    linked = bool(result.decision_date and result.rerating_assumption) and all(
        row.capital_date is not None and row.capital_date <= result.decision_date
        for row in result.scenario_results)
    dated = (all(row.multiple_assumption_date is not None for row in result.scenario_results)
             if result.method == "ev_revenue" else result.multiple_assumption_date is not None)
    linked = linked and dated
    assessment = result.decision_use
    historical = assessment.classification == "historical_diagnostic"
    label = ("Historical diagnostic" if historical else
             "Conditional decision-date valuation" if linked else "Conditional valuation sensitivity")
    parts = [
        f"**{label}**: {display_value(result.target, _target_text(result.unit))} (conditional calculation)",
        "",
        f"**Valuation method**: {_target_text(result.method)}; {_target_text(result.accounting_basis)}.",
        f"**Valuation period**: {result.valuation_period_start} to {result.valuation_period_end}.",
        "**Source fact IDs**: " + ", ".join(_target_text(identifier) for identifier in result.input_fact_ids),
        "Display values are rounded; exact arithmetic remains in evidence.json → target_validation.",
    ]
    parts.append(f"**Decision date**: {result.decision_date or 'not specified'}; rerating assumption: {_target_text(result.rerating_assumption or 'not supplied')}. No automatic near-term target or discounting is inferred.")
    if not assessment.final_target_eligible:
        parts.append("**Price Target**: not provided — decision-use suitability: "
                     + _target_text(assessment.suitability) + ". "
                     + " ".join(_target_text(reason) for reason in assessment.reasons))
    if historical:
        parts.append("Historical arithmetic is retained for inspection; it is not a forward earnings forecast or endorsed fair value.")
        for event in assessment.events:
            parts.append("Capital-change evidence: " + _target_text(event.fact_id)
                         + "; sources " + ", ".join(_target_text(item) for item in event.source_ids)
                         + f"; interval {event.period_start} to {event.period_end}; filed "
                         + ", ".join(str(item) for item in event.filed_dates) + ".")
    if result.weight_rationale:
        parts.append("**Subjective weight rationale**: " + _target_text(result.weight_rationale))
    if result.method == "pe":
        parts.append(f"**Multiple assumption date**: {result.multiple_assumption_date or 'not supplied'}.")
        parts.append(f"**Earnings bridge**: {display_value(result.earnings_value, _target_text(result.unit))} × {display_number(result.multiple)} = {display_number(result.target)}; {_target_text(result.eps_basis)} EPS.")
    if result.method == "ev_revenue":
        parts.extend([
            f"**Source capital snapshot**: {result.capital_snapshot_date}; each scenario uses its own capital bridge below.",
            "",
            "| Scenario label (unvalidated) | Subjective weight | Revenue assumption | Multiple assumption | Enterprise value | Equity value | Price |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ])
        for scenario in result.scenario_results:
            parts.append(f"| {_target_text(scenario.name)} | {display_number(scenario.weight)} | {display_number(scenario.revenue)} | {display_number(scenario.multiple)} | {display_number(scenario.enterprise_value)} | {display_number(scenario.equity_value)} | {display_number(scenario.price)} |")
        parts.extend(["", "| Scenario | Capital date | Closing cash | Closing obligations | Common shares | Net obligations | Funding gap | Multiple assumption date |",
                      "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |"])
        for scenario in result.scenario_results:
            parts.append(f"| {_target_text(scenario.name)} | {scenario.capital_date} | {display_number(scenario.closing_cash)} | {display_number(scenario.closing_obligations)} | {display_number(scenario.shares_outstanding)} | {display_number(scenario.net_obligations)} | {display_number(scenario.funding_gap)} | {scenario.multiple_assumption_date or 'not supplied'} |")
            parts.extend("- Unvalidated funding assumption: " + _target_text(item) for item in scenario.funding_assumptions)
        parts.append("Equity value = enterprise value − net obligations; price = equity value / common shares outstanding.")
    if result.assumptions:
        parts.extend(["", "**Conditional assumptions; free-form rationales remain unvalidated**:"])
        parts.extend("- " + _target_text(assumption) for assumption in result.assumptions)
    if result.warnings:
        parts.extend(["", "**Valuation limitations**:"])
        parts.extend("- " + _target_text(warning) for warning in result.warnings)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Sentiment Analyst
# ---------------------------------------------------------------------------


class SentimentBand(StrEnum):
    """Discrete sentiment direction produced by the Sentiment Analyst.

    Six tiers keep the signal granular enough to be actionable while remaining
    small enough for every provider to map reliably from its JSON output.
    """

    BULLISH = "Bullish"
    MILDLY_BULLISH = "Mildly Bullish"
    NEUTRAL = "Neutral"
    MIXED = "Mixed"
    MILDLY_BEARISH = "Mildly Bearish"
    BEARISH = "Bearish"


class SentimentReport(BaseModel):
    """Structured sentiment report produced by the Sentiment Analyst.

    Replaces the previous free-form prose output so downstream consumers
    (dashboards, audit logs, PDF renderers, other agents) can read
    ``overall_band`` and ``overall_score`` without maintaining fragile regex
    fallbacks that drift with every model release. ``narrative`` preserves the
    rich source-by-source analysis; ``render_sentiment_report`` prepends a
    deterministic header so the saved report stays human-readable.
    """

    overall_band: SentimentBand = Field(
        description=(
            "Overall sentiment direction. Exactly one of: "
            "Bullish / Mildly Bullish / Neutral / Mixed / Mildly Bearish / Bearish. "
            "Use Mixed when sources point in clearly different directions. "
            "Use Neutral only when all sources are genuinely silent or non-committal."
        ),
    )
    overall_score: float = Field(
        ge=0.0,
        le=10.0,
        description=(
            "Numeric sentiment intensity on a 0–10 scale. "
            "0 = maximally bearish, 5 = neutral, 10 = maximally bullish. "
            "Guideline for consistency with overall_band: "
            "Bullish ~6.5–10, Mildly Bullish ~5.5–6.4, Neutral/Mixed ~4.5–5.5, "
            "Mildly Bearish ~3.5–4.4, Bearish ~0–3.4. "
            "Only the 0–10 bounds are enforced."
        ),
    )
    confidence: Literal["low", "medium", "high"] = Field(
        description=(
            "Confidence in the assessment based on data quality and sample size. "
            "Use 'low' when one or more sources returned a placeholder or fewer "
            "than 5 data points; 'medium' when data is present but sparse; "
            "'high' when all three sources returned substantive data."
        ),
    )
    narrative: str = Field(
        description=(
            "Full sentiment report covering, in order: "
            "(1) source-by-source breakdown with specific evidence (cite message "
            "counts, ratios, notable posts); "
            "(2) cross-source divergences and alignments; "
            "(3) dominant narrative themes; "
            "(4) catalysts and risks surfaced by the data; "
            "(5) a markdown table summarising key sentiment signals, their "
            "direction, source, and supporting evidence. "
            "Keep it informative and substantive: develop each section thoroughly "
            "with concrete evidence so every point adds new signal for the trader."
        ),
    )


def render_sentiment_report(report: SentimentReport) -> str:
    """Render a SentimentReport to the markdown shape the rest of the system expects.

    The structured header (band + score + confidence) is prepended to the
    narrative so the saved report is both human-readable and machine-parseable
    without regex.
    """
    return "\n".join([
        f"**Overall Sentiment:** **{report.overall_band.value}** "
        f"(Score: {report.overall_score:.1f}/10)",
        f"**Confidence:** {report.confidence.capitalize()}",
        "",
        report.narrative,
    ])
