"""The caller's book, as the decision agents see it.

Optional input to a run: what is held, at what average price, and how much cash
is free. Without it the agents cannot tell adding to a full position from
opening a new one. Three states are distinct and must stay so: a position, a
flat book, and no context at all, since treating "not provided" as "flat" would
invent a fact about the caller's account.

Broker-neutral by construction: quantities are generic units and the currency is
whatever label the caller passes, so nothing here implies a venue or an
execution path.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator

RATINGS = ("Buy", "Overweight", "Hold", "Underweight", "Sell")
SIZING_LABEL = "Position and sizing"
AT_STANDARD_BAND = Decimal("0.05")  # within 5 percent of the standard weight counts as at standard
RANGE_SESSIONS = 14
_SIZING_FIELDS = ("portfolio_value", "default_standard_weight", "loss_budget", "rating_weights", "show_amounts")
# Read only by the portfolio review. They never enter a run's state, its agents' prompts or the file fingerprint.
_REVIEW_ONLY = {"watchlist": True, "limits": True, "positions": {"__all__": {"sector"}}}


class Position(BaseModel):
    ticker: str = Field(description="Instrument symbol, e.g. AAPL")
    quantity: float = Field(description="Signed units held; negative is short")
    average_price: float | None = Field(default=None, description="Average entry price per unit")
    standard_weight: float | None = Field(
        default=None, gt=0, le=1, description="Normal size of this position as a fraction of the portfolio")
    sector: str | None = Field(default=None, description="Sector for the review's sector limit; overrides the vendor's")


class Limits(BaseModel):
    max_position_weight: float | None = Field(default=None, gt=0, le=1, description="Most one stock may be, as a fraction")
    max_sector_weight: float | None = Field(default=None, gt=0, le=1, description="Most one sector may be, as a fraction")
    min_cash_weight: float | None = Field(default=None, ge=0, lt=1, description="Cash kept back, as a fraction")
    rating_max_age_days: int = Field(default=30, gt=0, description="A rating older than this is flagged stale")


class PortfolioContext(BaseModel):
    cash: float | None = Field(default=None, description="Free cash available")
    currency: str | None = Field(default=None, description="Currency label for cash and prices")
    positions: list[Position] = Field(default_factory=list)
    portfolio_value: float | None = Field(
        default=None, gt=0, description="Total portfolio value in the same currency as the instrument's price")
    default_standard_weight: float | None = Field(
        default=None, gt=0, le=1, description="Normal position size as a fraction of the portfolio")
    loss_budget: float | None = Field(
        default=None, gt=0, le=1, description="Most you accept losing on one position, as a fraction of the portfolio")
    rating_weights: dict[str, float] | None = Field(
        default=None, description="What each rating means as a multiple of the standard weight, e.g. Underweight 0.5")
    show_amounts: bool = Field(default=False, description="Show currency amounts beside percentages and units")
    watchlist: list[str] = Field(default_factory=list, description="Tickers not held that the review also covers")
    limits: Limits | None = Field(default=None, description="Position, sector and cash limits for the review")

    @field_validator("rating_weights")
    @classmethod
    def _known_ratings(cls, value):
        if value is None:
            return None
        unknown = sorted(set(value) - set(RATINGS))
        if unknown:
            raise ValueError(f"rating_weights has unknown rating(s) {unknown}; use {', '.join(RATINGS)}")
        if any(not 0 <= multiple <= 20 for multiple in value.values()):
            raise ValueError("rating_weights multiples must be between 0 and 20")
        return value

    def review_tickers(self) -> list[str]:
        """Held tickers, then the watchlist; upper-cased, each once."""
        names = [p.ticker for p in self.positions] + list(self.watchlist)
        return list(dict.fromkeys(name.strip().upper() for name in names if name.strip()))

    def position_in(self, ticker: str) -> Position | None:
        return next((p for p in self.positions if p.ticker.upper() == ticker.strip().upper()), None)

    def render(self, ticker: str) -> str:
        """The portfolio block for the decision agents, led by the analyzed instrument."""
        symbol = ticker.strip().upper()
        held = self.position_in(symbol)
        if held is None:
            lines = [f"- No current position in {symbol}. With nothing held, Underweight and Sell both mean do not buy; "
                     "neither opens a position"]
        else:
            price = f", average price {held.average_price:,.2f}" if held.average_price is not None else ""
            lines = [f"- Current position in {symbol}: {held.quantity:,.4g} units{price}"]
        if self.cash is not None:
            lines.append(f"- Cash available: {self.cash:,.2f}{' ' + self.currency if self.currency else ''}")
        others = [p for p in self.positions if p is not held]
        if others:
            lines.append("- Other positions: " + ", ".join(f"{p.ticker.upper()} {p.quantity:,.4g}" for p in others))
        return "Portfolio at the analysis date:\n" + "\n".join(lines)

    def fingerprint(self) -> str:
        """Stable digest of the book, so a changed one cannot resume a stale run."""
        sized = (any(getattr(self, name) != type(self).model_fields[name].default for name in _SIZING_FIELDS)
                 or any(p.standard_weight is not None for p in self.positions))
        # A file with none of the sizing inputs keeps the digest it always had.
        payload = self.model_dump_json(exclude=_REVIEW_ONLY) if sized else self.model_dump_json(
            exclude={**dict.fromkeys(_SIZING_FIELDS, True), "watchlist": True, "limits": True,
                     "positions": {"__all__": {"standard_weight", "sector"}}})
        return hashlib.sha256(payload.encode()).hexdigest()[:12]

    def inputs(self) -> dict:
        """The book as run state: read locally, shown to this run's agents, never written to a publication."""
        return {**self.model_dump(mode="json", exclude=_REVIEW_ONLY), "fingerprint": self.fingerprint()}


