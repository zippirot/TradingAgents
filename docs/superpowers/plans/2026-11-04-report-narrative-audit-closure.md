# Restore readable research while preserving evidence authority

Date: 2026-11-04. Status: implemented and verified on Machine 1; publication remains unauthorized.

## Outcome

Restore the useful analyst, bull/bear, research-manager, trader, risk and portfolio-manager narrative in readable reports. Separate that model-authored research from authoritative evidence, rating, validated target or explicit target omission, and sizing limitations. A reader must not need to open diagnostic JSON to understand the reasoning. Missing critical evidence must still produce REVIEW with no actionable decision or trading-memory entry.

This corrects the unconditional narrative suppression confirmed in Claude's audit and a direct reproduction: even prose containing no price or allocation disappears from both SEC-fundamental and technical-only runs. The previous completion assessment overstated product acceptance; passing safety tests did not establish preservation of the intended research output.

Audit: `/Users/zipp/Claude/audits/2026-11-04-tradingagents-report-evidence-integrity-audit.md`.
Original requirements: `2026-10-20-report-evidence-integrity.md` and its linked assessment.

## Baseline, execution and estimate

- Existing Machine 1 worktree: `/Users/zipp/Developer/tradingagents-integrity/feature`, branch `codex/report-evidence-integrity`.
- Reviewed HEAD: `7da7fd4d6dc5edd31c8cc515f977815d998cf348`; implementation `a0eb92c9a4bd009cca786b998fde184e7046c864`. HEAD adds evidence/documentation only.
- Canonical staging last verified at `3411158f91eb267aab8760fc90afbf43556eb0bb`. Before implementation, inspect current branch/worktree state and compare current GitHub staging. Preserve the existing feature work; do not restart from staging or substitute another branch. Investigate any drift before modifying overlapping files.
- Development, tests, rendering and paid application checks remain on Machine 1, verified M1 Pro/16 GB, over `ssh -i /Users/zipp/.ssh/tradingagents_machine1 -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes zipp@100.89.132.10`. This Mac coordinates and stores the proposed plan. Transfer this finalized plan explicitly into the remote worktree before implementation; do not copy secrets or runtime data wholesale.
- Build size: **medium**. Recommended model: **GPT-6 Astra (`gpt-6-astra`), medium reasoning**. The difficulty is keeping human-visible research separate from machine-consumed decision authority across publication, streaming, memory and recovery; superficially passing tests can miss that boundary. This is engineering judgment, not a measured model speed comparison or a request to change the running model.
- Active implementation and verification estimate: **4–8 hours**, assuming existing environment and API access remain available. Excludes approval/external waiting and subsequent remote CI. Codex credit range cannot be estimated credibly without measured usage for this follow-up.
- Previous aggregate API usage: **$0.444111567**. If implementation is authorized under the original verification budget, retain the **$10 aggregate ceiling across both builds**, not another $10. Refresh provider usage before reserving any run. The user's existing-key exception remains explicit: the provider's $250 weekly cap is not a $10 enforcement guarantee. No top-ups or new paid service/model commitment.

## Chosen approach and scope

Use the existing retained `unvalidated_outputs` and existing report/publication paths to present two clearly distinguished kinds of content. Do not invent a semantic verifier or use numeric-claim detection as proof that prose is safe. Canonical decisions stay authoritative; original research is explicitly labeled and separately presented.

For sufficient, limited or not-applicable evidence scope:

1. Keep the canonical rating, evidence scope, target result/omission and sizing limitation clearly identifiable, especially in the portfolio decision.
2. Restore original narrative under a consistent **Unvalidated model research** heading in its corresponding report section. Preserve original section order and nonempty debate histories. Include fundamentals reasoning as well as research/trader/risk/portfolio narrative; canonical facts must not erase the explanation.
3. State that numbers, targets, allocations and execution proposals in that research are model claims, not validated targets or instructions. Where a target is unsupported, the adjacent authoritative section must explicitly say so. Do not silently relabel a fundamental target as a technical level.
4. Preserve the complete original text in diagnostics. Rendering must not mutate graph state, source evidence, structured target requests or tool messages. Repeated publication/export must not duplicate banners or recursively embed canonical output as original research.
5. Keep memory/settlement/scoring inputs canonical. Restored presentation text must never replace the canonical decision text written to trading memory or become a new source for rating extraction. Reuse the existing report-state projection where possible; introduce only the smallest explicit separation needed across callers.

For insufficient evidence/REVIEW, retain the current readable explanation and skipped decision/debate behavior. Raw research stays in diagnostics; this correction must not display trading proposals as a REVIEW decision. Historical completed artifacts and legacy memory remain unchanged. Technical-only and non-SEC scopes retain their research without claiming SEC validation.

Included: F1 narrative preservation, F2 literal-newline correction, narrowly scoped F3 CI branch coverage, and accurate F4/F5 verification/limitation records. Excluded: new valuation methods, generalized narrative reconciliation, a KPI extraction overhaul, another model/provider, dashboard redesign, broker functionality, production installation or historical report replacement.

