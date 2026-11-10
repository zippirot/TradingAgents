# TradingAgents: a decision made from priced scenarios (Build Q)

**Status:** approved 2026-11-10 with all five recommendations: conditional range may inform and check the rating; mismatch requires a printed explanation; numeric subjective weights; 10 percent threshold; up to $10 for Portfolio Manager step re-runs. Build in `~/Worktrees/decision-basis-q`.
**Written:** 2026-11-10. **Repo:** `~/Documents/ChatGPT/Tauric/TradingAgents` (GitHub `zippirot/TradingAgents`).
**Base:** `staging` = `origin/staging` = launcher = `3e517089`.
**Evidence:** five saved DOCN runs of 2026-11-09 in `~/.tradingagents/logs/DOCN/TradingAgentsStrategy_logs/`.

Independent audit: required

## Goal

The Portfolio Manager's rating should rest on priced scenarios it has accepted, or on a named reason it has not. Today the rating is the same whether valuation cases exist or not.

## Why decision quality is capped (verified)

| Run | Cases priced | Case adopted by the Portfolio Manager | Rating |
|---|---|---|---|
| 08:43 `520623df` | 1 | no | Underweight |
| 11:57 `2a2e47dd` | 0 | no | Underweight |
| 14:26 `eea86100` | 2 (74.45 and 52.75 against a 78.31 close) | no | Underweight |
| 18:51 `86aa515f` | 0 | no | Underweight |
| 19:57 `c463bdac` | 0 | no | Underweight |

In `eea86100` the manager's `no_case_reason` was: cases "rely on uncalibrated borrowings-only multiples and unassessed funding ... A point price target would imply unsupported precision." Each part of that reason has a cause in the code:

| Objection | Cause in the code |
|---|---|
| "Unassessed funding" | `valuation_cases.price_case` attaches the warning "Funding feasibility unassessed. No cash plug or discounting." to every revenue case, whatever the case says. A funding model exists (`agents/funding.py`, `ForwardCapital`, `funding_gap`) but the revenue-case method the analysts use does not call it. |
| "Uncalibrated multiple" | `RevenueCase.multiple` is any positive number with a free-text rationale. Nothing compares it with the references the run already computes (`valuation_reference.calculate_own_history`, peer statistics). Those references are equity value over trailing revenue, while cases use forward enterprise-value bases, so they cannot be compared as shown. |
| "Would imply unsupported precision" | The only way to use a case is to adopt it as the price target (`CaseSelection`). The prompt then says "If no case is adopted, omit valuation_request and state why." There is no way to use cases as a labelled range, and declining costs nothing. |

Build R (installed) makes cases arrive reliably. This build makes them usable and used.

## Design in one paragraph

Keep the existing rule that nothing is published as a price target unless it passes the strict adoption path. Add a second, clearly labelled output: a **conditional scenario range**. The analyst submits a base and a downside case, optionally an upside. Each case carries a funding check computed from the filing's own schedules, and its multiple is positioned against the company's own history on one comparable basis. The Portfolio Manager must then accept or reject each priced case with a reason tied to a named input, and give each accepted case a subjective weight. Code computes the range and the weighted value against the current price and checks that the rating points the same way. A mismatch is not blocked: it must be explained, and the explanation is printed on the decision card.

Main alternative rejected: forcing the manager to adopt a single price target. It would trade honest uncertainty for false precision and contradict the standing rule on unsupported numbers.

## Tasks

### Q1 Funding is assessed inside each case
Files: `agents/valuation_cases.py`, `agents/retained_kpi_context.py`, `agents/analysts/fundamentals_analyst.py` (`SHARED_VALUATION_INPUTS`), `agents/shared_valuation.py` (render).
- `CashChange.source` gains `finance_payments` and `capex`; `operations` then means operating cash flow only. Existing sources stay valid.
- New `funding_check(capital, state)` in `valuation_cases.py`, called by `price_case`:
  - scheduled finance-lease and equipment payments from the analysis date to the case's valuation date, read from the filing table the run already parses (`render_lease_maturities`; expose its parsed rows as `lease_maturities(state)`), pro-rated by whole calendar years;
  - principal of any retained convertible note (`filing_terms_evidence.notes`) that matures on or before the valuation date;
  - the case's own cash changes by source.
