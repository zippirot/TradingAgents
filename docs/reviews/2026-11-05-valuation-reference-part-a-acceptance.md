# Part A valuation reference acceptance

Status: implementation in progress. This record does not claim final acceptance.

## Authorized scope and baseline

Part A of docs/superpowers/plans/2026-11-05-valuation-reference-and-forward-model.md only. Part B requires separate go-ahead after the user reviews real Part A reports. The six-run/six-review-call comparison remains unapproved for paid execution.

Machine 1 verified Apple M1 Pro, 17,179,869,184 bytes RAM. GitHub staging fetched without drift from ac661ca291599a8e3e9701bed73f60d979d38a01. Worktree /Users/zipp/Developer/tradingagents-valuation-reference-20261105/part-a; branch codex/valuation-reference-part-a. Installed launcher and existing worktrees untouched.

Original approved plan SHA-256: 4ebb3390add58fead26d8509b65b7388e9d6bcb75f542e2aa1c65734875b101f. Private retained inputs at ../private/inputs; all 26 manifest members verified before and after copying. The application publication/evidence loaders verified decision 8b1933a8-8a3f-438b-b412-45c03fb88c89 and snapshot 893e506dbe9e53e40d2c60726fd91a978b4a5ddd25d25473ea8336f78c9ed0df. No private inputs or credentials enter Git.

## Verification evidence

External task evidence root: /Users/zipp/Developer/tradingagents-valuation-reference-20261105/evidence.

- Fresh isolated Python 3.12 environment; all 90 non-editable dependency pins match the preserved Build 1 environment; pip check passed.
- Source-acquisition, price-implied and valuation-comparison baseline: 40 passed (baseline-focused.log).
- A6 menu/preferences: behavior red run showed missing two-round option; green run plus existing preference tests: 21 passed. Focused Ruff passed (two-round-red.log, two-round-green.log).
- Baseline full-suite reuse: staging is unchanged from the accepted exact-head CI; a duplicate initial full local run adds no source coverage. Final changed-source coverage is still required. This reuse does not establish final acceptance.

## Work remaining

A1/A2 arithmetic and acquisition, A3 consensus integration, A4 context/reporting, A5 audit graph/recovery integration, A6 run metrics, A7 qualified harness/budget proposal, full applicable verification, rendered replay, one authorized live Part A proof and independent audit/gap closure. Part A publication CI awaits separate publication authority.

## Spending and release boundaries

New $10 aggregate/two-CLI-attempt allowance shared by Part A and later authorized Part B, one attempt each; zero spent and zero attempts started at this milestone. Comparison has a separate unapproved budget. No retries, top-ups or extra reports authorized. Do not inherit prior task allowances.

No push, PR, merge, installation, production action, worktree removal, scheduler or broker action authorized. Goal notifier enabled and privacy-minimal dry-run bodies verified; no incident alert has been required.


## Product integration milestone

A1–A6 are integrated for verification; this is not acceptance. Source Acquisition now retains own-history inputs, the prior/pinned default peer set, and typed vendor expectations. After the Fundamentals Analyst, the evidence step validates the proposed set before event comparison and debate. The final section replays saved source projections, keeps history and peer ranges separate, and reports unknown consensus dimensions. Optional pins use `valuation_peers_file` or `TRADINGAGENTS_PEERS_FILE`, mapping a ticker to up to five peer symbols (or ticker/reason objects); an empty list is authoritative. Content changes invalidate the checkpoint signature.

One advisory audit runs after risk debate and before the Portfolio Manager. It audits the original Fundamentals Analyst prose retained by claim validation, discloses per-role model identity and bounded-input truncation, and cannot veto publication or change accepted evidence. Actual debate turns and callback-observed model starts are retained, with incomplete resume coverage labeled.

Fresh combined integration evidence: 80 tests passed in reference-audit-integration.log. Product/CLI Ruff and changed product tests passed; pip check and git diff --check passed. This is focused combined evidence, not the final full suite. Existing component tests and the broader audit/recovery checks remain available; final coverage accounting is pending.

The free Yahoo preflight (private/evidence/reference-source-check/summary.json) returned 658 daily bars and all five expectations sections. Eight usable retained DOCN history quarters replayed and matched independently computed arithmetic. It is source feasibility evidence, not a paid CLI proof. Yahoo fiscal dates and complete accounting bases remain unknown; a numeric guidance/consensus comparison is unavailable for those observations.

Process adjustment: the initial history arithmetic component was written before its failing test was observed. That deviation was disclosed; focused arithmetic tests, independent component review and separate retained-data arithmetic checks were completed afterward. Integration behavior and later corrections used observed failing regression tests.

A7 protocol and the real CLI/cost/source adapter remain under development. Final full offline coverage, rendered retained-input replay, independent code-and-artifact audit, gap closure and the single authorized Part A CLI proof remain required. No paid attempts or model calls have started; prior task ledgers remain untouched.

## Broad offline run and review corrections

The full product offline inventory ran at 0f2b784337cab6965b54d0327fe18beb3074d327 with no tracked-source changes during execution: 2,461 passed, 100 subtests passed, two failed, one optional Bedrock SDK skip and one configured integration deselection. The two A7 tooling modules were excluded while their separate owner was editing them; they remain required. Exact command, source hashes, timestamps and terminal result are in offline-product-suite.job.json; output is offline-product-suite.log.

Both failures came from tests/test_portfolio_context.py's object.__new__ fixture omitting metrics state normally initialized by the graph constructor. The fixture now reflects the constructor's no-callback state without changing portfolio/checkpoint assertions. The affected portfolio and metrics tests passed.

Independent review confirmed and closed source gaps in mixed valid/invalid user pins, visible unavailable history quarters, enterprise-versus-equity table labels, adjacent source guidance with an explicit unavailable consensus difference, and an explicit not-run audit status on new REVIEW runs. Primary inspection also added same-SEC-issuer peer rejection. Corrections retained their failing regression evidence and passed focused checks: pin-identity-and-suite-corrections.log (86); reference-review-corrections.log (99); render-review-corrections.log (74); review-audit-status-correction.log (55). Counts overlap and must not be summed into a single run.

Evidence reuse is by impact: unchanged product checks from the broad run remain applicable under the unchanged Python/dependency environment; peer/history flow, rendering, REVIEW/audit routing and the corrected constructor-bypassing fixture were rerun. This is combined evidence across revisions, not a full passing run on one revision. Final tooling coverage, full repository Ruff, final independent audit/artifact closure and live proof are pending.

Read-only OpenRouter endpoint/key metadata was refreshed at 2026-11-05T22:48:46Z and retained privately with no credential/identifier fields. All three planned model IDs are served. Provider-specific prices include long-context/cache and faster-route variants; the proof guard must conservatively cover permitted routes and refresh again before paid execution. This task still has zero paid attempts and zero spend. Prior account usage is not charged to this task.
