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
