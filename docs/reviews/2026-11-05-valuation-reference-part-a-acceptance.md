# Part A valuation reference acceptance

Status: implementation and offline corrections verified; Part A remains incomplete because live consensus, accepted-peer and event observations are missing. Additional proof requires approval.

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

The approved Part A attempt is complete but acceptance is unmet. Implementation, independent review, affected recovery, artifact corrections and the A7 tooling/budget proposal are complete. A further live proof needs explicit approval; see the current decision below. Exact-head publication CI and all release actions still await separate authority.

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

## Offline qualification boundary before the live proof

The complete current offline inventory is accounted for with combined evidence across revisions: 2,505 selected tests have passing evidence, one optional Bedrock SDK test remains skipped, and one configured integration test remains deselected (2,507 collected in total). This is not one complete passing run on one revision. The broad run supplied 2,461 passes; its two fixture failures were corrected and rerun; all six subsequently added product regressions passed; the final A7 pair supplied 36 passes. The existing 100 subtest passes remain separate from these test counts.

Reuse is justified by the recorded broad-run source manifest and unchanged Python 3.12 environment, all 90 noneditable dependency pins, pytest configuration and product operating assumptions. Only the peer/history/render flow, explicit valuation-basis text, REVIEW/audit routing and constructor-bypassing portfolio fixture changed after the broad run; their focused tests and affected publication/checkpoint/recovery paths were rerun. The final Markdown table correction passed 48 affected tests. Publication, reports and checkpoint recovery passed 130 affected tests. New A7 files have their own final 36-test evidence, including actual CLI capture/replay with fake model HTTP, an eligible synthetic DOCN filer, RPO sources, prior/default/new peers, exact depth, the real SDK transport, one-shot claims, cost caps, unknown costs and the blinded reviewer callback.

Final gates: full repository Ruff passed; pip check passed; all 90 dependency pins still match; diff check passed. The final source-control correction reran the affected 36 checks and full Ruff; source hashes remained stable during execution. Logs and manifests: part-a-final-local-checks.json, a7-source-control-final.json, a7-source-control-final.log, full-ruff-final.log, final-pip-check.log and test-inventory-final.log. Collection alone is inventory evidence, not passing-test evidence.

The final retained-input replay is private/evidence/offline-replay-20261105-v3. Markdown hash 074e7b9f89e98382b650f738a7674cc0665fdc0769cc98de40fc2e00383cc8aa; HTML ffdeac0ba6054341f9f2b32b39aa18623eb00129208b3a377d7a45bbfe0e86b3; CLI e0200765f51b26450a80169a7fe05af47add4e087816b44a3b57d235972f4d6f. Its 22 artifact checks passed and all 26 original inputs remained unchanged. Primary and source-check agents inspected PDF-rendered HTML pages 36–37: eight history rows, eight consensus rows, notes outside tables, correct enterprise/equity labels and adjacent source guidance. Direct headless viewport screenshots were blank; PDF printing and native PDFKit page rendering supplied the visual inspection. This is an offline replay of old model text, not live peer/audit proof.

Two separately retained real-source peer packages reproduced independently: MSFT 11.9151x equity/revenue, 17.9138% growth and 67.6569% gross margin; ORCL 5.2128x, 21.6188% growth and unavailable gross margin. AKAM was excluded because the existing approved SEC mapping supplied no compatible TTM revenue. Both valid peers use the retained DOCN November 4 completed session and dated shares/filings. These later acquisitions are retrospective arithmetic/source-eligibility proof, not original-run timing or verified business comparability. The 16-file hashed inventory is private/evidence/two-peer-source-check/proof-summary.json.

A7 tooling preserves the A/B model IDs and ABBAAB order, uses original model prose for metrics and blind review, records source misses even if the product catches the error, and rejects a controlled-comparison receipt when replay is incomplete. Internal audit counts never rank setups. The proposed common reviewer is anthropic/claude-opus-5.5, temperature 0, maximum 4,096 output tokens, one fresh nonstream JSON call per output, provider-default reasoning (record actual usage), no retries. It overlaps setup B's deep tier; style may still reveal identity. Its six calls and six CLI runs remain separately unapproved. A usage-based ceiling will follow the Part A proof; no comparison call is required for Part A acceptance.

