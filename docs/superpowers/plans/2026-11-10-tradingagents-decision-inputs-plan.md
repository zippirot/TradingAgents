# TradingAgents: decision inputs plan (Build Q) — portfolio, what changed, feedback

**Status:** decisions made 2026-11-10 (see "Decisions"). Build NOT started and not yet authorised to start: no worktree or goal has been created. The user asked for the plan only.
**Written:** 2026-11-10. **Repo:** `~/Documents/ChatGPT/Tauric/TradingAgents` (GitHub `zippirot/TradingAgents`).
**Base:** `staging` = `origin/staging` = launcher = `3e517089`.
**Scope:** items 4, 5 and 6 from the decision-quality breakdown. Items 1 to 3 (scenario-based decision, checked multiple, funding inside the case) are a separate plan, not written yet.

Independent audit: required

## Goal

Give the Portfolio Manager three inputs it lacks today, so a decision can say how much, why now, and how past calls have done:

1. your actual position and limits, so sizing can be a number when you supply them;
2. what changed since the last decision, so each run decides on the change instead of re-arguing everything;
3. a scorecard of how earlier recommendations turned out.

None of these changes how the rating itself is reached. That is items 1 to 3.

## What exists today (checked in source and in run c463bdac's saved state)

| Area | Today | Gap |
|---|---|---|
| Portfolio | `tradingagents/portfolio.py` accepts a JSON file with positions, average price and cash (`--portfolio` on the command line). The Trader, risk analysts and manager read it. | The launcher never passes a file: the last run's `portfolio_context` is empty. The file has no portfolio value, no standard weight and no loss budget, so "above or below standard weight" cannot be computed. Sizing is always printed as "qualitative only", with or without a file (`output_validation.py:251`). |
| What changed | `assumption_history.assumption_changes` compares the run with the last verified publication and feeds the decision card. | In the last two runs it returned "unavailable (ValidationError)" while comparing against run 86aa515f. Not yet reproduced; the likely cause is that one unreadable saved case in the earlier run fails the whole comparison. When it does work it is display-only: the manager is not asked what the changes mean. |
| Feedback | Outcomes are already scored at 5, 21 and 63 trading sessions and 3 and 6 calendar months against a benchmark (`memory/publication_outcomes.py`). Settlement is attempted at the start of every run. | Every row is still "pending"; the first 5-session result matures about 2026-11-12. The manager receives the raw pending table plus one old memory entry from 2026-10-19 that contains numeric allocations ("30-35% of a normal weight") written before the sizing rule. There is no summary of hit rate or average result. |

## Tasks

### Q1 Portfolio inputs that make sizing a number (item 4)

- **File.** Extend the existing portfolio file with optional fields: `portfolio_value`, `standard_weight` per position (or one `default_standard_weight`), `loss_budget` (the most you accept losing on this position, as a share of the portfolio), and `rating_weights` (what each rating means as a multiple of standard weight, for example Underweight = 0.5). Every field is optional; a file with only positions works as today.
- **Pickup.** The launcher loads `~/.tradingagents/portfolio.json` when it exists (path overridable in settings). No file means exactly today's behaviour.
- **Arithmetic, not judgment.** When the fields are present the system computes, from the dated close: current weight, standard weight, whether the position is above, at or below standard, and, if `rating_weights` is given, the target weight for the final rating and the units between here and there. With `loss_budget`, it computes the loss at each advisory review level and at one average daily range, and says whether that is inside the budget.
- **Where it shows.** A "Position and sizing" block at the top of the decision, labelled as arithmetic on your inputs at a dated close, not an order. The fixed "qualitative only" sentence stays when the inputs are missing and is replaced when they are present. The agents receive the same block, so "trim only if above standard" becomes a stated fact, not a condition.
- **Privacy.** By default the report shows weights as percentages and units, not currency amounts; a setting shows amounts. The immutable publication record stores only a fingerprint of the file.
- Tests: file with and without each field; above, at and below standard; each rating with and without `rating_weights`; loss inside and outside budget; no file leaves every existing output unchanged; a malformed file fails before the run starts, as today.

### Q2 Decide on what changed (item 5)

