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

### Remaining A integrated evidence and review corrections

Deterministic disclosure discovery now uses the same strict validator as model
proposals. It retains complete qualifiers, separate exact period locators,
lower-bound growth without an invented ceiling, and NVIDIA's fiscal-period
central estimate with its stated tolerance and China exclusion. Non-exact
outlooks cannot become exact finite valuation inputs. Fifteen source-backed
DOCN records survive the recorded-source replay; rejected model records remain
rejected independently.

The actual live-02 multi-document package exposed the 128-cell discovery cap:
old annual/release material exhausted it before current 10-Q cash rows. Current
primary filings now receive priority, with the same cap and an explicit omitted
row warning. The actual saved companyfacts inputs and filing package, reprocessed
without network/model calls, reproduce all five required cash examples:
−381.974m investing, 153.818m after capex/principal, 149.022m after acquisitions,
411.619m cash change, and 666.252m cash plus restricted cash. Gross financed
investment remains separate and no residual becomes capex.

Exact compatible quarter facts now produce 39.87% revenue YoY, 10.28% operating
margin and −13.27% net margin (rounded presentation; exact decimals/lineage in
state). Bounded real SEC retrieval verifies RPO 893.828m at June 30 to 799.707m
at September 30: derived −94.121m/−10.53%. Source currency, recognition scope,
inline fact/context/unit spans and filing provenance are retained. The comparison
makes no causal or demand claim. Missing bounded excerpts do not establish
company nondisclosure. Receipts and replay inputs are under
`results/docn-abc/a-prior-source/rpo-comparison.json` and
`results/docn-abc/a-evidence-replay/`; executable replay is
`docn-abc-proof-tools/replay_a_evidence.py`.

Independent Build A review identified malformed deterministic proposals raising
before per-record rejection. Two regression tests first reproduced the failure;
construction is now bounded and tolerant per record, followed by unchanged strict
validation. Independent recheck passed 149 focused tests and a two-malformed-range
probe retained 13 other valid records. Reviewer found no additional material
issue in the integrated cash, RPO, operating metrics or issuer fallback paths.

The required second-issuer source proof exposed a pre-existing companyfacts bug:
NVIDIA's 2009 and Microsoft's 2016 ambiguous records aborted the current package
before the existing twelve-quarter/five-year bound was applied. Window discovery
now precedes value resolution, preserving strict rejection inside the window and
the default unbounded selector's behavior. Independent review passed 77 tests and
a 200-case differential probe against the original selector. Actual cached SEC
replays now produce NVIDIA 797 facts and Microsoft 891 facts. NVIDIA's full gate
then revealed a separate split exhibit-link layout; that narrow source-selection
fix and its proof are still pending here. No missing accounting coverage is being
converted to a passing actionable decision.

These checks establish implementation progress, not final Build A acceptance.
Final full-suite, actual complete source-gate/report/live proof and synchronized
candidate evidence remain required. No additional paid calls occurred in this
work; live attempts remain 2/7 and the prior spending receipt is unchanged.

### Build A offline candidate gate

The NVIDIA split-link fix is complete and independently reviewed: 75 focused
checks passed, preserving item-2.02 qualification, same-accession URL restrictions,
deduplication and the two-exhibit limit. A normal provider/evidence-gate source
proof now retrieves six NVIDIA documents and accepts its actual fiscal-quarter
108.0bn central estimate with ±2% tolerance and the China exclusion. Its missing
accounting/claim coverage remains REVIEW, as intended; this is source/gate coverage,
not a successful actionable NVIDIA research run. No model calls were used.
Receipt: `results/docn-abc/a-second-issuer-nvda/gate-result.json`.

Full offline candidate gate: **2,001 passed, 100 subtests passed**, one optional
`langchain_aws` skip, one configured external-service deselection, 20 warnings,
16.08 seconds. Full Ruff, dependency and diff checks passed. Initial full run had
2,000 passes and one obsolete expected checkpoint-version assertion; the fixture
now expects evidence version 3 and checks that version 2 yields a different
checkpoint identity. Eight focused recovery checks passed before the required
complete rerun. Both full-run logs are in `results/docn-abc/a-final-offline/`.

