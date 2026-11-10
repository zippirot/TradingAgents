# TradingAgents: valuation submission check-and-retry (Build R)

**Status:** approved 2026-11-10 (one real correction call approved, under $0.50; a successful correction scores 5). Build in `~/Worktrees/valuation-repair-r`.
**Written:** 2026-11-10. **Repo:** `~/Documents/ChatGPT/Tauric/TradingAgents` (GitHub `zippirot/TradingAgents`).
**Base:** `staging` = `origin/staging` = launcher = `242582db`.
**Evidence:** saved states for runs `2a2e47dd`, `86aa515f`, `c463bdac` in `~/.tradingagents/logs/DOCN/TradingAgentsStrategy_logs/`.

Independent audit: required

## Goal

A valuation case the fundamentals analyst wrote should reach the report priced, or the report should say exactly why not and score itself accordingly. Today a single formatting slip silently removes every scenario value, and the cause changes from run to run.

## The problem, with evidence

| Run (2026-11-09) | What the analyst submitted | Why it was lost |
|---|---|---|
| 11:57 `2a2e47dd` | Two cases | A required field on a share change was missing; both rejected |
| 18:51 `86aa515f` | Two cases | The `assumption` label was missing on borrowings; both rejected (fixed by Build Z) |
| 19:57 `c463bdac` | One case, every label present | One closing brace in the wrong place put `capital` beside `request` instead of inside it, so the block is not valid JSON. **Ran:** with the brace moved, the case prices at 74.16 USD/share. The report showed only "missing, malformed, duplicated or oversized" and scored 5/5 |

Cause common to all three: the analyst writes the block as free text inside its report (`fundamentals_analyst.py`, `SHARED_VALUATION_INPUTS`), it is first checked later in the Evidence Check step (`graph/setup.py` `evidence_with_scenarios` → `prepare_shared_valuation`), and by then nothing can ask the analyst to correct it. Build Z's count of rejected cases cannot count a block it cannot read (`shared_valuation._parse`).

## Tasks

### R1 Precise, typed rejection reasons
`prepare_shared_valuation` reports what was wrong in words the analyst model and the reader can act on:
- unreadable block: `Valuation block is not valid JSON: <parser message> near "<up to 60 characters around the position>"`;
- wrong shape: name the offending keys, for example `Row 1: unexpected field capital beside name and request; capital belongs inside request`;
- no block, more than one block, oversized, duplicate names: each its own sentence instead of the shared "missing, malformed, duplicated or oversized".
The record gains `submission_error` (one of `unreadable`, `missing_block`, `duplicate_block`, `oversized`, `duplicate_names`) when the submission failed as a whole. No change to which submissions are accepted.
Tests: each failure type yields its own reason and `submission_error`; the saved `c463bdac` block yields the JSON message with the nearby text; a valid submission has no `submission_error`.

### R2 One correction attempt by the analyst model
New `repair_shared_valuation(state, record, llm)` in `agents/shared_valuation.py`, called from `evidence_with_scenarios` with the quick-slot model the fundamentals analyst uses, when and only when the record has a `submission_error` other than `missing_block`, or at least one row was omitted. One attempt, no tools.
- The prompt contains: the analyst's original block verbatim, the exact reasons from R1, the existing `SHARED_VALUATION_INPUTS` shape text, and the instruction to return only a corrected `valuation_scenarios` block, changing nothing except what the reasons name.
- The corrected block goes through the same `prepare_shared_valuation` validation. It replaces the original only if it prices more cases than the original did; otherwise the original record stands and gains the reason `Correction attempt did not produce an accepted case.`
- Each case that is priced after correction carries a visible note on the scenario table: `Row N: corrected by the analyst after a validation error: <original reason>.` The analyst's original text stays unchanged in the saved report.
- A model or provider error during the attempt is caught, recorded and never fails the run.
- Not retried: an empty list (a valid "no case" answer), a run where scenarios do not apply, a REVIEW-route run.
Tests, with a stub model: the three real failures above are each corrected and priced with the note; a correction that is still invalid leaves the original record plus the failure reason; a correction that changes a case that was already priced is not applied to that case; a provider exception leaves the original record; no call is made for an empty list or a fully priced submission; the corrected requests are what publication replay and the advisory audit read.

### R3 The score reflects what happened
`operational_audit`:
- a submission that failed as a whole and was not corrected scores 3 (`valuation_cases_rejected`), using `submission_error` so an unreadable block is counted;
- a successful correction is recorded as `valuation_submission_corrected`, scored 5 like the existing recovered-retry codes, and listed in the operational audit detail.
Run `c463bdac` without a correction would have scored 3/5.
Tests: unreadable and uncorrected scores 3 with its reason; corrected scores 5 and is listed; empty list and not-applicable stay 5.

## Proof and acceptance

- Each task's tests fail before the change and pass after.
- Offline replay of the three saved runs with a stub model that returns the corrected block: each ends with its cases priced and the correction note; with a stub that returns the same bad block, each scores 3/5 and names the cause.
- Full `pytest -q` and `ruff check .` pass on the final commit.
- Independent audit through the registered executor, then closure of confirmed findings.
- Optional, needs approval: one real correction call on the saved `c463bdac` block through the configured quick model, to prove the model actually fixes it. Estimated under $0.50.
- Not proven without a paid run: behaviour inside a full live run.

## Estimate

- Build size: small.
- Recommended model: Claude Fable 5.2, `claude-fable-5-2`, medium effort. One new function, one call site, clear tests and three real failing inputs to replay.
- Wall-clock: 2 to 4 active hours including the audit and closure. Build Z had the same estimate and took about one hour.
- Run cost after the build: one extra quick-model call only in runs where the submission fails; no cost in runs where it is valid.

## Boundaries

No merge, push, install, production promotion or paid call without separate approval. Build in an isolated worktree from `242582db`.

## Not in this plan

- Provider-enforced structured output for the whole fundamentals report. The analyst uses tools and writes four blocks plus prose in one answer; changing that is a larger redesign.
- A second correction attempt.
- A deterministic JSON fixer. It would handle today's brace but not the other two failures.
- Point-in-time valuation history, an expected-return model, execution backtests, pre-debate fact checks of analyst prose, and the display items from earlier reviews.

## Decisions for the user

1. Approve Build R as written?
2. Approve one real correction call (under $0.50) as proof after the build?
3. A successful correction scores 5/5 with a visible note (recommended), or 4/5?
