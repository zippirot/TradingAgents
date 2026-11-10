# TradingAgents: decision-basis repair plan (run d58117ef)

Date: 2026-11-10. Status: approved 2026-11-10 and built; evidence in `docs/reviews/2026-11-10-decision-basis-repair.md`.
Repo: `~/Documents/ChatGPT/Tauric/TradingAgents`. Base: `staging` at `237930f9` (confirm at kick-off).
Evidence run: DOCN decision `d58117ef`, saved state
`~/.tradingagents/logs/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-10_d58117ef.json`.

## Outcome wanted

When the Portfolio Manager weighs the priced valuation cases, the report publishes that weighted,
conditional range as the basis of the rating. Today the pipeline discards it whenever the audit has
flagged a case, even when the manager did everything asked of it.

## What failed, and why (causes confirmed in code and in the saved run)

| # | Failure seen in the report | Cause |
|---|---|---|
| 1 | "Accepted weights sum to 0.15", "not a priced case", basis "opinion only" | The manager accepted all three cases at 0.55 / 0.30 / 0.15. In the same answer it accepted audit findings that name two of those cases. On replay, an accepted finding marks the case disputed, and a disputed case is removed from the priced list (`scenario_decision.py:50`). The manager's answer is then judged against a list of one. The manager cannot accept a finding about a case and weigh that case in the same run. |
| 2 | Only "$103.25" shown, with "close is below the conditional value" | The displayed range drops disputed cases too (`decision_context.py:218`), leaving the upside case alone. |
| 3 | Operational score 3/5: "did not address the priced cases" | The audit reads the status from failure 1 (`operational_audit.py:257`). The message is wrong for this run. |
| 4 | "≥ 85.69: unobserved to breached" and two more, at a $78.30 close | Internally "breached" means "the comparison is not satisfied". The decision card translates it to "not met"; the change note prints the raw word (`decision_brief.py:84-88`). A first reading of "not met" is also reported as a change. The same raw word reaches the Research Manager and Portfolio Manager, who called the labels "conflicting". |
| 5 | Decision card is one run-on block | Card items are joined without line breaks in the rendered card. Exact location to be confirmed at build time. |

Two of the three disputing findings were about a researcher misdescribing a case, not about the
case's inputs. Only the lease-interest finding on the base case questions its arithmetic.

## The rule change (the one product decision in this plan)

A case flagged by an accepted audit finding **stays in the manager's priced list and in the published
conditional range, with the flag shown beside it**. The manager's own accept/reject entry for each
case decides whether it is in the range.

Unchanged and still strict:
- The price-target path is not changed by this build. (Corrected during the build: a case the manager adopts as its
  target is already kept and printed as a disputed calculation; there is no block. See the evidence report.)
- Case arithmetic is never altered by a finding.
- Every figure stays labelled conditional, not a target, not a probability.
- Weights must still sum to 1 and every priced case must still be addressed.

