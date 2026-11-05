# Market evidence and valuation acceptance

Approved revision 2 began 2026-11-05. This record separates local development acceptance from publication/release acceptance.

## Identity and authority

- Goal: thread `01a1acf2-856a-7883-aa92-274cb5e7a172`, created `1793902973`.
- Machine 1: verified `Michaels-MacBook-Pro-2.local`, arm64, Apple M1 Pro, 17,179,869,184 bytes RAM before mutations. All application development/verification runs here.
- SSH: `zipp@100.89.132.10`, key `/Users/zipp/.ssh/tradingagents_machine1`, IdentitiesOnly/BatchMode/StrictHostKeyChecking enabled.
- Canonical repository: `/Users/zipp/Developer/tradingagents-integrity/repository`. Its existing staging checkout was preserved at `f1e846d`.
- Fetched GitHub origin/staging: `6340c9df6cd557195ea13ae994d19bd874b00746`, exactly the reviewed baseline; no intervening drift.
- Build 1: `/Users/zipp/Developer/tradingagents-market-evidence-20261105/build1`, original frozen branch `codex/market-evidence-build1` at `8850b74fb5cb6bf4d65572b50cd56ed18cee0378`; corrected release branch `codex/market-evidence-build1-correction`, application head `2c3b7d00e4088380e7f2637371e86e3dd658d966`.
- Task evidence/private root: `/Users/zipp/Developer/tradingagents-market-evidence-20261105`. No installed runtime or other project was modified.
- New authority: $10 aggregate, at most three paid CLI attempts total; failures count, no retry reserve. Attempt 1 completed: 17 model requests, $0.83083285 actual cost; $9.16916715 and two planned attempts remain.
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

## Build 1 live proof and narrow correction

The all-analyst shallow CLI on frozen `8850b74fb5cb6bf4d65572b50cd56ed18cee0378` completed successfully (exit 0), with actual price fetches November 5 at 18:47:59–18:49:59 UTC / 13:47:59–13:49:59 New York, before the 21:00 UTC / 16:00 session end. Official schedule: https://www.nyse.com/trade/hours-calendars, corroborated by provider session metadata. Run: `evidence/paid-proof/build1-open`; report: `results/reports/DOCN_20261105_115240`. Raw Yahoo rows show completed November 4 close 84.0199966430664 and actual unfinished November 5 values 72.50 / 72.5250015258789. Actual stock/snapshot/indicator tool output excluded November 5 before calculation; all used November 4. The report separately labels a provisional 72.50 quote, vendor cap/P/E limitations and advisory sale reference 84.02. Quote news succeeded twice with retained publication-window filtering; search fallback was not exercised in this attempt and remains a final-proof obligation. No target or scenario was forced.

The installed yfinance 1.8.0 returns lazy `HistoryMetadata`, a Mapping rather than dict. Live inspection found the new OHLCV loader had conservatively dropped its currency/end metadata, although partial-row exclusion was correct using the frame timezone. Preserved the paid-run branch and corrected only the type acceptance on a separate branch. Actual-wrapper regressions failed before and pass after correction, including before-close rejection, after-close admission and no lazy trading-period fetch.

Corrected application commit: `2c3b7d00e4088380e7f2637371e86e3dd658d966`. Full suite: **2329 passed, 1 optional skip, 1 integration deselection, 100 subtests**, 20 known warnings, 16.10 seconds; full Ruff/pip check/diff check pass. Reviewer independently ran 40 focused tests and verified original paid-run source hashes. Supplemental **free source/caller proof**, not another paid CLI attempt, on the clean corrected commit fetched actual Yahoo data at 19:03:51–52 UTC / 14:03:51–52 New York. It retained USD and 16:00-05:00 end metadata, excluded actual unfinished 72.38999938964844, and produced the same November 4 84.0199966430664 canonical close in stock/snapshot paths. All 11 default indicators independently reconcile to captured completed rows. Receipt: `evidence/build1-corrected-source-proof/receipt.json`.

Evidence reuse is explicit: the only application delta is dict→Mapping acceptance. Pre-close finality, cutoff, cache TTL, indicator algorithms, graph, model calls, news, rendering, publication and memory paths are unchanged. Original paid execution, rendered replay, fresh-wheel import smoke and 59 recovery tests remain valid for those unchanged paths/dependencies; affected loader and callers received new offline/full-suite and actual-source checks. **This is combined evidence across revisions, not a paid all-analyst run on the corrected SHA.** Changed model prose from restored currency was not observed in a corrected paid run. Live after-close admission was not observed; actual-wrapper fixed-clock tests cover that boundary. Original metadata captures are JSON strings of the provider wrapper, not replayable structured objects; the supplemental proof includes selected structured fields. Its initial assertion compared equivalent timezone strings; the assessment corrected that expectation by comparing instants against the original captures, with no application change or repeated source calls.

