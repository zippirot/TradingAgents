# Market evidence and valuation acceptance

Approved revision 2 began 2026-11-05. This record separates local development acceptance from publication/release acceptance.

## Identity and authority

- Goal: thread `01a1acf2-856a-7883-aa92-274cb5e7a172`, created `1793902973`.
- Machine 1: verified `Michaels-MacBook-Pro-2.local`, arm64, Apple M1 Pro, 17,179,869,184 bytes RAM before mutations. All application development/verification runs here.
- SSH: `zipp@100.89.132.10`, key `/Users/zipp/.ssh/tradingagents_machine1`, IdentitiesOnly/BatchMode/StrictHostKeyChecking enabled.
- Canonical repository: `/Users/zipp/Developer/tradingagents-integrity/repository`. Its existing staging checkout was preserved at `f1e846d`.
- Fetched GitHub origin/staging: `6340c9df6cd557195ea13ae994d19bd874b00746`, exactly the reviewed baseline; no intervening drift.
- Build 1: `/Users/zipp/Developer/tradingagents-market-evidence-20261105/build1`, branch `codex/market-evidence-build1`.
- Task evidence/private root: `/Users/zipp/Developer/tradingagents-market-evidence-20261105`. No installed runtime or other project was modified.
- New authority: $10 aggregate, at most three paid CLI attempts total; failures count, no retry reserve. No paid attempt yet.
- No push, PR, merge, installation, promotion, worktree removal, scheduler or broker authority. Exact-head GitHub CI is pending authorized publication.
- Goal notifier key: `thread:01a1acf2-856a-7883-aa92-274cb5e7a172:goal:1793902973`, enabled and verified; dry-run bodies `blocked` / `decision needed`. No test notification sent. Disable only on completion/abandonment.

## Private input handoff

Manifest `private/inputs/manifest.json`, SHA-256 `6dfb2a71a75f0471ac2667e9a013b2227693ccbdc57f1f88a9d6775eb4f4677e`: 26 explicit files / 8,463,748 bytes, frozen read-only. Includes plan, assessment, both attachments, complete November 5 DOCN report, full state/tool log, exact publication and immutable snapshot. Original and transferred member hashes verified. Receipt: `evidence/private-input-handoff.md`.

Application loaders validated decision `8b1933a8-8a3f-438b-b412-45c03fb88c89`, record hash `b0ba780a023061b6d3bcd9792c5218e65551b31deccec418708f628e43f22feb`, snapshot hash `893e506dbe9e53e40d2c60726fd91a978b4a5ddd25d25473ea8336f78c9ed0df`, prior thesis `c45b4127-18c4-5d15-b691-bc90a32eff13`. Replays go outside inputs; no original rewritten.

Existing M1 credential configuration reused read-only: `/Users/zipp/Developer/tradingagents-integrity/private/verification.json`, mode 0600. Only OpenRouter key and SEC contact loaded; no values printed/copied. Provider cap is not task-budget enforcement.

## Build 1 progress and verification

- Completed-session stock, snapshot and indicator paths share the existing OHLCV loader, canonical Yahoo non-dividend-adjusted basis, retained run cutoff and existing session-finality rule. Cached source retrieval metadata is retained inside the existing CSV; pre-close rows cannot become final with elapsed time. Legacy adjusted caches refresh through the existing fetch path; 15-minute TTL retained.
- Fetch window includes all possible current exchange dates independent of host date; returned data still filtered by requested date and completion metadata. No calendar service or universal market close is introduced.
- Vendor fundamentals explicitly noncanonical with retrieval/quote timing, currency, share/earnings-definition limitations.
- Expected quote-news errors fall back to existing search; unavailable remains explicit and ticker/time filtering preserved.
- Buy purchase entry / Sell reference sale level are distinct; legacy ambiguity remains labeled. Exact structural fact-only legacy context omitted without deleting memory.
- Checkpoint signature changed for completed-market semantics; historical checkpoints retained.

Focused evidence: market baseline 33 passed; news slice 91 passed; action/report/thesis slice 143 passed; vendor fundamentals 20 passed; surrounding market tests 146 passed; final new session/cutoff tests 14 passed, including actual StateGraph/ToolNode injection. Relevant publication/restart tests 59 passed; independent reviewer ran 29 compatibility tests. Logs are under task evidence root. These are combined results across development revisions, not a single full-suite run.

Red/green evidence: new session tests initially 9 failures/2 passes; source window regression reproduced technical November 4 versus canonical November 5 for a Tokyo close while host still November 4; corrected tests passed. Independent review also found Sell fallback retaining Purchase Entry Price, now corrected with regression.

Stable Build 1 full offline suite: **2327 passed, 1 skipped (optional langchain_aws absent), 1 deselected (integration), 100 subtests passed**, 20 known model-name warnings; exit 0. Log: `evidence/build1-full-offline-final.log`. Initial full run had 2324 passing and three failures: explicit metadata/adjustment fixture drift and historical prompt timestamp disclosure. Corrected related fixtures and preserved no-current-date historical presentation, with 40 focused checks passing before the full rerun. Two affected fixtures also needed independent cache directories after stock data began using the shared loader. No assertion was weakened to bypass finality or stale-data behavior.

Full Ruff, pip check and diff check pass. Dependency versions: `evidence/build1-dependencies.txt`. Fresh no-dev wheel installation into `private/smoke-env` passed isolated (`python -I`) package and CLI imports from its site-packages plus pip check; log `evidence/build1-clean-install.log`. This temporary test environment does not replace any installed app. Local checks use Python 3.12; exact-head GitHub Python 3.11/3.12/3.13/3.14, New York timezone, clean-install and lint jobs remain pending authorized publication.

Replay: 277 retained rounded tool rows become 276 completed rows ending November 4 at 84.02; historical source adjustment basis is not independently proven by the retained rounded CSV. This is reconstructed offline evidence, not a raw vendor or live proof. Historical narrative remains historical/unvalidated. Corrected replay artifact labels were independently reviewed. M1 Chrome rendered desktop/narrow sale screenshots without clipping; primary visually inspected them. The long historical page screenshot was blank, so its exact Trader section and CSS were extracted and inspected; this limitation is recorded in replay findings. Inputs rehashed unchanged.

Independent review receipt: `evidence/build1-independent-review.md` (also committed beside this record). All material application/artifact findings closed, including final historical-presentation delta. Reviewer executed 26 final affected tests and inspected full-suite/lint/dependency evidence; no claim that source inspection alone proves live behavior.

## Outstanding acceptance

- Build 1 offline development gates and independent review complete on the frozen candidate's source. The first actual NYSE regular-session all-analyst shallow CLI proof and spend reconciliation remain required. Missing required proof means acceptance remains incomplete.
- Paid proof runner and observer are task-private, adapted from the existing runner with three ordered phases, request reservations, actual reported cost reconciliation, no SDK retries, isolated runtime paths and raw source capture. No paid attempt at this commit. Official November 5 NYSE session verified at https://www.nyse.com/trade/hours-calendars: 14:30–21:00 UTC / 09:30–16:00 Eastern. Live fetch timing must still be observed.
- Build 2: deterministic independent valuation and source-only historical scenario suitability, not started.
- Build 3: pre-analyst evidence acquisition/shared brief and recovery, not started.
- Final full offline/lint/dependency gates, two remaining paid proofs, independent code-and-artifact audit/material-finding closure, clean committed records, notifier disable on completion.
- Release acceptance is not claimed: separate integration/publication/installation approval and exact-published-head GitHub CI remain required.
