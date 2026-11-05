# DOCN A/B/C implementation evidence

## Authorized boundary and baseline

User authorized all A/B/C milestones with early outcome recording/scoring,
advisory thesis dispositions (automatic hard rules deferred), and final independent
audit plus material gap closure. User explicitly selected GitHub staging
`f1e846d67bd9d02446956df882650f4eedac3a1b` after fetch revealed the original
launcher checkout remained at `b075166df6f1738ef691cee23d1473e5085e05a1`.
The launcher has not been advanced.

Worktree: `/Users/zipp/Documents/ChatGPT/Tauric/worktrees/docn-abc-gap-closure`.
Branch: `codex/docn-abc-gap-closure`. Native creation rejected the nested repository
as outside its allowed roots, without creating a worktree; ordinary Git worktree
creation then succeeded at the approved base. No merge/push/install is authorized.
Existing shared valuation implementation and its evidence are on the base; reuse
is subject to source and acceptance checks rather than rebuilding it.

## First-slice progress (not acceptance)

Created an independent Python 3.12 `.venv`, installed `.[dev]`, and verified that
both interpreter and imported `tradingagents` resolve inside this worktree.
Dependency resolution is new to this environment; prior suite results are not
claimed as verification of this installation.

Added list-marker regression cases and negative preceding-qualification cases.
Before correction: 3 failed, 4 passed, 49 deselected; all three failures were the
otherwise valid bullet-prefixed records. The minimal correction strips layout
markers before deciding whether preceding prose exists; subject, period,
qualifier, comparison, document identity and source-span checks remain in place.

After correction:

```text
.venv/bin/python -m pytest -q tests/test_disclosure_context.py tests/test_disclosure_evidence.py
92 passed in 0.80s
.venv/bin/python -m ruff check tradingagents/dataflows/disclosure_context.py tests/test_disclosure_context.py
All checks passed!
.venv/bin/python -m pip check
No broken requirements found.
```

At this initial checkpoint, remaining first-slice work was compact accepted-evidence presentation, separate
bounded narrative, readable prior decisions, integrated negative/positive tests,
and one authorized real CLI proof. No first-slice acceptance or full-suite success
was claimed. No paid calls had run at that checkpoint.

### Bounded narrative context

Added failing behavior checks for labeled narrative reaching the shared context
and for removing unterminated extraction fences (2 failures before implementation).
The shared context now carries at most 6,000 characters of original research after
canonical evidence, explicitly labeled unvalidated, with instructions preserving
canonical calculation/publication authority. Financial/disclosure/scenario JSON
extraction blocks are removed from this prose view, including an unterminated
final block. Original diagnostics remain intact and truncation is disclosed.
The run signature adds `evidence_presentation=1` so older checkpoints cannot resume
under the changed context contract.

Verification: evidence-gate/graph/publication selection 53 passed in 4.19s;
checkpoint resume/lifecycle selection 13 passed in 0.78s; changed context/test
Ruff check passed. These are focused checks, not full first-slice acceptance.
Additional adversarial integrated assertions, compact evidence/prior-decision
presentation and real proof remain required. The earlier parser results remain
valid: its source and dependency environment have not changed.

### Compact evidence and memory presentation

The shared brief now names current reported metrics, accounting checks, periods,
bases and coverage gaps with readable fact/source labels. Exact IDs live in a
separate reference appendix; the canonical package, source locators and calculation
lineage remain unchanged. Reused compatible-fact selection rejects conflicting
core observations instead of choosing an arbitrary value. Reported quarter/YTD
observations are not silently expanded into new TTM derivations.

Canonical published decisions and new memory entries retain the readable values
without embedding the reference index. Reports expose the exact index once as a
separate appendix. Existing memory records are not rewritten: prompt projections
shorten long hashes and point back to the original record. Original research and
structured extraction remain in diagnostics; structured extraction fences are
removed from ordinary research prose. Five debate/risk roles no longer repeat the
same fundamentals context after receiving the shared brief.

On the original DOCN report's frozen evidence package (1,019 facts), the previous
accounting renderer produced 21,386 characters. The new context including exact
references is 18,536 characters; its readable brief alone is 6,164 characters.
This measures accounting presentation, not total model-token cost or investment
quality. Source: `/Users/zipp/.tradingagents/logs/reports/DOCN_20261104_171931/evidence.json`.

