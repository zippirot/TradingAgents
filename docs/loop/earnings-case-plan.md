# Earnings-based valuation case: plan

**Status:** approved in principle by the user 2026-11-11 ("yes" to building an earnings-based valuation for mature companies). Not started.

**Goal:** A mature, profitable company can be valued on its earnings, and that value can carry weight in the decision, instead of every company being valued on a multiple of revenue.

**Why:** Both evaluators marked WMT and CAT down for it ("valuation method does not fit the asset; earnings never valued"). After cycle 1 WMT's D1 (valuation and expected return) sits at 5.2 against 6 to 7 for the others.

## Estimates

| Item | Estimate |
|---|---|
| Build size | medium |
| Recommended model | Claude Fable 5.2 (`claude-fable-5-2`) |
| Reasoning effort | medium |
| Wall-clock | 4 to 7 hours including paid checks |
| Paid runs | about 10 to 15 dollars (one run, then three each on WMT and CAT, plus DOCN and MSFT to show no change) |

Reason for the model: the change crosses the valuation core, the decision arithmetic and a prompt; a plausible but wrong reading could pass local tests. This is an engineering judgment.

## What exists already (found 2026-11-11)

- `tradingagents/agents/valuation.py`: `PETarget` (`method: "pe"`, `eps_fact_id`, `eps_basis`, `multiple`, optional `forecast`), priced by `_pe`, classified by `_decision_use` as a historical diagnostic.
- `tradingagents/agents/shared_valuation.py:452`: every row that is not a `RevenueCase` is stored with `diagnostic_only: True`.
- `tradingagents/agents/scenario_decision.py:71` `priced_cases`: only `method == "revenue_case"` and `status == "supported"` can be weighed by the Portfolio Manager.
- `tradingagents/agents/analysts/fundamentals_analyst.py:167`: the analyst is shown only the revenue case shape.
- Places that branch on `revenue_case`: `assumption_history.py`, `case_reference.py` (own-history placement), `decision_context.py:213`, `prior_cases.py`, `scenario_return.py` (return arithmetic uses revenue), `shared_valuation.py` (several).

## Design choice

Add an `earnings_case` beside `revenue_case`, priced as forecast earnings per share times a stated multiple, with the same case fields the manager already weighs (name, role, forecast, multiple, dated assumption, rationale). Rejected alternative: promote the existing `pe` diagnostic. It prices from one historical EPS fact with no forecast period or scenario role, so it would need the same new fields anyway, and saved runs holding `pe` diagnostics must keep replaying as they are.

- Value per share = forecast diluted EPS for a stated future period times the multiple. No net-debt bridge (earnings are after interest), so no cash or obligation inputs; share count enters only through EPS, which the analyst forecasts and code checks against the filed diluted share count (forecast net income divided by filed diluted shares must be within a stated band of the forecast EPS, or the case says shares are assumed to change and by how much).
- Guard rails in code: the company must have positive filed trailing diluted EPS (else the case is refused: use a revenue case); the forecast period must end after the analysis date; the multiple must be dated; the result states the trailing P/E at the current close beside the case multiple.
- Which method: the analyst may submit either kind; all cases in one submission must be one kind (a weighted value across methods is not defined). The prompt says when each fits: earnings case when trailing earnings are positive and stable; revenue case when earnings are negative or not meaningful.

## Tasks (each: failing test first; then free checks; then one paid run before three)

1. `EarningsCase` model and `price_earnings_case` in `valuation_cases.py`; result `method: "earnings_case"`. Tests: arithmetic; refusal on non-positive trailing EPS, past period, missing multiple date; EPS and share-count consistency note.
2. `shared_valuation._prepare`: accept and store earnings cases as weighable (`diagnostic_only: False`); refuse a submission that mixes kinds, with the reason. Replay of all saved runs must show zero differences.
3. `scenario_decision.priced_cases`, `scenario_return`, `decision_context`, `prior_cases`, `case_reference`: carry an earnings case through weighting, return against the required return, the decision card and prior-case comparison; own-history placement says "not available for an earnings case" until a P/E history exists.
4. Prompt (`fundamentals_analyst.py`): the earnings case shape and the rule for choosing. This is the only type 3 change.
5. Paid check: one WMT run; if it submits earnings cases and they price, three WMT and three CAT runs; DOCN and MSFT three each to show no loss. Keep rule: WMT or CAT Decision mean up by more than 0.5, or D1 up by more than 1.0, with DOCN and MSFT inside noise and reached-a-decision not lower.

## Out of scope

A P/E history series, discounted cash flow, sector-specific methods (banks, insurers, REITs), dividends in expected return.
