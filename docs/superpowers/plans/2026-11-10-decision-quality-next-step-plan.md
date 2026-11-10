# TradingAgents: next step up in decision quality (parts A, B and D)

Date: 2026-11-10. Status: for your review. Nothing is built.
Repo: `~/Documents/ChatGPT/Tauric/TradingAgents`. Base: `staging` at `b7c26758` (installed on the launcher).
Evidence used: DOCN run `7822a890` (11:00 AM, saved state and report), the code at `b7c26758`, and
ChatGPT's seven-part scores for that run.
Follows: `2026-11-10-tradingagents-decision-quality-gap-plan.md` (Builds 3, 1, 2, all installed).

## Where things stand

| Component (weight) | Before today's builds | Run 7822a890 |
|---|---|---|
| Valuation and expected returns (25%) | 5.5 | 6.5 |
| Portfolio construction (15%) | 5.0 | 6.5 |
| Other five components | 7.5 to 9.0 | 8.0 to 9.3 |
| Weighted total | about 7.2 | 7.8 |
| ChatGPT overall | 7.6 | 8.1 |

Valuation is below the 7 set as the earlier stop rule and below my estimate of about 8. The user has
reviewed the result and chosen to continue. This plan keeps the work narrow and sets a new stop rule.

Part C (the portfolio file) is not in this plan; it is on hold at the user's choice.

## Part A: make what is built count (small)

Faults found in run `7822a890`. Each was confirmed in the saved record or the code.

| # | Fault | Cause | Fix |
|---|---|---|---|
| A1 | The same-basis history (4.84x low, 7.84x median) was cited by two agents, flagged "unsupported" by the in-run auditor, and set aside by the manager. Two of six audit findings. | The auditor is given each case's inputs only (`audit_pass.py`, case items carry `request` and nothing computed). It never sees the same-basis history. | Give the auditor, per case, the computed reference line and funding line, marked as computed by code from retained filings. Give the same-basis history a citable label in the evidence references so a correct citation is recognised. |
| A2 | Managers called the reference "trailing, not comparable to a forward multiple". | Every case is labelled "forward from the analysis date" (`multiple_period`), while the arithmetic applies the multiple to the case year's revenue with shares and net debt at the period end. | Describe the construction as it is computed, in one consistent sentence, wherever the case is printed or shown to an agent. Confirm at build time whether the field changes any arithmetic; if it is only a label, stop asking the analyst for it. |
| A3 | Funding read "partial" on all three cases. | The analyst entered 320.428M against a schedule of 320.453M, a 25,000 difference on 320 million. The comparison is exact (`valuation_cases.py:262`). | Treat a difference of 0.1% or less as matching. Both figures are still printed. |
| A4 | The Trader's "Sell" for an Underweight research rating was criticised by all three risk analysts, the manager and ChatGPT. | The Trader's action has three values (Buy, Hold, Sell), so Underweight can only map to Sell. | Display-level relabel: when the research rating is Underweight and the action is Sell, show "Reduce" with the research rating beside it, in the report and in what the risk analysts are shown. Likewise "Add" for Overweight and Buy. The stored action value is unchanged. |
| A5 | The report prints "Position sizing: qualitative only" beside the new sizing rule. | Two fixed sentences in `output_validation.py` predate the rule. | When a sizing rule is stated, the sentences point to it and say no allocation is given without holdings. |
| A6 | The base case used 1.930B, slightly under the 1.9328B that guidance implies. Caught by the manager and ChatGPT, not by code. | No check compares a case's forecast with the guidance arithmetic the run already holds. | Code states, per case, the forecast against the guidance-floor arithmetic (above, at, or below by how much). A note, not a rejection. |

Proof: replay run `7822a890` offline. Expected: funding "assessed" on all three; the auditor's input
contains the reference lines; the Trader line reads "Reduce"; the base case carries the floor note. A1
cannot be fully proven offline, because it depends on how the auditor model responds to the added input.

## Part B: a six-month view built from dated events (medium)

### The problem
The decision horizon is six months. The case values are for the end of 2027. Bringing them back to
today (Build 1) fixed the time basis but did not say what could change within six months. ChatGPT rates
this the most important remaining gap.

### The approach
The report already names the events that decide the view: the December 1 note repayment and the
fourth-quarter results. Today they are review triggers only. Part B asks the manager to commit, in
advance, to how each one would change its view, and has code do the arithmetic.

1. **The manager names up to three events** that should resolve within the horizon, by the identifier of
   an existing advisory condition, with the date it expects each to resolve. Code checks the condition
   exists and the date is inside the horizon.
2. **For each event, two sets of case weights:** the weights the manager would hold if the outcome is
   favourable and if it is adverse, as that condition already defines them. Each set sums to 1.
3. **Code computes, per outcome:** the weighted value at the horizon date (each case brought back from its
   period end to the horizon date at the required return) and the move from today's close to that value.
   Printed as an implied move if the price went to that value, not as a forecast.
4. **Code derives the odds the manager's own numbers imply.** The current weights sit between the two
   outcome sets. From where they sit, code states "your current weights imply about X% for the favourable
   outcome". No probability is asked for. An implied figure outside 0 to 100% means the three sets
   disagree with each other, and the manager is asked once to correct them.
5. **Follow-through in later runs.** When a later run observes the event, the "since the last decision"
   block shows which outcome occurred, the weights the earlier run said it would then hold, and the
   weights it holds now.