Current recorded-source context measures 33,930 characters including exact
references, 16,461 readable characters and 17,099 reference-appendix characters.
This exceeds the first slice's smaller coverage because it now includes fifteen
qualified disclosures, cash reconciliations, operating comparisons and RPO.
References remain separately rendered and narrative remains independently bounded;
this is not a claimed token/cost reduction versus the first slice.

All confirmed material Build A review findings are closed. Final authorized
Shallow live proof 3, actual first-debate/report/persistence inspection and Build A
acceptance evidence remain next; A is not yet accepted by these offline checks.

## Build A runtime acceptance

Shallow live proof 3 completed on `9022e47152329bf642d990ceb032b27ef0b9b2aa`
with 17 model requests. It published limited-evidence Underweight decision
`60e36cd4-21bb-4472-9309-e8827228b26d` at
`2026-11-05T04:07:17.629658+00:00`, saved Markdown/HTML/evidence/quality and
persisted the matching memory/publication. Both first debate speakers used the
149.0m cash measure, 893.8m→799.7m RPO decline and 60%-plus management outlook,
retaining the relevant caveats. All five exact cash checks, fifteen disclosures
and the exact RPO comparison match state and immutable evidence. Reports contain
one reference appendix; their HTML structure/text was inspected without claiming
a browser screenshot.

Fresh real-graph construction with paid HTTP blocked verified source fingerprints,
ID/rating/time/evidence consistency and repeat-safe pending settlement; memory
remained unchanged and all 5/21/63 endpoints remain pending. The acceptance script
is `docn-abc-proof-tools/verify_build_a.py`; durable summarized hashes/results are
in `2026-11-04-docn-build-a-evidence.json`.

Live independent news was available, issuer accepted values were retained, and
optional FRED coverage remained unavailable. The outage branch is covered by
focused fault-injection/source tests, not claimed as an observed live news outage.
Shared scenarios and the final target were unavailable, which remains Build B
work. No prospective investment performance is claimed.

This accepts Build A together with its required review, full suite, recorded
reproduction and second-issuer source/gate coverage. Three of seven live attempts
are used; cumulative maximum-rate usage is USD7.324695 (not an independently
retrieved provider bill); original preferences are unchanged. Build B, final C
and the final connected audit remain outstanding.

### Build B reviewed offline candidate (live acceptance still pending)

Implemented advisory thesis versions in the existing immutable publication snapshot,
with exact-source observations, explicit kept/overridden/retired dispositions and
reasons. Gross Margin is a deterministic Gross Profit / Revenue observation; the
October 19 53% text remains an advisory legacy narrative with unestablished authority.
No automatic rule enforcement or authorization UI was added. Invalid optional
thesis proposals preserve the canonical rating; retired/kept lifecycle conflicts
were corrected and independently rechecked.

The shared/final valuation calculator now supports explicit forward cash, debt,
lease, equity issuance and dilution bridges per scenario. Unfunded cases retain
cash-gap diagnostics but publish no target or return. Weights require rationale;
multiple dates and optional decision-date/rerating assumptions distinguish dated
conditional values from annual sensitivities. Replayed price comparisons use each
scenario's capital and show implied multiple/revenue without calling them expected
returns. Source-basis checks reject intervening splits, including an incomplete
current session and later splits contaminating historical Yahoo closes.

The existing financial-evidence tool now exposes the same strict filing-table
Total Borrowings fact that was previously available only after the analyst finished.
Actual saved DOCN evidence replay retained the exact $461.630m fact/source IDs in
63,816 characters, within the unchanged 64KB tool limit. No additional model call
was introduced. Current model prompts require an explicit scenario fence, allowing
an empty list when a defensible calculation is unavailable.

The decision card separates the canonical PM rating from the provisional Trader
proposal and labels risk-based opinions without a supported valuation. Independent
review caught raw debate and free-form horizon text leaking numeric targets/sizing
into this card: the card now retains diagnostic references rather than duplicate
quotes, and accepts only whole-value dates/durations for a stated horizon. Existing
publication authority tests were preserved. Both findings were independently closed.