Actual cost: **$0.83083285**, one of three attempts. All 17 requests settled using provider response usage; refreshed key-level usage after reporting lag agrees exactly. The earlier immediate key delta was incomplete due to reporting lag. Two final attempts and $9.16916715 remain; no retries/top-up authorized. Original inputs, preferences and installed applications preserved.

## Build 1 release decision

Build 1 local development acceptance is supported by the disclosed combined evidence and independent review. Candidate is isolated from Build 2/3. Original paid source 8850b74 and reviewed staging baseline `6340c9df6cd557195ea13ae994d19bd874b00746` are preserved as references. Publication/CI/release acceptance is pending. Proposed next step under separate user authorization: publish only this corrected Build 1 branch, run required exact-head GitHub CI, reassess staging drift, and integrate/install only the accepted Build 1 source after green CI. Preserve current launcher/source/configuration and user data before any separately authorized replacement; rollback must preserve newer reports, memory and immutable publications. No release action has been performed.

## Outstanding acceptance

- Build 2: deterministic independent valuation and source-only historical scenario suitability are in progress in `/Users/zipp/Developer/tradingagents-market-evidence-20261105/build23`, branch `codex/market-evidence-build23`, based on frozen 8850b74. It will inherit the narrow Mapping correction without moving the original frozen branch.
- Build 3: pre-analyst acquisition/shared brief and recovery remain required.
- Final full offline/lint/dependency gates, two remaining paid proofs, independent code-and-artifact audit/material-finding closure, clean committed records, notifier disable only on actual completion/abandonment.
- Exact-published-head GitHub CI remains pending separate publication authority; local checks do not establish release acceptance.

## Build 1 boundary evidence hashes

- `evidence/build1-correction-full-suite.log`: `8f1f37338c343e880a301366c86a663543e8576536c310f9159e6af61b89652c`
- `evidence/build1-corrected-source-proof/receipt.json`: `e7cb639012916bae07d65e19cc0d9cb445bd511ca8d853eeb52ae7d6f3511a42`
- `evidence/build1-correction-independent-review.md`: `1bcbb2eac699109c78362789e4b2578b231a3ad04c764ffef03266d9801b3173`
- `evidence/paid-proof/cost_ledger.jsonl`: `e11d3bcc7ee7804993c39e3a616ca6a8e04e1cfc16c6c56e47e87d160f9756e1`
- `evidence/paid-proof/build1-open/usage_after_lag.json`: `f73cf93655adb58dc45a121646c9c0c897b060d9e4943edc6711d8f67104d6fa`
- `evidence/paid-proof/build1-open/source_sha256.json`: `7f307bbace0578a823e8940de2e38a50e5f31077a1d79f1c3e861e4258af31f9`
- `evidence/paid-proof/build1-open/results/reports/DOCN_20261105_115240/complete_report.html`: `35bd2141c7ee981193039ee1d78f27a8be04e32b37458f84fa6a097b25784156`

Actual paid-report HTML: primary and independent reviewer visually inspected exact sale, market and vendor sections rendered with original CSS; labels readable. Direct long-page anchor capture was blank, so bounded section captures were used. Original report unchanged. Screenshots: `evidence/build1-paid-visual-review/`.

## Publication transition and Build 2 milestone

The user separately authorized Build 1 push/PR for CI on November 5. Draft PR https://github.com/zippirot/TradingAgents/pull/2 publishes exact `b89353fa89fe67d49c02a5fb5f103fc6a79a9853` against rechecked unchanged staging `6340c9d`. CI was started; merge and installation remain unapproved. M1 lacks a GitHub push credential, so its exact Git bundle was relayed through a task-private bare object repository on the coordinating Mac using existing keyring authentication. No application checkout/execution occurred there. Receipt: `evidence/build1-publication.json`. The decision alert was provider-accepted and its queue/notifier fingerprint resolved after explicit user approval. Build 1 remains frozen. Build 2/3 inherited only its Mapping correction and records through local focused cherry-picks `d97c214` / `d955e76`.