What the reader gets, in one table: each event, its date, the implied six-month move under each
outcome, and the implied odds. That is a six-month distribution tied to real dated events.

### What it deliberately does not do
- It does not forecast a price path or a benchmark return.
- It does not ask for probabilities; it derives them from weights the manager already gives.
- It does not add a new model call. It adds one structured field to the manager's existing answer.
- It does not gate the rating.

### Design choice to confirm
**Required or optional.** Optional fields are usually skipped. Recommended: required when at least one
advisory condition is expected inside the horizon, with one retry and the same operational treatment as
the existing scenario answer (score 3 if still unusable). Alternative: optional, with no score effect.

### Proof and its limit
Unit tests and a replay of `7822a890` with a constructed manager answer prove the arithmetic and the
checks. No saved run contains a real answer to this new question, so the manager's behaviour can only be
shown by a live call. Options: wait for your next full run, or approve one paid call that re-runs only
the Portfolio Manager step on the saved run using the existing step tool.

## Part D: evidence that the decisions are good (time and runs, plus a small build)

Decision quality as scored so far measures how well a decision is constructed. Whether the decisions are
right is a separate question that only outcomes answer. Today there are five DOCN observations, all
Underweight, with overlapping windows, and none settled.

1. **D1 Confirm settlement works (free, no build).** The first five-session window, on the November 5
   decision, completes on November 12. On or after that date, run the existing settlement pass and
   confirm the result is recorded and appears in the scorecard. Fix it if not.
2. **D2 Score decisions against what they said (small build).** Outcomes are scored today on direction
   against a benchmark only. Add, from fields each publication already stores: whether the close at 21
   and 63 sessions fell inside the accepted value range, on which side of the weighted value, and, once
   Part B exists, which event outcome occurred against the implied odds. Reported in the scorecard with
   the existing "too few to conclude" label under ten independent observations.
3. **D3 Find companies the system can analyse (free, small build).** Very large filers are known to stop
   before the debate (a separate plan, on hold). Add a no-model command that runs only source collection
   and the evidence checks for a list of tickers and reports which pass. Run it on a list of about
   fifteen mid-sized US filers.
4. **D4 Forward runs on other companies (your spend, no build).** One run each on four to six companies
   that pass D3. This shows at once whether the system can reach a rating other than Underweight, and
   each run starts an independent outcome clock. A full run is about 2.2 million input tokens and thirty
   model calls; dollar cost per run is not recorded by the system, so budget it in runs.
5. **What I would not do first:** a historical backtest. The code already warns that the models may know
   what happened after a past date, so past-dated runs cannot show clean skill.

Earlier you chose to get DOCN right before other companies. D1 to D3 respect that. D4 is the step that
changes it, and it is yours to time.

## Order, measurement and stop rule

1. Part A, then one DOCN run you start. Judge on valuation and on agent handoffs.
2. Part B, then one DOCN run. Judge on valuation.
3. Part D1 on November 12; D2 and D3 alongside B; D4 when you choose.

**Stop rule.** If valuation is below 7.5 after Parts A and B, stop building on valuation. What remains
would be an integrated financial model, which is large, moves a case by about 2 to 3 dollars a share by
my sizing, and depends on a lease schedule the company has not published.

Each part gets the independent audit, as before.

## Decisions for you

1. **A3 tolerance:** treat a funding difference of 0.1% or less as matching? Recommended: yes.
2. **A4 Trader label:** show "Reduce" and "Add" for Underweight and Overweight, with the stored action
   unchanged? Recommended: yes.
3. **B approach:** the event-based six-month view as described? Recommended: yes.
4. **B required or optional:** required with one retry and a score effect (recommended), or optional?
5. **B live proof:** one paid Portfolio Manager call on the saved run, or wait for your next full run?
6. **D4:** how many other companies, and when? Recommended: four to six, after Part A.

## Decisions recorded 2026-11-10

The user adopted every recommendation above ("We'll follow your recommendations"): A3 tolerance 0.1%;
A4 display-level "Reduce"/"Add" with the stored action unchanged; Part B required with one retry; no
paid call without explicit approval. Part A is built first.

## Estimates

Part A, the part built and audited first:

- Build size: small.

| Part | Size | Build and verification | Recommended model |
|---|---|---|---|
| A. Make what is built count | small | 2 to 4 hours | Claude Sonnet 5.5 (`claude-sonnet-5-5`), medium |
| B. Six-month event view | medium | 5 to 8 hours | Claude Opus 5.5 (`claude-opus-5-5`), medium |
| D2 and D3 | small | 2 to 4 hours | Claude Sonnet 5.5 (`claude-sonnet-5-5`), medium |

Part B gets the stronger model because it changes what the manager is asked and adds consistency checks
across three sets of weights, where a plausible but wrong rule could pass local tests. A and D are
narrow changes with clear checks. These are engineering judgments, not measured comparisons; continuing
in this session's model is acceptable for all three. Hours exclude your runs and decisions. Codex
credits: not applicable.

Expected effect, as judgment only, noting my last estimate was too high: Part A lifts valuation to about
7 and handoffs slightly; Part B lifts valuation to between 7.5 and 8. With portfolio construction left
at 6.5, that gives a weighted total of about 8.1 to 8.2. Part D does not move the construction score; it
is the only route to knowing whether the decisions are right.