def _number(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def average_daily_move(closes) -> Decimal | None:
    """Mean absolute close-to-close change over the last sessions, as a fraction; None when too few closes."""
    values = [number for number in map(_number, closes) if number is not None and number > 0]
    if len(values) < RANGE_SESSIONS + 1:
        return None
    recent = values[-(RANGE_SESSIONS + 1):]
    return sum(abs(b / a - 1) for a, b in zip(recent, recent[1:], strict=False)) / RANGE_SESSIONS


def sizing(inputs, ticker: str, quote, *, levels=(), closes=(), rating: str | None = None) -> dict:
    """Arithmetic on the caller's inputs at a dated close. No judgment and no order.

    ``inputs`` is ``PortfolioContext.inputs()`` as kept in run state. Whatever an
    input does not allow is left out and said so; nothing is assumed.
    """
    if not isinstance(inputs, dict) or _number(inputs.get("portfolio_value")) is None:
        return {"status": "not_configured"}
    result = {"status": "unavailable", "fingerprint": inputs.get("fingerprint"), "ticker": ticker.strip().upper(),
              "show_amounts": bool(inputs.get("show_amounts"))}
    close = _number(quote.get("close")) if isinstance(quote, dict) else None
    if close is None or close <= 0 or not quote.get("session_date"):
        return {**result, "reason": "no completed close is available for this run"}
    currency = inputs.get("currency")
    if currency and quote.get("currency") and currency.upper() != str(quote["currency"]).upper():
        return {**result, "reason": f"the portfolio file is in {currency} and the price is in {quote['currency']}"}
    value = _number(inputs["portfolio_value"])
    held = next((p for p in inputs.get("positions") or () if p["ticker"].upper() == result["ticker"]), None)
    quantity = _number(held["quantity"]) if held else Decimal(0)
    weight = quantity * close / value
    result.update(status="available", close=str(close), currency=quote.get("currency"),
                  session_date=quote["session_date"], quantity=str(quantity), current_weight=str(weight),
                  portfolio_value=str(value), standard_weight=None, standing=None, targets=[], final=None, loss=None)
    standard = _number((held or {}).get("standard_weight")) or _number(inputs.get("default_standard_weight"))
    if standard is not None:
        gap = weight - standard
        result.update(standard_weight=str(standard),
                      standing="at" if abs(gap) <= standard * AT_STANDARD_BAND else "above" if gap > 0 else "below")
        for name in RATINGS:
            multiple = _number((inputs.get("rating_weights") or {}).get(name))
            if multiple is None:
                continue
            target = standard * multiple
            row = {"rating": name, "multiple": str(multiple), "target_weight": str(target),
                   "units_change": str((target * value / close - quantity).quantize(Decimal(1)))}
            # A rating below Hold never opens or enlarges a long position: with less held than its weight, it is no purchase.
            if name in ("Underweight", "Sell") and quantity >= 0 and target > weight:
                row.update(target_weight=str(weight), units_change="0", scale_weight=str(target), no_addition=True)
            result["targets"].append(row)
            if name == rating:
                result["final"] = row
    budget = _number(inputs.get("loss_budget"))
    if budget is not None:
        rows = []
        for level in levels:
            price = _number(level)
            # A long position loses below the close, a short one above it.
            if price is not None and price > 0 and quantity and (price < close) == (quantity > 0):
                rows.append({"kind": "level", "level": str(price), "loss": str(abs(quantity) * abs(close - price) / value)})
        move = average_daily_move(closes)
        if move is not None and quantity:
            rows.append({"kind": "daily_move", "move": str(move), "loss": str(abs(quantity) * close * move / value)})
        for row in rows:
            row["inside"] = Decimal(row["loss"]) <= budget
        result["loss"] = {"budget": str(budget), "rows": rows, "daily_move_available": move is not None}
        # The same test at the size the final rating calls for, so a recommendation to buy is tested before it is acted on.
        final = result["final"]
        weight_at_target = Decimal(final["target_weight"]) if final else Decimal(0)
        if final and weight_at_target > 0 and Decimal(final["units_change"]):
            at = [{"kind": "level", "level": str(price), "loss": str(weight_at_target * (close - price) / close)}
                  for price in map(_number, levels) if price is not None and 0 < price < close]
            if move is not None:
                at.append({"kind": "daily_move", "move": str(move), "loss": str(weight_at_target * move)})
            for row in at:
                row["inside"] = Decimal(row["loss"]) <= budget
            result["loss"]["target"] = {"rating": final["rating"], "weight": str(weight_at_target), "rows": at,
                                        "budget_fall": str(budget / weight_at_target) if budget < weight_at_target else None}
    return result


def downside_test(result, rule) -> dict | None:
    """The size the final rating calls for against the lowest accepted case and the loss budget.

    ``rule`` is the decision card's sizing rule. None when there is no final size, no loss budget, or no
    accepted case below the close: nothing is assumed in their place.
    """
    final = result.get("final") if isinstance(result, dict) and result.get("status") == "available" else None
    budget = _number((result.get("loss") or {}).get("budget")) if final else None
    fall = _number(rule.get("fall")) if isinstance(rule, dict) and rule.get("status") == "available" else None
    weight = _number(final["target_weight"]) if final else None
    if None in (budget, fall, weight) or fall <= 0 or weight <= 0:
        return None
    loss = weight * fall
    return {"rating": final["rating"], "role": rule.get("role"), "name": rule.get("name"), "fall": str(fall),
            "weight": str(weight), "loss": str(loss), "budget": str(budget), "inside": loss <= budget,
            "ceiling": str(budget / fall)}


def _percent(value, places=1):
    return f"{Decimal(value) * 100:.{places}f}%"


def _units(value):
    return f"{Decimal(value):,.4f}".rstrip("0").rstrip(".")


def render_sizing(result, *, final: bool = False) -> list[str]:
    """Lines of the block; empty when no portfolio value was supplied."""
    if not isinstance(result, dict) or result.get("status") in (None, "not_configured"):
        return []
    mark = f"file fingerprint {result.get('fingerprint')}"
    if result["status"] != "available":
        return [f"**{SIZING_LABEL}**: not computed; {result['reason']} ({mark})."]
    money = result["currency"] or ""
    amounts = result["show_amounts"]
    close, value, quantity = Decimal(result["close"]), Decimal(result["portfolio_value"]), Decimal(result["quantity"])

    def amount(number):
        return f", {number:,.2f} {money}".rstrip() if amounts else ""
    lines = [f"**{SIZING_LABEL}** (arithmetic on your portfolio file, {mark}, at the {result['session_date']} close of "
             f"{close:.2f} {money}; not an order):".replace("  ", " "),
             (f"- Current position in {result['ticker']}: {_units(quantity)} units, "
              f"{_percent(result['current_weight'])} of the portfolio{amount(quantity * close)}." if quantity else
              f"- Current position in {result['ticker']}: none.")]
    if result["standard_weight"] is None:
        lines.append("- Standard weight: not supplied, so above or below standard and rating targets are not stated.")
    else:
        lines.append(f"- Standard weight: {_percent(result['standard_weight'])}. The position is {result['standing']} "
                     "standard (within 5 percent of the standard weight counts as at standard).")

        def move(row):
            if row.get("no_addition"):
                return ("no purchase (a rating below Hold never adds to a position; "
                        + ("nothing is held" if not quantity else
                           f"you hold less than its {_percent(row['scale_weight'])} weight") + ")")
            change = Decimal(row["units_change"])
            gap = "what you hold now" if not change else (
                f"about {_units(abs(change))} units {'more' if change > 0 else 'fewer'} than you hold"
                f"{amount(abs(change) * close)}")
            return f"{_percent(row['target_weight'])} of the portfolio ({gap})"
        if not result["targets"]:
            lines.append("- Rating targets: no rating_weights supplied, so no target weight is stated.")
        elif final and result["final"]:
            lines.append(f"- For the final rating {result['final']['rating']} on your scale: {move(result['final'])}.")
        elif final:
            lines.append("- Rating targets: your rating_weights has no entry for the final rating.")
        else:
            lines.append("- What each rating means on your scale: "
                         + "; ".join(f"{row['rating']} {move(row)}" for row in result["targets"]) + ".")
    loss = result["loss"]
    if loss is None:
        lines.append("- Loss budget: not supplied, so no loss is compared with a limit.")
    elif not quantity:
        lines.append(f"- Loss budget {_percent(loss['budget'], 2)} of the portfolio: no position, so nothing is at risk"
                     + (" now." if final and loss.get("target") else "."))
    else:
        parts = []
        for row in loss["rows"]:
            where = (f"at the advisory review level {Decimal(row['level']):.2f} {money}".rstrip() if row["kind"] == "level"
                     else f"at one average daily move ({_percent(row['move'])}, mean absolute close-to-close change "
                          f"over {RANGE_SESSIONS} sessions)")
            parts.append(f"{where} the position loses {_percent(row['loss'], 2)}"
                         f"{amount(Decimal(row['loss']) * value)}, {'inside' if row['inside'] else 'OUTSIDE'} the budget")
        if not loss["daily_move_available"]:
            parts.append("average daily move unavailable (fewer than 15 retained closes)")
        lines.append(f"- Loss budget {_percent(loss['budget'], 2)} of the portfolio: " + "; ".join(parts) + ". "
                     "Prices can gap through a level; these are not stops.")
    target = loss.get("target") if loss and final else None
    if target:
        parts = []
        for row in target["rows"]:
            where = (f"at the advisory review level {Decimal(row['level']):.2f} {money}".rstrip() if row["kind"] == "level"
                     else f"at one average daily move ({_percent(row['move'])})")
            parts.append(f"{where} it would lose {_percent(row['loss'], 2)}, "
                         f"{'inside' if row['inside'] else 'OUTSIDE'} the budget")
        parts.append(f"a fall of {_percent(target['budget_fall'])} in the price would use the whole budget"
                     if target["budget_fall"] else
                     f"losing the whole position would use {_percent(target['weight'])}, inside the budget")
        lines.append(f"- At the {target['rating']} target of {_percent(target['weight'])}: " + "; ".join(parts) + ". "
                     "This is this position alone, at this close. Other holdings are not included, and prices can "
                     "gap through a level.")
    test = result.get("downside") if final else None
    if test:
        case = " — ".join(str(part) for part in (test["role"], test["name"]) if part)
        lines.append(f"- In the lowest accepted case ({case}), worth {_percent(test['fall'])} below the close today: "
                     f"the {test['rating']} size of {_percent(test['weight'])} would lose {_percent(test['loss'], 2)} of "
                     f"the portfolio, {'inside' if test['inside'] else 'OUTSIDE'} the {_percent(test['budget'], 2)} "
                     f"budget; that case allows at most {_percent(test['ceiling'])} at this budget. This is this "
                     "position alone; the case is the report's own, not a forecast of the worst outcome.")
    return lines


def sizing_from_state(state, *, final: bool = False) -> dict:
    """The block for a run: before the decision from the earlier thesis' levels, after it from this run's."""
    inputs = state.get("portfolio_inputs") if isinstance(state, dict) or hasattr(state, "get") else None
    if not isinstance(inputs, dict):
        return {"status": "not_configured"}
    quote = state.get("price_observation") or {}
    thesis = state.get("thesis" if final else "prior_thesis") or {}
    levels = [row.get("threshold") for row in thesis.get("conditions") or ()
              if isinstance(row, dict) and row.get("kind") == "price_level"]
    bars = (quote.get("raw_source") or {}).get("bars") if isinstance(quote.get("raw_source"), dict) else None
    session = str(quote.get("session_date") or "")
    closes = [bar.get("close") for bar in bars or () if isinstance(bar, dict)
              and str(bar.get("timestamp", ""))[:10] <= session]
    result = sizing(inputs, state.get("company_of_interest", ""), quote, levels=levels, closes=closes,
                    rating=state.get("final_rating") if final else None)
    card = state.get("decision_context") if final else None
    basis = card.get("scenario_decision") if isinstance(card, dict) else None
    test = downside_test(result, basis.get("sizing_rule") if isinstance(basis, dict) else None)
    return {**result, "downside": test} if test else result


def default_portfolio_path() -> str | None:
    """The user's own portfolio file when it exists; a missing file is not an error."""
    from tradingagents.default_config import DEFAULT_CONFIG

    path = DEFAULT_CONFIG.get("portfolio_path")
    return str(path) if path and Path(path).is_file() else None


def load_portfolio(path: str | Path) -> PortfolioContext:
    """Read a portfolio JSON file, failing before the run rather than mid-graph."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return PortfolioContext.model_validate(data)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"portfolio file {path} is not usable: {exc}") from exc