Alternative rejected: keep removing flagged cases (ChatGPT's proposed gate). With a thorough audit
that leaves nearly every run as "opinion only".

## Tasks

### Task 1: flagged cases stay priced
- `tradingagents/agents/scenario_decision.py`: `priced_cases` keeps rows with `disputed_by` and
  carries the finding ids on each case. `render` prints "flagged by accepted audit finding AF-…"
  beside the case. `render_cases_for_manager` adds one sentence: a finding about a case does not
  remove it; weigh it or reject it by naming the input.
- `tradingagents/agents/decision_context.py`: the case-group range and close position use all priced
  cases; flagged ones are marked, not excluded. "Supported scenarios" reports priced and flagged
  counts separately. Adopted-target dispute handling is not touched.
- `tradingagents/agents/shared_valuation.py` (lines 537, 579) and `output_validation.py`: wording
  changes from "excluded from range" to "flagged; shown in the conditional range". Target wording
  stays "excluded".
- Tests in `tests/test_scenario_decision.py`, `tests/test_decision_context.py`:
  - manager accepts three cases and accepts findings naming two: status `addressed`, weights kept,
    range low/high from all three, flags present;
  - a flagged case still cannot be an adopted target;
  - manager rejects a flagged case: range excludes it and remaining weights must sum to 1;
  - when the manager's answer is unusable, the range shows all priced cases with flags, never a
    single surviving case presented alone as "the conditional value".

### Task 2: accurate operational message
- `tradingagents/operational_audit.py`: the `decision_basis_unaddressed` finding states the first
  specific problem from the scenario decision (missing entry, weights, unknown case) and
  distinguishes "not addressed" from "rated against the range without a reason".
- Test: each of the two situations produces its own wording; a properly addressed run produces none.

### Task 3: condition change notes
- `tradingagents/agents/decision_brief.py`: the change note uses the same reader labels as the
  decision card ("met" / "not met" / "no reading yet"). A first reading of "not met" is not reported
  as a change. A move to "met" is always reported.
- The condition lines given to the Research Manager and Portfolio Manager use the reader labels, not
  the raw status word.
- Check, and record the answer in the evidence report: whether the outcome tracker or any stored
  history reads the raw "breached" status as an event. If it does, stop and report before changing
  stored data.
- Tests in `tests/test_decision_brief.py`: unobserved → not satisfied produces no change row;
  not met → met produces one; wording never contains "breached" for a reconsideration trigger.

### Task 4: decision card layout
- Each card item (change notes, basis, scenario range, horizon, coverage, valuation availability,
  trader action, limits) renders on its own line in markdown and HTML.
- Test in `tests/test_decision_page.py`: the rendered card for the saved run has these items as
  separate lines.

### Task 5: proof on the saved run (no paid call)
Replay `d58117ef` offline with the new code and record in
`docs/reviews/2026-11-10-decision-basis-repair.md`:
- scenario decision status `addressed`; weights 0.55 / 0.30 / 0.15;
- accepted range 42.93 to 103.25; weighted value about 70.84 against the 78.30 close;
- both flags visible on the base and downside cases;
- no "breached" change row;
- the operational score and its reason after the fix;
- replays of the five 2026-11-09 runs show no unintended change other than the new wording.

Full test suite and `ruff check .` pass before each commit.

## Acceptance

1. The saved run replays as in Task 5.
2. The four behaviours in Task 1's tests hold.
3. The price-target path behaves exactly as before this build.
4. Full suite and lint pass; changes committed on an isolated branch.

## Out of scope, recorded for later

- Funding inside the case arithmetic: separating lease interest from principal and modelling rent on
  leases that start inside the case period. This is the one audit finding that questions a case's
  numbers. Medium build of its own.
- A computed reference multiple for the cases.
- A shorter path for runs where price and filings are unchanged (this run used 2.3M tokens).
- An independent check of the Portfolio Manager's own text (previously declined).

## Assumptions

- Older reports re-rendered with the new code will show "flagged" where they showed "excluded".
  Their saved evidence snapshots are not rewritten.
- The manager prompt changes by one sentence; no other prompt or debate change.

## Boundaries

No merge, push, install, production promotion or paid run without separate approval. The next paid
DOCN run is yours to make after install.

## Estimates

- Build size: small.
- Recommended model: Claude Sonnet 5.5 (`claude-sonnet-5-5`), medium effort. The rule is narrow,
  the causes are located, and the saved-run replay detects a wrong result. Continuing in the current
  session (Fable 5.2) is equally acceptable. This is an engineering judgment, not a measured comparison.
- Wall-clock: 1.5 to 3 hours of build and verification, plus the same independent audit used for
  Builds Y, Z and R (about 20 to 40 minutes, within its existing cost caps). Say so if you want the
  audit dropped for a build this size.
- Codex credits: not applicable; the plan runs in Claude Code.