Build 2 implementation: an independent source-only What the price implies section remains available without model targets. It retains dated outstanding shares, a separately conditional guided diluted weighted-average share range, complete obligation definitions, source IDs, revenue ranges and conditional growth-floor assumptions. Unavailable inputs suppress only affected rows; generic source periods prevent hardcoded example years from leaking into future reports. Non-stock/REVIEW scopes remain explicit. Missing reported shares does not erase independently supported guided-share sensitivity.

Retained DOCN reconciliation uses completed price 84.0199966430664, September30 shares117920731, dated equity value9907699422.7679359695384USD, TTM revenue1102671000USD, and net-obligation perimeters -204466000 /719133000 /1385744000USD. Full-year management revenue guidance1208000000–1211000000USD and guided Q4 diluted weighted-average shares128000000–129000000 are ranges, never midpoints or claims of current shares. Management's2027growthfloor60% yields only a conditional upper ratio using the explicit2026base and fixed capital. Input/source/hand-reconciliation receipts: `evidence/build2-input-reconciliation.json` and `.md`.

Historical P/E arithmetic remains inspectable and separately assessed. Retained DOCN 2025EPS2.52 precedes exact verified issuance887888000USD and conversion515696000USD; its three scenarios remain historical diagnostics but are excluded from decision-use comparison/final targets. Exact fact/source/date traces are in `evidence/build2b-suitability-replay.json`. Absence of events is not no-event evidence; unknown coverage remains comparability-unestablished. A comparable historical control is conditionally comparable without automatically becoming a forward target. No unusual-item engine or blanket arithmetic ban added.

Verification: supporting scenario slice188passed, independent-table slice123passed; primary integrated slice204passed after one discovered legacy-guard regression. The original publication guard still returns no mutation for old unvalidated states; the new legacy appendix is confined to the presentation copy, with original data and publication meaning unchanged. Full Ruff/dependency/diff checks pass. Private DOCN acceptance inputs remain outside Git; portable synthetic arithmetic and source-qualification coverage supplements that replay. Final full-suite, graph integration, rendered report/recovery and independent final audit remain required before final acceptance.

## Build 3 integrated milestone

Source Acquisition precedes the four parallel analyst branches, with Memory Log retaining its independent start/join. Acquisition retains raw financial evidence for deterministic replay, enriched source facts, filings, source checks, a canonical completed price and one bounded18k-character brief. Every actual analyst factory consumes that identical brief. The source tools serve the retained package or a clear unavailable/mismatched-cutoff response, never a replacement vintage. Later Evidence Check still validates model claims, prepares canonical report/debate inputs and controls REVIEW. Acquisition alone has no final evidence-quality/rating authority. Technical-only/non-stock paths acquire no mandatory SEC dependency. News distinguishes issuer disclosure from independent coverage; sentiment requires matching metric/period/unit/definition and never authenticates an account or story from a number.

Checkpoint signature now evidence=4/source_acquisition=1; old states retained under their old identities. Pre-/post-acquisition interruption, replay once, memory join and final REVIEW tested. Added acquisition/brief to existing full-state and evidence snapshots for audit/recovery. No new persistence store introduced.

Verification:65 acquisition/graph/checkpoint tests and35 deterministic regressions passed;60 prompt/tool tests passed, including all four real factories. Portable source-grounded range tests passed without private inputs. First full suite:2384passed, one failure from the old expected checkpoint-signature version. Updated the expectation while preserving explicit old/new-ID and old-state preservation assertions. Added source/brief serialization regression; stable full offline suite: **2386passed,1optionalBedrockskip,1integrationdeselection,100subtests,20knownwarnings,16.82seconds**. FullRuff andpipcheck pass. An attempted focused recovery command named a nonexistent test file and ran zero tests; the stable full suite subsequently ran all tests, including required recovery/serialization cases. Logs: `evidence/build23-full-offline-first.log`, `evidence/build23-full-offline-stable.log`, `evidence/build3-prompt-tools-focused.log`; acquisition log initially `/tmp/build3-acquisition-tests.log` onM1.

Build1 publication transition: all7 exact-head GitHubCI jobs passed run42091972884. User separately approved stagingmerge; PR2 merged at `a17d56eee945defc585646083ea0d1a6878502a8`. Launcher installation remains unapproved. Read-only inspection found installed `600dad3` pins OpenRouter menu choices; a separate M1 installation candidate is being prepared to preserve that customization. OriginalBuild1release and installedapp remain preserved.

Final code/artifact audit, fresh install smoke, retained/private replay and render, two remaining paid proofs and their source/prompt/recovery assertions remain outstanding. This milestone is not final goal completion or finalreleaseacceptance.