The new task-specific harness is separate from the earlier fixed-Terra/depth-1-or-5 harness so its old ledger and authorization remain untouched. It reuses the real CLI, source functions, HTTP transports and publication/recovery paths; its fixture drills are explicitly not live evidence. Private proof runtime disables dotenv reloading, isolates yfinance/cache/results/memory/preferences, refreshes actual account usage and all three model endpoint rates before execution, and reserves conservatively before each request. The aggregate proof ceiling remains $10; this Part A attempt is additionally capped at $5, retaining at least $5 for a later separately authorized Part B attempt. Unknown costs retain their reservations.

Independent pre-live review and primary inspection closed the material product and tooling findings in this worktree. The external audit record is evidence/part-a-independent-audit-prelive.md; final live observations still require review. The one authorized Part A paid CLI attempt remains unstarted at this boundary. No additional reports, Part B work or publication are authorized.

## Live attempt and corrected candidate — acceptance incomplete

The one authorized Part A CLI attempt ran from frozen clean commit 6764186f633294fdd08bfa47e6b522fde73283c5 on 2026-11-05, 23:24:15.495203–23:29:30.411505 UTC, after the NYSE regular close at 21:00 UTC. Machine 1 PID 60746; private runtime ../private/part-a-live-proof; job evidence/part-a-live-proof.job.json. It ran all four analysts and one research/risk round, with Terra Pro in both tiers. All 17 requests settled to $1.14128440; zero unknown costs or automatic retries. The resolved provider was OpenAI; no response reported length truncation. Fresh account usage before/after agrees with the request-cost sum. Remaining aggregate allowance is $8.85871560, but Part A's attempt authority is consumed. Remaining money does not authorize another attempt. Part B still needs its own go-ahead.

The canonical quote is the completed November 5 close, $70.69999694824219, retrieved at 23:24:22.287964 UTC with provider regular-session end 16:00 America/New_York. Current equity/revenue is 7.5607278344x; eight historical rows, low 3.12x, median 4.47x and high 16.31x. This after-close proof contains no live partial bar; partial-bar exclusions retain their offline evidence. Optional FRED macro data was unavailable because no credential was authorized.

The model proposed AKAM and NET with reasons; both were fetched after the analysts. AKAM lacked compatible verified TTM revenue; NET lacked eligible outstanding shares. These are honest exclusions, but no accepted live peer table was observed. Separate MSFT/ORCL source checks do not substitute for live model-selected success.

The advisory audit executed with 20 accepted, quote-attributed findings, all labeled unsupported by the supplied material; zero rejected. Independent review matched every quoted claim to original role prose. This verifies execution, attribution and status, not substantive accuracy or contradiction/numerical-error detection. All roles correctly say same model. Input truncation is disclosed; evidence absent from its bounded context can exist elsewhere. The original Portfolio Manager prose names findings that mattered and remains in diagnostics under ordinary publication rules.

The proof exposed two product defects, now corrected:
- Rejected consensus became a minimal dictionary; later validation printed raw schema errors and downgraded the saved event comparison. Unavailable consensus is now typed, scoped and idempotent, preserving the reason and same-scope timing while removing unusable rows. Historical and after-cutoff rejection remain strict.
- Debate lengths were 67/67 because publication replaced histories with placeholder text. Metrics now use retained original histories. Offline recomputation gives 11,088 research and 7,735 risk characters, preserving 17 calls and one round each.

Consensus was suppressed by the private harness fixing the analysis cutoff to run start, before acquisition. The retained valuation brief explicitly states "Vendor expectations retrieved after analysis cutoff". The normal application analysis-day clock was not used. An offline drill with retained real Yahoo data confirms that strict early cutoff rejects the snapshot and the normal day clock accepts all eight estimates, leaving the completed-market cutoff unchanged. Any further authorized proof must use the normal analysis clock. The original typed snapshot and event record cannot be recovered from the final state; no values were reconstructed as live evidence.

The corrections passed 275 affected checks across vendor/event handling, metrics, publication/reporting, recovery and A7 real-CLI fixture drills. Full Ruff and diff checks passed. Python/dependencies/configuration are unchanged, including all 90 noneditable pins; pip check and unaffected broad results are reused. Current inventory: 2,510 tests, with combined passing evidence for 2,508, one optional SDK skip and one configured integration deselection. Three new regressions explain the increase from the pre-live inventory. This is not a full passing run on one revision. Exact source hashes and checks are in evidence/live-corrections-checks.json.