Event comparison uses source-compatible pre-event guidance when available and
existing configured Yahoo prices on aligned completed sessions. Consensus remains
explicitly unavailable because there is no typed timestamped consensus source;
no paid source or key was added. DOCN's disclosed peer AKAM is selected before
returns, with SPY as broad benchmark. Intraday release time is unknown: these are
filing-date windows, not causal attribution. Independent review found that a filing
CIK could be paired with another ticker; the existing SEC-map gate identity now
binds ticker/CIK/cutoff before either event or valuation price comparisons. A direct
DOCN-evidence/AAPL-ticker probe now fails before any quote fetch. Legacy records
without this binding retain arithmetic but cannot claim a new price comparison.

Required offline gate: **2,170 passed, 100 subtests passed**, one optional
`langchain_aws` skip, one configured integration deselection, 20 existing model
warnings; 16.43 seconds. Full Ruff, pip dependency check and diff check passed.
The initial full run had 2,161 passes and one prompt wording regression after
trimming redundant instructions; the original Hold/conflict rule was restored,
55 affected checks passed, then the complete reviewed candidate passed. Logs are
`results/docn-abc/b-offline/pytest-candidate.log` and
`results/docn-abc/b-offline/pytest-reviewed-candidate.log`.

Independent targeted reviews closed funding/date/weight, historical/current-session
split, thesis lifecycle, card-authority and issuer-binding findings. Final binding
verification ran 100 focused/integrated tests. Earlier unaffected passing checks
were retained; this does not replace the completed full candidate run or final
connected exact-base/head audit.

A real, non-LLM Yahoo probe returned DOCN's November 4 completed close at
84.0199966430664 USD (about $84.02), with verified coverage from September 23;
saved-source replay matched. A fresh SEC-map-bound event probe using the real
saved A filing package and current provider data measured November 2–4 moves:
DOCN approximately -6.43%, SPY +1.96%, AKAM -0.88%. Guidance comparison and consensus
were unavailable and remained labeled. Receipts live under
`results/docn-abc/b-price-probe/` (`event_comparison-bound.json` is the post-review
issuer-bound receipt). These source probes do not replace the required real CLI
B proof or second-process thesis-continuity proof.

No additional paid attempt has run: three of seven used, conservative token-rate
usage $7.324695 of the $70 proof allocation; $30 audit allocation untouched.
Build B is **not yet accepted**. Next: commit this candidate, run live-04 at the
approved Shallow settings, inspect reports/state/memory and prove persisted thesis
continuity in a second real process before moving to final C.

### Build B first real CLI proof and fresh-process readback

Paid attempt `live-04` completed on application commit
`ee7174f091e858b9ca2ceca51bbc0f6977fb8591`: 17 model requests, unchanged saved CLI
preferences, approved Shallow settings. Conservative cumulative token-rate usage
is **$10.2494125** across four attempts; the separate audit allocation is untouched.
The canonical rating is Underweight with limited evidence. Three early EV/revenue
scenarios passed validation and all three have available dated price/reverse
comparisons. The PM supplied no final structured valuation request, so final target
omission remains explicit and does not erase the supported conditional table.

Publication `54e3a2d3-4f5a-49e1-a999-461ad8970838` links thesis version
`282f78f4-c085-5a2a-9e99-25d830044b77`. Two advisory conditions refer to Q4 2026:
Gross Margin >=55.5% and Revenue >=348m USD. They remain unknown until compatible
Q4 evidence exists; no current measurement or automatic trading rule is invented.
The actual settled October 19 memory was copied unchanged into this isolated run,
with its source hash recorded in `live-04/seed-memory.json`.

`verify_build_b.py --run-name live-04` ran in a fresh process with paid HTTP blocked.
It verified runtime source hashes, publication/evidence/report agreement, all three
supported comparisons, condition/version persistence, current pending endpoints,
and unchanged memory. The real graph's memory step retrieved the same thesis
version and conditions. Markdown and parsed HTML contain the decision card,
conditional comparison and continuity display. Receipt:
`results/docn-abc/live-04/build-b-readback.json`; no browser screenshot was taken.