## Task 1 — Restore narrative at the presentation boundary

**Files:** `tradingagents/agents/output_validation.py`, `tradingagents/reporting.py`, `tradingagents/report_html.py`; inspect affected callers in `tradingagents/graph/trading_graph.py`, `tradingagents/agents/stream_publication.py` and `cli/run.py`. Change callers only where necessary to maintain one coherent contract. Relevant tests include `test_output_publication.py`, `test_evidence_reporting.py`, `test_stream_publication.py`, `test_review_authority.py` and `test_review_memory_backtest.py`.

**Implementation:** Trace final publication, CLI display, Python returned state, direct HTML rendering, saved per-section reports, consolidated reports and `record_decision` together. Define explicitly which objects contain canonical decisions and which are presentation-only. Restore labeled original research through the shared presentation mechanism; expose the original research consistently to Python consumers without weakening canonical decision fields. Preserve the exact canonical decision sent to memory. Fix the escaped newline separator in the omitted-target text. Keep diagnostic originals and evidence/quality JSON stable.

**Verification:** First reproduce failures for benign narrative retention in SEC, technical-only and non-SEC scopes. Replace blanket assertions that all raw prose must disappear with assertions that it is retained only in a labeled research section and cannot control the authoritative result. Do not weaken target validation or REVIEW assertions. Cover:

- Benign prose, unsupported dollar/numeric-word/non-English target claims, allocation claims, and conflicting prose versus a valid structured target.
- All affected analyst/research/trader/risk/portfolio sections, rather than only final decision text.
- Supported structured target, unsupported target, free-text fallback, missing original text and repeated export/idempotency.
- Markdown, direct HTML, saved report tree, final CLI display and Python contract; no duplicated narrative or banners.
- Explicit REVIEW, empty skipped sections, no memory insertion, settlement/scoring exclusions and same-date corrected rerun behavior.
- Canonical memory content contains no restored unvalidated research even when the readable report does.
- Literal newline characters render as paragraph separation, not visible backslash sequences.

## Task 2 — Make the documented branch CI behavior accurate

**Files:** `.github/workflows/ci.yml` and the existing evidence/acceptance record.

**Implementation:** Add `staging` and `production` to the existing push branch list while retaining `main`, version branches and pull-request triggers. Preserve existing jobs, Python matrix and concurrency. This closes the pre-existing mismatch with the documented release workflow; it does not authorize a push, merge or production change.

**Verification:** Inspect the actual trigger diff and validate workflow structure with available tooling. Run the existing local checks required below. Report remote CI and unavailable Python versions as **not run** until an explicitly authorized push/PR actually triggers them. A committed workflow edit is not a passing remote CI run. Remote CI on the resulting commit remains an integration/release gate after publication is separately authorized.

## Task 3 — Prove restored reports without repeating unaffected work

**Offline checks on Machine 1:**

```sh
.venv/bin/python -m pytest -q tests/test_output_publication.py tests/test_evidence_reporting.py tests/test_stream_publication.py tests/test_review_authority.py tests/test_review_memory_backtest.py tests/test_portfolio_valuation.py tests/test_reporting.py tests/test_report_html.py tests/test_cli_headless.py tests/test_checkpoint_resume.py
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/python -m pip check
git diff --check
```

Extend focused selection for new tests and affected callers. Verify existing test names before execution. Preserve meaningful assertions and diagnose setup/application/external failures separately.

Replay retained real full-state and raw model outputs from `../evidence/m6-acceptance-source` through the corrected report writer into a **new** proof directory. Inspect complete narrative sections, authoritative target omission, evidence tables and REVIEW output visually in Markdown/HTML. This replay is useful regression evidence, not a new live model run. Do not overwrite prior reports.

On a committed candidate with isolated results/cache/memory/preferences, run bounded actual CLI proofs for:

1. A source-complete SEC-fundamental run: readable research survives, core evidence checks pass, target is validated or explicitly omitted, and canonical memory remains isolated from displayed research.
2. Controlled SEC unavailability: readable REVIEW, no target/trading proposal as the decision, no trading-memory entry; injection confined to the proof process.
3. Technical-only selection: readable research survives and the scope does not claim SEC validation. Non-SEC scope must also pass focused integrated report tests; a separate live non-SEC run is not required solely to repeat the same presentation contract.

Use the existing runners and process/log conventions; inspect before adapting them and never duplicate live jobs. Recalculate each run's conservative cost bound against current aggregate usage. Run sequentially if reservations cannot fit concurrently. No automatic repeated model attempts to force a desired structured response. Record actual provider/model/configuration and source/fixture hashes.

F4 is an evidence distinction: exercise a valid structured valuation request and free-text fallback end-to-end offline. Record which path the live model actually takes. If the live run again falls back, do not claim live structured-output success; do not change models or increase spending merely to erase that limitation. F5 remains explicitly bounded: inspect and report accepted/rejected optional disclosures; do not represent recorded AI Customer ARR validation as live extraction success or silently expand this follow-up into extraction redesign.