Original report: ../private/part-a-live-proof/results/reports/DOCN_20261105_162929. Offline corrected derivative: ../private/evidence/live-proof-corrected-render, explicitly labeled as a correction of recorded data, not a new analysis. Markdown SHA 0407921666e1753a8c6f1a9b65818a24c2c16dc5e799aedc562e1c944f52630e; HTML SHA 058f630ace3194769e2d1966e663762609613c2884c35383265ddb5af6f0c520. A plain generic retained-snapshot-unavailable reason replaces schema errors; zero accepted peers and unavailable event comparison remain. Original report, receipt and publication hashes are unchanged. Primary and independent visual inspection covered valuation and audit pages.

Independent code findings are closed; live acceptance remains open. Audits: evidence/part-a-independent-audit-prelive.md and evidence/part-a-independent-audit-live.md. No push, PR, merge, installation, production, scheduler or broker action occurred.

## Prepared comparison proposal, not spending authority

A7 remains unexecuted and separate from the proof allowance. Proposed ceiling: $65 for exactly six ABBAAB two-round runs plus six blind Opus 5.5 reviews, without retries or replacements. Reviewer: anthropic/claude-opus-5.5, temperature 0, output cap 4,096, provider-default reasoning recorded, fresh nonstream JSON context. Setup models remain as approved. Common run limits: all four analysts, four tool rounds, 16,384 output tokens, context cap 1,000,000 (within the smallest advertised model context). Reviewer overlap with B and residual style identification are disclosed.

The shallow proof used 1,373,847 prompt tokens and 48,299 completion tokens (including 7,559 reasoning tokens); 561,948 prompt tokens were reported cached. Planning adds five debate turns, each at this run's largest observed input/output, yielding 2,409,647 input and 129,269 output tokens per two-round run. Ignoring cache discounts and pricing all B calls at standard Opus rates yields $3.055992 per A run and $12.223968 per B run. Six reviews at 250,000 input plus 4,096 output tokens each add $6.491520. Total $52.331400 plus 20% margin is $62.797680, rounded to a proposed $65 ceiling. Details: ../private/evidence/comparison-budget-proposal.json.

This is a planning estimate, not measured B behavior or a guarantee. Faster/long-context/cache-write routes can exceed these planning rates; fresh Sol metadata includes a $24/$90 per-million input/output override and cache writes up to $30. The wire guard uses refreshed conservative route caps, not planning rates. More expensive routing or larger inputs may stop the pilot incomplete at $65. No top-up, automatic retry or comparison call is authorized. Freeze and revalidate actual common-source maps plus the exact source/prompt/starting-state manifest before approved execution.

## Decision needed for remaining live proof

Currently authorized implementation and offline correction work is complete. A further paid Part A attempt requires approval because the goal allowed one, and failures/missing acceptance consume it.

Recommended proof adjustment: one additional after-close DOCN attempt, capped at $3.85 within the existing $10 aggregate allowance, with temporary explicitly user-pinned MSFT/ORCL peers for this proof only. Their real source packages passed independent arithmetic checks; business comparability is not established. This combines the first run's live model proposal/rejection evidence with a live accepted-user-pin path, without claiming successful model-selected peer acceptance. It also exercises available consensus and event replay with corrected clock/record handling. Pins remain isolated from preferences and launcher settings. This proposal is unapproved; no extra attempt has started.

## Approved additional proof amendment

The user explicitly approved the extra proof and combined-evidence proposal after the decision above. Approval is retained at ../private/extra-proof-approval.json; the original notification/decision fingerprint is resolved in both stores. The native goal is active again.

Authority is exactly one additional after-close DOCN all-four-analyst shallow attempt, capped at $3.85 inside the original $10 aggregate. The consumed original A attempt and its $1.14128440 cost remain in the same ledger. A2 failure consumes this extra attempt; there is no replacement or automatic retry. A later B attempt still requires its separate start authorization. Comparison, release and installation remain unapproved.

Temporary MSFT/ORCL pins are authorized only for this isolated proof, with the explicit reason that business comparability is not established. The approved evidence combines the original live model proposals/rejections with an accepted-user-pin path; successful live model-selected acceptance remains unobserved and will not be claimed. Free current-session prerequisites passed for both pins using November 5 completed prices (MSFT 11.4891x, ORCL 4.8517x). These later source acquisitions are feasibility evidence, not part of the original live proof.

The normal application analysis-day clock replaces the first harness's too-early exact cutoff. Completed prices retain the separate normal market-observation clock. The additional attempt is not yet started at this preparation milestone. Its claim, exact approval hash, pins, phase cap and aggregate cap must pass offline qualification and independent review before launch.
