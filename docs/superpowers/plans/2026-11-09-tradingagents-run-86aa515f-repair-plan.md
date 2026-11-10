# TradingAgents: repair plan after DOCN run 86aa515f (Build Z)

**Status:** approved 2026-11-09 (Z1 fill as estimate; Z3 scores 3, 3, 4). Build in `~/Worktrees/report-repair-z`.
**Written:** 2026-11-09. **Repo:** `~/Documents/ChatGPT/Tauric/TradingAgents` (GitHub `zippirot/TradingAgents`).
**Base:** `origin/staging` = launcher = `f4776526`. The local `staging` branch is behind at `b47fb367`; build from `origin/staging`.
**Evidence:** saved state `~/.tradingagents/logs/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-09_86aa515f.json`, attempt folder `~/.tradingagents/logs/DOCN/2026-11-09/183149-61c0b886/`.

Independent audit: required

## Goal

The 6:51 PM run lost two things the 2:26 PM run had: priced valuation cases and a current price. It still scored 5/5 for operations, and its risk debate spent effort on a false "dropped conditions" finding. This plan restores the first, makes the second impossible to miss, makes the score reflect both, and removes the false finding.

## What broke, with confirmed cause

| # | Symptom in the report | Cause (checked against saved state and source) |
|---|---|---|
| 1 | "Row 1 omitted / Row 2 omitted: malformed valuation request at capital.obligations.borrowings.assumption". No scenario values. | The fundamentals analyst omitted the required `assumption` label on the borrowings figure in both cases. `CapitalValue.assumption` is required (`valuation_cases.py:29`), so each whole case failed validation (`shared_valuation.py:224-226`). The 2:26 PM run included the label. **Ran:** replaying the two saved requests with only that label filled in as `estimated` returns status `available` with both cases priced. |
| 2 | Every section analyses the Friday 11-06 close of $72.48 on a run made after Monday's close. | Yahoo returned an 11-09 row with no closing price for DOCN, SPY, AKAM and NET. **Ran 2026-11-09 evening:** Yahoo still returns no 11-09 close for DOCN or SPY, although the 2:26 PM run read $78.31 from it. The fallback to the last valid session (`dataflows/vendors/yahoo/ohlcv.py:400-416`) worked as designed and is disclosed, but only in one "Price fallback" line inside the decision section and the analyst context. |
| 3 | Operational quality 5/5 "no material operational problem". | `operational_audit.REASONS` has no entry for rejected valuation cases or a price-session fallback, so neither is recorded. |
| 4 | All three risk analysts list the Research Manager's conditions as "dropped" by the Trader. | Since Build Y the conditions are printed under "Carried from the Research Manager's plan (not restated by the Trader)". The risk prompts (`risk_mgmt/*_debator.py:36`) say "Flag any Trader step that drops or contradicts a research condition" and do not mention the carried block. |
| 5 | The Trader's own wording says "staged trim toward an underweight" without "only if exposure exceeds that posture". | The Trader prompt does not ask it to keep the plan's exposure condition in its own proposal. The condition is still present in the carried block. |

Not a defect: the `%s` placeholders in `run.log` are the log's deliberate argument redaction ("[arg types: ...]"). I earlier called this a slip; it is not, and it is not in this plan.

## Tasks

### Z1 A missing label no longer discards a valuation case
In `prepare_shared_valuation`, before a revenue case is validated, any capital value (`closing_shares`, `cash`, each entry in `obligations`) that has no `assumption` key gets `"estimated"`. Each fill adds a visible reason on the scenario table: `Row N: assumption label missing on <field>; treated as estimated.` A label that is present but invalid is still rejected, as are all other malformed fields. The saved original request stays unchanged in `unvalidated_outputs`.
Tests: the two saved 86aa515f requests price; the note names the field; an invalid label value is still rejected; a request with all labels present is unchanged and carries no note.
Alternative rejected: one retry call to the model. It costs a paid call on every miss and can fail again.

### Z2 A fallback price is stated where the reader starts
When the price record carries a fallback, one line appears at the top of the Final Portfolio Decision, in the executive summary's inputs, and at the head of the Market Analyst section: `Stale price: latest completed session <date> has no close from the data source; all price and indicator figures use <selected date>.` The existing "Price fallback" lines stay. No second data source and no blocked run; both are separate decisions.
Tests: a state with a fallback record renders the line in all three places; a state without one renders none.

### Z3 The operational score reflects lost capability
Two new entries in `operational_audit.REASONS`, recorded where the events happen:
- `valuation_cases_rejected` scored 3: every submitted valuation case was rejected. (Some but not all rejected: `valuation_case_rejected` scored 4.)
- `price_session_fallback` scored 3: the price used is from an earlier session than the latest completed one.
Run 86aa515f would have scored 3/5. Scores for these events are a product choice; the values above are my recommendation.
Tests: each observation lowers the assessment to the stated score with its text; a clean run stays 5/5; unknown codes are still refused.

### Z4 Risk analysts treat carried conditions as kept
One sentence added after the existing instruction in the three risk prompts: conditions printed under the "Carried from the Research Manager's plan" heading are part of the Trader's plan and count as kept; flag only a Trader statement that contradicts or weakens one.
Test: each prompt contains the sentence.

### Z5 The Trader keeps the plan's exposure condition
One clause in the Trader prompt: when the plan makes an action conditional on current exposure, the Reasoning or Position Sizing must state that condition.
Test: the prompt contains the clause. Live effect shows only on a paid run.

## Proof and acceptance

- Each task's tests fail before the change and pass after.
- Offline replay of 86aa515f on the built code: both valuation cases priced with the label note; the stale-price line present in the three places; operational assessment 3/5 naming both events.
- Full `pytest -q` and `ruff check .` pass on the final commit.
- Independent audit through the registered executor, then closure of confirmed findings.
- Not proven by this build: Z4 and Z5 change model instructions, so their effect appears only on the next paid run.

## Estimate

- Build size: small.
- Recommended model: Claude Fable 5.2, `claude-fable-5-2`, medium effort. The changes are narrow with clear tests and an offline replay; nothing here needs more.
- Wall-clock: 2 to 4 active hours including the audit and closure.
- Paid calls: none. Audit cost under $1 at the last two runs' rate.

## Boundaries

No merge, push, install, production promotion or paid DOCN run without separate approval. Build in an isolated worktree from `f4776526`.

## Not in this plan

- A second price source for when Yahoo lacks a close. New dependency; your decision.
- Blocking a run on a stale price.
- A structured research-to-trader contract object, typed multiple labels in analyst prose, and a post-PM audit (declined earlier).
- Repeat-run stability test of the fundamentals step on frozen evidence (paid; step tool exists).
- Display items carried from the earlier review.
- Large-filer plan (on hold).

## Decisions for the user

1. Approve Build Z as written?
2. Z3 scores: decided 2026-11-09, 3 for all cases rejected, 3 for a price fallback, 4 for some cases rejected.
3. Z1: fill the missing label as an estimate (recommended) or retry the model once?