Verification on the application candidate committed as `bb48cf1`: full offline suite **1,869 passed,
1 optional dependency skipped, 1 configured external-service deselected, 100
subtests passed** in 13.92s. Full Ruff, dependency consistency and whitespace
checks passed. Logs: `results/docn-abc/a1-offline/pytest-final-candidate.log`,
`ruff.log`, `pip-check.log`. Earlier focused selections establish regression
behavior; the final full suite includes them. Live proof and visual inspection
of the actual saved live report remain pending, so the first slice is not yet
accepted. A second full suite was justified by the added memory/report projections
and final fact-selection change after the earlier 1,867-test run.

The subsequent report-only polish puts the exact references inside the existing
Evidence and Quality appendix, preventing duplicate section VI numbering, and
uses its fact labels in the calculation table. The affected report/presentation
selection passed 36 tests in 1.04s; full Ruff and whitespace checks passed.
This reuses the unaffected `bb48cf1` suite evidence, not a claim that the entire
suite ran again on the later report revision.

The tracked proof runner is `docs/reviews/docn-abc-proof-tools/live_cli.py`.
Nine offline runner tests passed, including the installed SDK's HTTP transport,
price checks, cross-attempt reservations and failure handling. A free SEC
submissions preflight returned HTTP 200 and valid JSON. No paid request has run
at that preflight checkpoint. Runtime artifacts are excluded locally at `/results/docn-abc/`; helper
source and evidence records are committed. The original launcher preferences
are hashed before/after each proof; credentials are never written to artifacts.

## Paid verification decision

User approved: USD100 combined ceiling, allocated USD70 to at most seven
Shallow proofs including retries and USD30 to independent audit/rechecks. Codex
usage is separate. Resolved decision fingerprint:
`f34adad2c5688edf55059ed1cc9f8b5ed85e2f96233b063989dabed4487c04c5`.
Before paid calls, enforce the approved ceiling using per-request reserves,
including outstanding calls; a low observed historical bill is not a bound.
Saved CLI models are OpenRouter `openai/gpt-6.1-terra-pro` for both roles; saved
depth is 5. Proofs use explicit depth 1 without changing saved preferences.
Earlier shared-valuation proof costs used DeepSeek and are not comparable.

## First-slice runtime acceptance and next milestone

Live proof 1 on `34c1c44` completed with exit 0 and 17 model calls. Revenue
(`321 million`, including its source bullet) and AI Customer ARR (`376 million`)
were accepted. Both first debate turns used the accepted figures and distinguished
the AI-customer definition from pure AI-product revenue. Saved state, canonical
rating, memory, Markdown, HTML and machine evidence were inspected. Original
launcher preferences matched their pre-run hash.

One presentation defect was found: rejected-disclosure warnings still repeated
the source hash in the saved decision. A failing regression was added, then
`6a4e54a` replaced those occurrences with the existing source labels while
retaining warning reasons/locators and the exact machine evidence. The affected
56-test selection passed; full Ruff passed. Using the existing bare-graph test
setup, the actual saved live state was replayed through `record_decision`, required
state/memory writes and report export into a new isolated directory with zero
model calls. All replay checks passed and original artifacts remain untouched.
The live source manifest confirms that only this presentation helper and its test
changed. This is explicit evidence reuse across revisions, not a new live analysis
on the later commit. See `2026-11-04-docn-first-slice-evidence.json` for hashes,
checks, source revisions and exact artifact paths.

The browser tool rejected local `file:` navigation. Actual saved HTML structure
and text were inspected directly without page execution; no visual screenshot
inspection is claimed. Existing HTML rendering tests passed.

**First A slice accepted; early C is next.** Guidance/EBITDA and other extraction
rejections remain for the rest of A. Shared scenarios were unavailable in this
run, so it does not establish Build B valuation acceptance. One of seven live
attempts has been used. All 17 requests reported usage; the conservative
maximum-rate usage total is USD 2.3436025 (not an independently retrieved bill).
The USD30 audit allocation is untouched.

Final independent audit, full build acceptance, remaining A/B/C implementation
and their required runtime proofs remain outstanding.

## Early C groundwork: outcome provenance and invocation identity

Added `fetch_outcome` alongside the compatible `fetch_returns` interface. A
resolved outcome retains instrument and benchmark entry/exit dates and prices,
return arithmetic, source, explicit split/dividend adjustment policy and the
session-based entry policy. Benchmark observations keep their actual dates when
calendars differ. Daily bars are explicitly not execution timestamps. Yahoo
requests now specify `auto_adjust=True` instead of relying on its default.

Initial graph state now assigns a UUID per invocation; the state schema retains
it across a real SQLite checkpoint close/reopen/resume. The checkpoint signature
is versioned so older checkpoints cannot skip the new publication contract.