Review checkpoint/publication compatibility. If changed state semantics or signatures can affect resumed runs, test old/current checkpoint behavior and perform affected real interruption/resume. If this is solely a presentation change with unchanged persisted authority, retain the previous recovery proof with exact source/dependency justification and test export from retained resumed state. Do not rerun expensive recovery without an affected contract.

## Task 4 — Independent review, evidence and handoff

Obtain one independent review of the complete correction, concentrating on readable product behavior, canonical-versus-research boundaries, memory/rating consumers, REVIEW, idempotency and scope preservation. Review actual rendered reports, not only tests. Close confirmed material findings in the same worktree and rerun affected verification.

Update the existing acceptance/audit records with findings F1–F5, corrected behavior, exact tested commit, commands/results, rendered artifact paths, API spend, reused evidence rationale and remaining limitations. Explicitly correct the earlier overbroad completion claim. Keep the original audit and historical proof untouched. Commit task changes and records; require a clean task worktree.

**Completion requires:** substantive labeled narrative is visibly retained; authoritative target/rating/sizing and REVIEW rules remain intact; canonical memory stays separate; focused/full checks and required actual report proofs pass; independent review closes material issues; implementation and evidence agree; all changes are committed. CI configuration can be complete locally while remote CI remains explicitly pending authorized publication. No claims of universal prose validation, reliable extraction of every KPI or live structured-output success without evidence.

## Approval and release boundary

The proposed product choice is to restore labeled research, not keep evidence-only reports. Approving this plan would also approve the narrow CI trigger edit; actual pushes, pull requests, merges, releases, installation, production alteration and worktree removal remain separately authorized. No additional product decision is needed for ordinary implementation details within these boundaries.

Rollback, if needed, is a focused local revert of follow-up commits while retaining evidence and leaving installed applications and historical reports untouched. Any externally published rollback requires its own authority.


## Execution checkpoint — 2026-11-04

Machine 1 identity, clean existing feature HEAD 7da7fd4 and exact canonical staging 3411158 were verified before edits. The plan was transferred explicitly. Presentation restoration uses prepare_report_state; graph canonical fields, memory, checkpoint schema and provisional streaming remain unchanged. Python consumers can obtain the labeled display with this public helper while retaining canonical propagate() results for decisions. Fundamentals reasoning comes from the existing financial_claim_validation.raw_report; other originals come from unvalidated_outputs.

Nine regression cases cover visible narrative, retained real fundamentals, scopes, REVIEW, supported target beside conflicting research, CLI display, idempotence and memory isolation. Focused suite: 122 passed. Full suite: 1,825 passed, one optional Bedrock skip, one configured integration deselection, 100 subtests. Full Ruff and dependency checks passed. Source/unavailable retained-state replays passed; rendered portfolio research was visually inspected. Independent correction review found no material issue. Actual final CLI source, unavailable and technical-only proof remains required; implementation is not complete.

The prior recovery proof is reused only for unchanged checkpoint/graph/memory authority; current checkpoint tests and actual resumed-state export replay passed. No live interruption is needed for this presentation-only change and the newline formatting correction.


## Final acceptance — 2026-11-04

Implementation d675a0b146e4a5bf559c0bd57fac769377e14aa1 passed 1,826 offline tests, 123 focused checks, full-repository Ruff and dependency checks. The final audit added one integrated non-SEC saved-report case; all 216 recorded source/workflow hashes match the final offline candidate. Application source remains exactly d675a0b; the final commit adds only that test and acceptance records, so the live proofs remain valid. Independent correction and final artifact review found no material remaining gap.

Three actual CLI runs passed on that implementation. Source-complete: eight critical checks, 31 financial claims, ten labeled original research sections (including original fundamentals), canonical Underweight memory with no restored research, target omitted. SEC-unavailable: readable insufficient/REVIEW, no target or memory entry. Technical-only: nine labeled research sections, scope explicitly not_applicable with no US accounting validation, canonical decision/memory separation. Saved state/evidence/quality agree. Actual rendered reports were inspected. Source and technical runs exercised Trader fallback and structured Portfolio Manager output, but not a supported live valuation request. Only Cash was accepted as an optional live disclosure; broader KPI claims remain unverified.

Aggregate provider usage is $0.675044417 across both builds; this follow-up adds $0.230932850. The existing-key exception remains explicit, and no more paid proof is planned. CI push triggers now include staging/production, with jobs/matrix/concurrency unchanged; remote CI and unavailable Python versions remain unrun until separately authorized publication. Previous checkpoint recovery evidence is reused for unchanged persistence/authority, supported by current checkpoint tests and export replay of the actual resumed state.

See ../../reviews/2026-11-04-narrative-audit-closure-evidence.json for exact manifests, hashes, commands, proof paths, audit findings and limitations. The earlier completion claim was too broad because safety verification missed narrative suppression; this acceptance includes explicit product-behavior proof. No push, merge, release, installation, production change or historical artifact replacement occurred.