- Result attached to the case as `funding`: `assessed` when the case states `finance_payments` at least equal to the scheduled amount and accounts for each maturing note (a `debt` cash change, a conversion share change, or the principal still in borrowings); otherwise `partial` with the exact shortfall sentence, for example "Scheduled finance and equipment payments of 320.4M through 2027-12-31 are not reflected in the case's cash." Closing cash below zero is already refused by the schema.
- The blanket warning "Funding feasibility unassessed" is replaced by the actual status. A case with no split stays `unassessed` and says which inputs are missing.
- Not modelled, and said so on every case: rent on leases that have not commenced, because the filing gives one undiscounted total with no schedule.
Tests: a case that states the scheduled payments and repays the maturing note is `assessed`; one that omits the payments is `partial` naming the amount; a case over a period with no schedule data is `unassessed` with the reason; the two saved `eea86100` cases price as before and report `partial` with DOCN's 2027 schedule (250.0M) and the 312.3M note treated as repaid; existing bridge rules (share and cash changes must sum, no double counting) are unchanged.

### Q2 Each case multiple is positioned against a comparable reference
Files: new `agents/case_reference.py`, `agents/shared_valuation.py`, `agents/valuation_reference.py` (read only).
- For every priced case compute its **implied equity value over forecast revenue** (per-share value times closing shares, over the forecast revenue). That is the same basis as the own-history series, whatever obligation basis the analyst chose.
- Position it against the retained own-history record: below the low, low to median, median to high, above the high; and against today's trailing multiple. State the count of quarters and the label the series already carries (retrospective, not point-in-time).
- For each history quarter also show revenue growth year over year and gross margin where the retained facts allow it, so "median 4.47 times" comes with the growth and margin it was earned at. Unavailable where the facts are missing; never estimated.
- Peers are shown beside it as individual points when fewer than three pass, as today.
- Output per case: `reference_position` record plus one sentence on the scenario table, for example "Implied 4.9 times equity value to 2027 revenue: between the eight-quarter median (4.47) and high (16.31); history median was earned at X% growth and Y% gross margin."
- No model, regression or adjustment is introduced. This task makes the comparison like-for-like and visible; it does not claim what the multiple should be.
Tests: positions for values in each band; a case on a lease-inclusive basis and one on an equity basis with the same per-share value get the same position; unavailable history yields `unavailable` with the reason and no position; growth and margin appear only for quarters with facts; replay of the `eea86100` cases gives their positions.

### Q3 The Portfolio Manager decides from the priced cases
Files: `agents/schemas.py` (`PortfolioDecision`), `agents/managers/portfolio_manager.py`, new `agents/scenario_decision.py`, `agents/decision_context.py` (card), `agents/output_validation.py`, `operational_audit.py`, `agents/analysts/fundamentals_analyst.py`.
- Analyst instruction: submit a base and a downside case, optionally an upside, each with `scenario_role` (`downside`, `base`, `upside`). An empty list stays valid when no case can be supported, with the reason in the narrative. Maximum stays three.
- `PortfolioDecision` gains `scenario_view`: one entry per priced case with `case_id`, `version`, `disposition` (`accepted` or `rejected`), `weight` (0 to 1, required when accepted), `rejected_input` (one of `revenue_forecast`, `multiple`, `shares`, `cash`, `obligations`, `funding`, required when rejected) and `reason`. Accepted weights must sum to 1. `no_case_reason` is no longer sufficient when priced cases exist.
- Prompt: the manager receives each case's price, funding status (Q1) and reference position (Q2), and is told that "uncalibrated" or "unassessed" is not a reason unless the printed status says so.
- `scenario_decision.summarize(state)` computes in code, from replayed cases only: the range of accepted cases, the weighted value, each as a percentage against the completed close, and a direction (`below`, `near`, `above`) using the threshold in decision 4.
- Consistency: Sell or Underweight with direction `above`, or Buy or Overweight with direction `below`, requires a non-empty `rating_basis_reason`. Nothing is overridden or blocked.
- Missing or invalid `scenario_view` when priced cases exist: one structured retry through the existing path; if still missing, the card states "Decision basis: opinion only; the Portfolio Manager did not address the priced cases" and the operational score records it (new reason, score 3).
- Decision card gains a block, above the conditions list: "Conditional scenario range (not a price target)": each case with role, price, funding status, reference position, disposition and weight; the range and weighted value against the close; the direction; the consistency line. "Fundamental price target" stays unavailable unless the existing adoption path succeeds. All text keeps the labels "conditional", "subjective weights, uncalibrated".
- The summary is saved in the publication record so outcome tracking can later compare weighted values with what happened.
Tests: accepted and rejected dispositions validate; weights not summing to 1 are refused; a rejection without a named input is refused; range, weighted value and direction are computed from replayed cases and never from stored prices; each consistency combination; the card renders the block with every label; no priced cases renders "No priced scenario; rating is a research opinion" and makes no extra call; REVIEW-route runs are unchanged; the strict price-target path is unchanged.

