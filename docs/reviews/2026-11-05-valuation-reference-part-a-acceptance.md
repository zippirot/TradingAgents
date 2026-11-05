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