Red checks observed: six missing-outcome behavior failures, then a missing-run-ID
failure. After implementation, the focused selection passed **171 tests**:
`test_publication_run_identity`, `test_checkpoint_lifecycle`,
`test_checkpoint_resume`, `test_graph_end_to_end`,
`test_settlement_provenance`, `test_memory_log`, `test_memory_pointintime`, and
`test_backtest`. Ruff on changed files and `git diff --check` passed. One existing
price-history fixture was updated to require the explicit adjustment argument;
its original longer-window assertion remains intact. An additional 45 Yahoo
rate-limit, date-boundary and stale-price tests passed.

This is groundwork, not early C acceptance: immutable record integration,
independent endpoint persistence, publication/restart/real settlement proof and
later final C requirements remain outstanding. No paid calls were made for this
step; proof budget usage is unchanged.

The immutable storage module is now implemented with hash-checked evidence
snapshots, stable first-publication timestamps, linked revisions and one primary
eligible observation per ticker/date. Tests cover concurrent writers, interrupted
writes/retry, changed-content reuse of an ID, corruption, REVIEW exclusion and
local-date/UTC rollover. It is not yet wired into the graph publication path.

Settlement's structured price result now accepts actual publication time and
uses the instrument's bar timezone to select the first close strictly after both
the requested as-of and publication session. Missing timezone fails visibly;
naive publication times are rejected. A reproduced infinite-price defect was
fixed so nonfinite bars cannot create infinite returns. The latest combined
publication/storage, checkpoint, graph, settlement, memory, backtest and report
selection passed **200 tests**; changed-file Ruff and diff checks passed.

A real, unpaid Yahoo retrieval confirms the legacy October 19 DOCN window is
available: entry October 20 at 99.4800033569336, exit October 27 at
106.38999938964844; raw return 0.06946115600661797 and SPY-relative return
0.0686679886426693. Exact benchmark prices and retrieval time are retained in
`results/docn-abc/early-c/legacy-price-availability.json`. The existing legacy
memory records the same window rounded to +6.9%. Publication time remains
unknown. This is price-availability evidence, not the still-required integrated
publication/restart/settlement proof or prospective performance evidence.

## Early C graph and settlement integration

`record_decision` now writes the immutable record before state/memory projections;
its state log retains the decision ID, first-publication timestamp and record
hash. Invocation settings and installed source/prompt fingerprints are captured
at initialization and retained across checkpoints. Programmatic legacy states
receive an ID and publication time only when actually published now. Markdown
and HTML distinguish first publication from export generation, and repeated
exports preserve identity.

The existing graph settlement entry points scan publication records independently
of pending prompt memory. Each endpoint persists atomically in a separate,
hash-checked companion linked to its publication and thesis version. Resolved
endpoints are retained without fetching again; later horizons remain pending.
No model calls are added for these outcomes. The existing single reflection
uses a new publication's resolved window and predeclared benchmark, while old
memory without a publication continues through the compatible legacy path.
Current or future exchange daily bars are excluded when settling new records;
the host-date cutoff cannot admit a still-open session in a behind-host exchange.

Observed red tests covered missing durable publication after a projection failure,
missing publication identity in exports, and unfinished/future price visibility.
The endpoint module also tests concurrent writers, interrupted writes, per-window
provider failures, corruption and settlement after prompt memory becomes empty.
The first full suite exposed five bare-graph fixtures without results/config or
selected analysts. Those fixtures now supply normal persistence prerequisites;
all original authority and memory assertions remain. The corrected full offline
suite passed **1,904 tests, 100 subtests**, with one optional `langchain_aws` skip
and one external-service deselection (20 warnings), in 13.57 seconds. Logs:
`results/docn-abc/early-c/pytest-integration.log` (initial failures) and
`results/docn-abc/early-c/pytest-integration-corrected.log` (passing run).
Full Ruff, pip dependency check and diff checks passed.

Early C is not accepted yet. Visible horizon summaries, explicit legacy import
without fabricated publication metadata, and the required real CLI publication /
process restart / historical settlement proof remain. No additional paid calls
were made; one of seven live attempts remains used.

## Early C visible horizons, legacy runtime and focused review

Added known-at outcome tables to graph context, saved state and Markdown/HTML.
Pending and ineligible observations remain blank; revisions are excluded from
independent sample counts. Security, benchmark and excess returns are distinct,
and 63 sessions is explicitly not three calendar months. Prompt/report history
is bounded to ten publications with omission counts; the read-only summary API
can show all publications. Historical cutoffs exclude later publications/imports
and outcomes not yet recorded. The original rounded legacy returns never become
measured price results.