- **Fix the comparison.** Reproduce the "unavailable (ValidationError)" result against run 86aa515f, then make one unusable part of the earlier record degrade only that part, with a stated reason, instead of the whole comparison.
- **A "Since the last decision" brief.** Built without a model call from saved records: the earlier decision's time and rating; price then and now; whether new filings arrived between; which advisory conditions changed status; which valuation cases were added, removed or repriced; whether the data sources differ (for example a stale price then, current now).
- **The manager must use it.** The Research Manager and Portfolio Manager receive the brief. The manager's answer gains a required field: no material change, strengthens the earlier call, weakens it, or reverses it, with one sentence naming the change that matters. A rating different from the earlier one must be labelled weakens or reverses and name its cause; the same rating with "no material change" is allowed and shown as such.
- **Where it shows.** First block of the decision page, above the thesis.
- Tests: no earlier decision; an earlier decision the same day; new filing between; rating unchanged and changed; the manager's field missing or inconsistent with the two ratings is rejected by the existing structured-output path; replay of runs eea86100 → 86aa515f → c463bdac produces a brief for each pair.

### Q3 A scorecard the manager can read (item 6)

- **Scorecard.** From settled outcomes only: for this ticker and for all tickers, by rating and horizon, the number of calls, how many were right against the benchmark, and the average excess return. Fewer than ten settled calls is labelled "too few to conclude". Pending rows are summarised as a count, not listed.
- **To the manager and the report.** The scorecard replaces the raw pending table in the manager's input and sits above the full table in the report.
- **Clean the old memory.** Old memory entries shown to the manager pass through the existing numeric-sizing filter, so the 2026-10-19 entry no longer feeds allocation percentages back in.
- **Confirm settlement works.** After 2026-11-12, check that the first 5-session result for the 2026-11-05 decision is actually recorded on a normal run; fix it if not. Same-day reruns stay excluded from the count, as today.
- Tests: zero, few and many settled outcomes; mixed ratings and horizons; a right and a wrong Underweight; the memory entry with and without numbers; the manager's input contains the scorecard and not the pending table.

## Proof and acceptance

- Each task's tests fail before the change and pass after.
- Offline replay on saved runs: Q1 with a sample portfolio file against run c463bdac; Q2 across the three most recent runs; Q3 with the real outcome store plus a synthetic settled set.
- Full `pytest -q` and `ruff check .` pass on the final commit.
- Independent audit through the registered executor, then closure of confirmed findings.
- Not proven without a paid run: how the manager words its change assessment and uses the sizing block and scorecard. Your next normal run shows that.

## Estimate

- Build size: medium (three independent tasks, three commits, one audit).
- Recommended model: Claude Fable 5.2, `claude-fable-5-2`, medium effort. Each task has a clear contract and offline proof; none involves cross-system reasoning.
- Wall-clock: 5 to 9 active hours including the audit and closure. Q1 about 2 to 3, Q2 about 2 to 4, Q3 about 1 to 2. The last three builds finished in roughly half their estimates.
- Paid calls: none in the build. Audit about $1.
- Run cost after the build: no extra model calls; slightly more input text to the managers.

## Boundaries

No merge, push, install, production promotion or paid run without separate approval. Build in an isolated worktree from `3e517089`. The portfolio file is read locally and never sent anywhere except inside the prompts of your own runs.

## Not in this plan

- Items 1 to 3: the rating is still reached the same way.
- Skipping the debate when nothing changed. It would cut cost, but it changes what a run is; decide after seeing Q2's briefs for a week.
- Orders, broker connection, or any execution.
- Probability-weighted expected returns.
- Counting same-day reruns as separate track-record samples.

## Decisions (made by the user 2026-11-10, following the recommendations)

1. Scope: all three tasks, Q1, Q2 and Q3.
2. Q1 rating meanings in the sample file, as a multiple of standard weight: Buy 1.5, Overweight 1.25, Hold 1.0, Underweight 0.5, Sell 0. They live in the user's portfolio file, not in the code.
3. Q1 display: percentages and units only. Currency amounts stay off unless a setting turns them on.
4. Q2 comparison: against the last decision of any earlier run, including one from the same day.
5. Build order: Q2, then Q3, then Q1. One commit per task, one independent audit at the end.

## Still needed before any build

An explicit instruction to start. Merge, push, install and any paid run each need their own approval afterwards.