B remains pending its next-CLI condition/disposition proof. For `live-05`, the exact
immutable publication/evidence and memory were copied into a fresh isolated runtime,
with no changed timestamps and no reused checkpoint. `seed-continuity.json` hashes
all copied files. This is a real persisted prior decision, not a synthesized fixture.

### Build B second CLI: continuity finding and correction candidate

`live-05` completed on documentation-only commit
`9cd33dd368d73c0700d53de720cb43d78fa4397d`, with application/test source hashes
identical to live-04. It read thesis `282f78f4-c085-5a2a-9e99-25d830044b77` and
published child `7c94e1e7-02fc-566c-ad04-a10d3307d57b` in decision
`a11c8098-dfa2-44dd-8a4f-58c998780bd7`. Both prior Q4 conditions were explicitly
unknown and kept, with reasons. The daily publication is a revision, not another
primary sample; memory correctly retains the first daily publication link.

The model intentionally emitted a valid empty scenario list, explaining uncertain
future funding/full lease perimeter and a weak normalized EPS baseline. This is
not a parser failure. The generic readback script initially failed its extra
valuation assertion; the separate continuity verifier retains live-04's supported
valuation evidence only after proving identical application hashes and unchanged
prior artifacts. No paid valuation retry was launched. The empty-list diagnostic
now explicitly says no scenarios were proposed, separately from malformed inputs.

Independent artifact review found a material flaw despite successful version
readback: rewording a condition's rationale changed its ID, leaving four active
entries for two measurement contracts. The correction defines identity by the
measurement/period/comparator/threshold/unit/basis/expiry, with exact Decimal
normalization and no rationale hashing. New versions reuse prior IDs; equivalent
legacy duplicates coalesce with bounded aliases. Conflicting alias dispositions
preserve the condition with visible warnings/reasons. Published same-run thesis
projections remain frozen; the original live-04/live-05 records are not rewritten.

The correction candidate passed the required full suite: **2,179 passed, 100
subtests passed**, one optional dependency skip, one integration deselection,
20 existing warnings, 18.21 seconds. Ruff and diff checks passed. Log:
`results/docn-abc/b-offline/pytest-continuity-fix.log`. Independent targeted review
and real saved-input persistence replay are the remaining acceptance checks for
this correction. `recover_build_b_thesis.py` will run the actual live-05 proposal
through the graph's real publication/report path in an isolated historical
engineering replay, with all HTTP/model calls blocked. It is not another live
model decision and must not be counted as prospective investment evidence.

Live-05 used 17 model requests and $2.7035875 at the conservative token-rate caps.
Five paid proofs have used **$12.953** cumulatively; two of seven attempts remain.
The audit allocation remains unspent. No saved model/depth preferences changed.

### Build B acceptance

The correction is committed as `a10b7d2` (full SHA retained by the recovery
receipt). `recover_build_b_thesis.py` passed through actual graph publication,
report/evidence writing, repeat publication and second-graph readback. The new
historical engineering record `62d642a2-13a1-48c5-b15d-fcd128f443a8` contains two
conditions under the original IDs and preserves legacy duplicate IDs as aliases.
All original live-04/live-05 publication/evidence/state/memory hashes are unchanged.
The original buggy version remains an immutable historical observation; it was
not relabeled as a clean run. This proof made zero model or network calls.

Independent verification reran 89 focused tests, directly checked original B4/B5
same-run projections and new-version coalescing, loaded the recovery publication
and evidence through integrity checks, and independently rehashed all eight
protected original files. The semantic-identity finding is closed. Receipt:
`results/docn-abc/b-thesis-recovery/acceptance.json`.

**B accepted:** real CLI valuation proof (live-04), real next-CLI disposition proof
(live-05), targeted actual-input persistence recovery, the final 2,179-test suite,
and independent material-fix verification together establish the build boundary.
The accepted evidence is intentionally across stated revisions, not one invented
all-passing live run. No completed forward-funding model scenario was produced;
that arithmetic and its full report path have focused deterministic tests and
independent review. Final target/scenario omissions remain permitted and explicit.
Final C and the connected final exact-base/head audit remain outstanding.