Explicit legacy import preserves the actual recorded rating/decision and source
file hash while leaving publication time, original code/config and original
benchmark provenance unknown. Import time is separate. The real October 19 DOCN
entry was copied verbatim into isolated memory and imported, then a **fresh
process constructed TradingAgentsGraph normally and called settle_all_pending**
with real Yahoo prices. All paid HTTP requests were blocked. Five sessions
resolved; 21 and 63 remained pending. Another fresh-process settlement produced
no duplicate outcome and identical publication/outcome objects. Copied memory
and the already-recorded reflection remained unchanged. Receipts are in
`results/docn-abc/early-c-settlement/{prepare,settlement,settlement-repeat}.json`;
the reproducible command is `docs/reviews/docn-abc-proof-tools/settlement_proof.py`
with `prepare`, then `settle` in separate invocations. Original memory was read
only. This is legacy runtime evidence, not prospective investment performance.
The initial proof predates the following reviewed corrections; the preserved
legacy settlement path is unaffected. A new live CLI publication is still due.

New memory entries retain exact publication IDs through settlement. Legacy
entries stay unlinked rather than being guessed onto a same-date revision.
A focused independent engineering review confirmed two material issues:

- Publication mode inferred from completion date could turn a midnight-crossing
  live run into a simulation (and a today-dated simulation into prospective).
  Fixed with explicit invocation mode retained in state/checkpoints; ordinary
  publication respects actual publication time even for an earlier requested
  as-of date, and the backtest path explicitly selects historical simulation.
- Projection scheduling could let a later same-day revision reach memory first.
  Fixed by projecting the authoritative first primary record; later revisions
  may repair its missing projection, with bounded-excerpt labeling if necessary.

Both fixes had observed failing regression tests. The independent reviewer then
reproduced the original concurrency probe, verified both mode cases, and ran
53 focused tests: both findings closed, no further material blocker identified
within this focused scope. This review does not replace the final completed-build
audit or remaining recovery/live gates. The final offline suite after these
fixes passed **1,915 tests and 100 subtests**, one optional dependency skip, one
external-service deselection, 20 warnings, 13.92 seconds. Log:
`results/docn-abc/early-c/pytest-review-fixes.log`. Full Ruff and diff checks passed;
pip check passed earlier with unchanged dependencies. No additional paid calls
have run yet; live proof 2 is next within the approved budget.

## Early C runtime acceptance

Live proof 2 completed on `ea1caff` with 17 model requests and successful report
saving. The actual CLI produced prospective Underweight publication
`9b939daf-b362-49ce-a1f4-5312f0c15a80` at
`2026-11-05T03:29:35.203435+00:00`. A fresh process constructed the real graph,
blocked paid HTTP calls, loaded the immutable record/evidence, and exercised
`settle_all_pending()`: no premature outcome or reflection, all 5/21/63-session
endpoints pending, and memory unchanged. Decision ID/rating/time match the saved
state, memory and Markdown/HTML; installed source fingerprints match the record.
Actual HTML structure/text was inspected without claiming a browser screenshot.

Together with the real legacy settlement/repeat proof, this accepts the early C
slice. The immutable publication/outcome paths are operating; future performance
remains pending. Exact source, artifact hashes, exclusions and evidence-reuse
limits are in `2026-11-04-docn-early-c-evidence.json`. Two of seven live attempts
are used. Cumulative maximum-rate usage is USD4.635765, not an independently
retrieved provider bill. Original launcher preferences are unchanged. The USD30
audit allocation remains untouched. Remaining A, B, final C and the final
connected completed-build audit remain required.

## Remaining A implementation in progress

The news analyst now retains bounded coverage from its actual private tool
results, distinguishing failed requests, successful empty news windows and
available responses. The evidence gate separately records independent news,
issuer-event, consensus and optional macro coverage. For unavailable/empty news,
it exposes eligible already-retrieved 8-K metadata as an **Issuer disclosures**
supplement, retaining URL/hash/filing date and leaving the original news prose
unchanged. Whole documents are not called verified, and no vendor or model call
was added. News coverage survives the analyst subgraph output boundary; the
checkpoint signature advances for the changed post-analyst contract.

Observed initial missing-behavior tests failed, then the issuer-event, evidence,
news, routing and full-graph selection passed **91 tests** in the current working
candidate. Changed-file Ruff passed. These are focused implementation checks,
not the final Build A gate. Disclosure extraction, prior-quarter source/KPI and
cash-bridge work is being integrated separately; the final full suite, actual
report proof, second-issuer gate coverage and independent Build A review remain.