## Proof and acceptance

- Each task's tests fail before the change and pass after.
- Offline replay of `eea86100` (two priced cases): Q1 funding status and Q2 positions on both cases; Q3 summary computed from a stub manager answer; card rendered.
- Paid proof, needs approval (decision 5): re-run only the Portfolio Manager step on saved `eea86100` with the step tool, twice. Acceptance: both runs return a valid `scenario_view` covering both cases, and the card shows range, weighted value, direction and consistency line. Whether the rating changes is reported, not required.
- Full `pytest -q` and `ruff check .` on the final commit.
- Independent audit through the registered executor, then closure of confirmed findings.
- Not proven by this build: that decisions become more accurate. That needs the outcome record, whose first six-month result matures in May 2027.

## Estimate

- Build size: extra medium.
- Recommended model: Claude Fable 5.2, `claude-fable-5-2`, medium effort. Three coupled changes across the case model, the manager's contract and the decision card, each with clear tests and saved inputs to replay. Raise effort to high for Q3 only if the manager's contract and the publication record prove harder to reconcile than the read suggests.
- Wall-clock: 5 to 9 active hours including the audit and closure. The last two small builds ran at about one third of their estimates; this one touches more shared code.
- Paid calls: the step re-runs in decision 5; audit about $1.
- Ongoing run cost: a larger analyst submission and a larger manager answer; roughly 1 to 3 percent more tokens per run. Engineering judgment, not measured.

## Boundaries

No merge, push, install, production promotion or paid call without separate approval. Build in an isolated worktree from `3e517089`. Suggested order Q1, Q2, Q3; Q1 and Q2 can be integrated and installed before Q3 if you want the case table improved first.

## Risks

- The manager may give arbitrary weights. They are labelled subjective and saved for later scoring; they are not presented as probabilities of outcome.
- More required structure means more ways to fail validation. Build R's correction attempt covers the analyst; Q3 uses the manager's existing structured retry.
- Prorating scheduled payments by calendar year is approximate; the note on the case says so.
- Own history has eight quarters spanning two very different periods. Q2 shows that instead of hiding it.

## Not in this plan

- A model of what the multiple should be, more peers, or point-in-time history.
- Rent schedules for leases that have not commenced.
- Portfolio inputs and numeric position sizing, "what changed since last run", and faster outcome scoring (items 4 to 6 of the earlier list).
- Display items carried from earlier reviews; the large-filer plan (on hold).

## Decisions for the user

1. **Product rule.** May a labelled conditional scenario range inform and check the rating, while "price target" stays reserved for the strict path? Recommended: yes.
2. **Strictness.** When the rating points against the accepted scenarios: require a printed explanation (recommended), or refuse the decision until they agree?
3. **Weights.** Numeric subjective weights that give a weighted value (recommended), or qualitative likelihoods only, which give a range and no weighted value?
4. **Threshold.** How far from the close counts as "above" or "below"? Recommended: 10 percent.
5. **Paid proof.** Approve up to $10 for Portfolio Manager step re-runs on the saved run?
