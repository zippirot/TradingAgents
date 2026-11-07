# Executive summary and table of contents implementation plan

Date: 2026-11-06
Completed locally 2026-11-07; no release action taken. The implementation record is [report executive summary acceptance](../../reviews/2026-11-06-report-executive-summary-acceptance.md).
Independent audit: required

## Outcome

Every newly completed report opens with the title and analysis date, an executive summary, a visible table of contents, and then the existing report. The summary first explains how that particular report was produced, then explains the final decision and its principal inputs in 5–12 sentences. The rating is immediately defined in plain language. HTML and Markdown show the same summary.

The full research remains available with its substance preserved, but the final portfolio decision moves ahead of the analyst reports in both the contents and the report body. This changes reading order only; analysis and decision-making still execute in their existing order.

## Delivery estimate

- Build size: **medium**.
- Recommended implementation model: **GPT-6 Sol (`gpt-6-sol`)**.
- Recommended reasoning effort: **medium**.
- Estimated active build, verification, independent audit, and gap closure total **8–14 hours**. This allows 6–10 hours for implementation and initial verification plus roughly 2–4 hours for review, a bounded correction pass, and follow-up. The range assumes the existing clients, fixtures, and renderers work and the audit finds no extensive rework. It excludes external waits.
- Codex credits: not credibly estimable from the available workload measurements; API token prices do not establish Codex credit consumption.
- Rationale: the presentation work is bounded, but summary fidelity, publication immutability, and common CLI/API finalization require substantive engineering judgment and integrated tests. These contracts are inspectable and testable; Astra is not required by the present scope.
- This follows the user's explicit GPT-6 Sol policy. Current [official Codex model guidance](https://developers.openai.com/codex/models) also discusses newer GPT-6.1 models; this plan does not silently substitute one or change app defaults. Model availability must be checked when starting implementation.
- Runtime cost: one additional bounded editorial request using the report's already configured deep-thinking client on an eligible new run. Re-exporting does not invoke a model. Exact latency and provider cost remain unmeasured; there is no new provider, credential, or model-setting UI.

## Grounding and execution boundary

Inspected repository: `/Users/zipp/Documents/ChatGPT/Tauric/TradingAgents`, branch `codex/installed-staging-89aae49-with-pins`, commit `e48207008874e05680d3fa28357682834f52e38f`. The November 6 DOCN example is `y/complete_report.md` and `y/complete_report.html`, approximately 47,000 words. It ends with an Underweight rating, limited evidence coverage, and no supported final price target.

The checkout has existing untracked `y/` output and a branding plan; preserve both. Paths below are relative to this repository root. This planning task writes only this document. For implementation, use the existing isolated implementation worktree if supplied, otherwise create an isolated `codex/` branch from the agreed integration baseline and reconcile its source with these observations. Do not modify the installed launcher checkout to implement the feature. Recheck applicable machine and repository instructions at execution time; machine restrictions in older feature plans are not automatically a new authorization to access another machine.

Completion requires a verified candidate committed on the isolated branch, the independent build audit and verified gap closure in Task 6, synchronized acceptance evidence, and a clean task diff. Push, pull request, merge, installation, deployment, and worktree removal require separate authority.

## Existing mechanisms to reuse

- `tradingagents/reporting.py`: `prepare_report_state`, `_report_parts`, `evidence_appendix`, and `write_report_tree` already construct the readable report and both export formats.
- `tradingagents/report_html.py`: `render_report` builds section anchors and a contents rail. That rail is collapsed on wide screens and hidden in print; it does not satisfy the requested visible outline.
- `tradingagents/graph/trading_graph.py`: both `propagate` and the CLI converge on `record_decision`; `save_reports` delegates to the shared report writer. `_log_state` explicitly allowlists retained state fields.
- `cli/run.py`: calls `record_decision` after streaming, then `save_reports`. Avoid a second CLI-specific generation path.
- `tradingagents/agents/rating.py`: `run_rating` is the authoritative rating accessor; `REVIEW` must remain a non-tradeable result.
- `tradingagents/agents/audit_pass.py`: established structured-output/provider-error handling patterns can be reused without extending the advisory audit itself.
- `tradingagents/memory/publication.py`: immutable publication and evidence records are authoritative. Rendering and state logs are projections.

## Reader-facing contract

### Opening order

1. Existing branding, company/ticker, and analysis date.
2. **Executive summary** containing the two paragraphs described below.
3. **Table of contents**, visible without hovering, clicking, or expanding controls.
4. Existing report metadata and advisory conditions, followed by the full report in the decision-first order specified below.

Keep metadata, publication identity, and existing advisory disclosures accessible after the contents. Do not let their current volume precede the new summary. The title may retain its rating badge; the first decision sentence must still define that rating.

### Process paragraph

Use 2–3 short sentences, normally 50–90 words, generated deterministically from retained settings, completed sections, and available execution/evidence status. Describe participating analysts, actual available source categories, research debate, trading proposal, risk debate, evidence checks, and final portfolio decision as applicable.

Do not claim that a configured vendor returned data, a selected analyst completed, or a configured debate limit was the actual number of rounds. Use observed completion/retrieval information where available; otherwise use accurate wording such as “configured for up to three rounds” or omit the count. Explain abbreviated REVIEW runs accurately: skipped debates and portfolio decisions did not occur. Omit missing model/vendor names instead of printing placeholders. The paragraph can mention evidence checks without claiming that all narrative conclusions were validated.

### Decision paragraph

- Exactly **5–12 sentences**, excluding the process paragraph and labels. Aim for 8–10 sentences on a full report and avoid padding a short report.
- First sentence: canonical rating plus its plain-language meaning, assembled from `run_rating` and a shared definition map.
- Remaining sentences explain the main conclusion and key contributions from market, sentiment, news, fundamentals, bull/bear research and its adjudication, trading, risk, valuation, and evidence quality. Combine related contributions to stay within the sentence limit.
- Include the final rationale, material disagreement, horizon when present, and the most consequential uncertainty. A full run must not summarize only the portfolio manager's text.
- Last sentence provides an accurate concise evidence/target limitation from the prepared decision context. It must distinguish conditional scenario values from a supported final price target.
- Attribute interpretation to the report or analysts. Management guidance remains forward-looking; vendor estimates remain unverified where labeled. Do not turn proposed execution levels, stops, or allocation percentages into validated instructions.
- Preserve the configured output language using existing language handling; do not introduce a translation service. Rating tokens remain canonical. English is the primary acceptance fixture, with a non-English fixture for sentence handling and definitions.

Rating definitions must match existing semantics: Buy = favors entering or adding; Overweight = favors increasing exposure above a normal allocation; Hold = maintain exposure; Underweight = reduce exposure toward a lower-than-normal allocation; Sell = exit or avoid entry. Do not imply a known numerical benchmark, guaranteed return, profit on existing holdings, or automatic short sale. REVIEW = no actionable rating established, with the reason when available. Define a rating whenever the summary introduces it; avoid repeating competing rating labels unnecessarily.

### Contents

List the actual emitted sections with a short description and their agent/subsection entries. Use this same order in the full report body, in HTML and Markdown:

1. Final portfolio decision — rating, rationale, valuation, scenarios, and reconsideration conditions; include the existing mechanical sensitivity material.
2. Analyst reports — market, sentiment, news, and fundamentals.
3. Research decision — bull case, bear case, and research manager's conclusion.
4. Trading plan — proposed action, timing, and exposure considerations.
5. Risk assessment — aggressive, conservative, and neutral perspectives.
6. Evidence and quality — checks, calculations, references, limitations.

Derive entries from one shared ordered report section model; do not hardcode links to absent agents. Display consecutive section numbering in this reading order (I–VI for a full report), without an empty entry or a duplicated portfolio decision. Preserve existing HTML section IDs by section identity rather than recalculating them from the new display position. Add explicit stable Markdown anchors to avoid collisions from model-generated headings. Keep the existing per-agent folder/file names unchanged. The existing HTML rail may remain as secondary navigation, in the same new order, but the new in-flow contents must also be visible on desktop, narrow screens, and print. For partial reports, retain the relative order of present sections and omit absent ones.

## Implementation approach

Add one small `tradingagents/report_summary.py` module for the summary contract, input preparation, deterministic framing, generation, validation, and rendering. Keep the existing report writer and HTML renderer responsible for assembling their respective formats.

Use the shared `record_decision` completion path after publication validation/creation and outcome-summary preparation, before `_log_state`. Construct summary input from the same prepared presentation used by exports. The report is logically complete at this point; it need not be written to disk and read back. Generate the editorial text using the existing deep-thinking client, then attach a presentation-only `executive_summary` field. Do not change graph routing or add a node solely for this feature.

Keep this field out of `evidence_snapshot`, canonical publication hashes, thesis records, trading memory, and evaluation. Persist it through `_log_state` and export a small `executive_summary.json` companion alongside the report. It contains a schema version, status, source-input digest, process text, decision sentences, generation model, and bounded failure/coverage information. It contains no credentials, endpoint URLs, or duplicated raw financial packages.

Build the source-input digest from stable summary-relevant prepared content, rating, constraints, and retained settings, excluding timestamps, generated summary fields, output paths, and incidental export notes. This is a stale-summary check, not a new source-of-truth system. The same builder must be used for generation and export validation. Avoid cyclic imports between the summary helper and report preparation by passing prepared sections/context into the helper.

Generation uses one structured response containing 3–10 body sentences, each associated with known input section keys. Code adds the rating-definition sentence and the evidence-limit sentence to produce 5–12 total. Validate structure, nonempty text, sentence boundaries, overall brevity, section coverage, and recognized section references. Counting list items alone is not proof of sentence count; handle decimal values and common abbreviations in focused tests. Do not claim these mechanical checks establish semantic truth: source-by-source review of the representative output is also required.

Send section-aware bounded input. Preserve the final decision and evidence/target constraints, and include every present major section. Remove repeated generated evidence wrappers rather than dropping late report sections under a global character limit. Record material truncation, and instruct the model that omitted content is not proof of missing evidence. Do not add a chain of per-section summarizer calls, new tokenizer dependency, or configurable summarization framework. If necessary information cannot fit safely, use the explicit unavailable path.

Treat research text as untrusted input. The editorial request has no tools and cannot fetch sources, execute actions, or revise the decision. Reuse provider timeout/error handling and bounded response parsing. Do not add automatic model repair loops. Existing transport retries remain bounded; one logical summary request does not promise exactly one billable transport attempt.

## Ordered work

### Task 1: Establish the summary contract and grounded inputs

**Files:** new `tradingagents/report_summary.py`, `tradingagents/agents/rating.py` if needed for a shared definition helper, new `tests/test_report_summary.py`.

Implement deterministic process text, the rating-definition map, stable input construction, bounded section inputs, output validation, and unavailable/fallback representation. Read existing rating prompts before assigning definitions; do not change decision semantics.

Use a compact fixture representing the November 6 DOCN report, including distinct contributions from all sections, an Underweight final rating, a provisional Sell trader action, conditional valuation scenarios, limited evidence, and no supported target. Do not commit the private full run or its raw state.

**Verify:** all five ratings and REVIEW; missing analysts; partial settings; actual versus configured steps; current rating versus trader disagreement; no target versus scenario prices; multi-sentence response items; decimals/abbreviations; missing section coverage; malformed response; hostile input; input truncation; non-English handling. Tests should assert reader-visible behavior and boundary preservation, not exact prompt wording.

### Task 2: Generate once in the common finalization path and retain it

**Files:** `tradingagents/graph/trading_graph.py`, `tradingagents/agents/state.py` only if its declared state contract needs the optional field, summary module, `tests/test_publication_graph.py`, new summary integration tests. Inspect `cli/run.py`; change it only if a real integration gap is found.

Attach the summary after the final decision is validated and publication succeeds, before the state log is saved. Persist the field explicitly. Skip generation for an already retained matching result and for historical publication replays. On a retry after a projection failure, reuse an available matching retained result; if a crash occurred before persistence, do not claim exactly-once generation.

Do not call a model for insufficient-evidence REVIEW runs that currently bypass decision calls. Produce a concise deterministic explanation of the stopped run instead. Normal summary timeout, malformed output, or missing client must not erase or invalidate a completed research publication. Preserve the existing failure semantics for actual publication corruption or required state-log write failures.

Generation occurs after existing graph metrics have finalized. Record editorial status/elapsed time in the summary companion rather than changing evidence-bound run metrics after publication. Explain the distinction if showing total call counts.

**Verify:** mocked successful CLI/common completion and Python completion attach the same field; repeated saves perform no model calls; skipped REVIEW pipeline remains skipped; generation failure leaves decision, publication, evidence hashes, and memory unchanged; retained state survives save/load; projection retry and publication-integrity tests retain their behavior.

### Task 3: Prepend matching content to both exports

**Files:** `tradingagents/reporting.py`, `tradingagents/report_html.py`, summary module, `tests/test_reporting.py`, `tests/test_report_html.py`, `tests/test_report_presentation.py`.

Build shared front-matter content once per export from the prepared state. Render title/date, executive summary, visible contents, then existing metadata/disclosures and body. Reorder the presentation section model to final portfolio decision, analysts, research, trading, risk, evidence; derive the visible contents, optional rail, and actual body from that same order. Apply it consistently when direct `render_report` calls rebuild prepared parts. Do not change graph execution order, source state, or per-agent export paths. Pass the same summary to both formats. Keep render/save functions free of model and network calls. Persist the summary companion using the existing file-writing convention.

Use the existing sanitized Markdown rendering for summary text and escape metadata. Maintain the self-contained HTML policy: no scripts, trackers, fetched assets, or new dependencies. Adapt rail-specific CSS so it cannot collapse or hide the in-flow contents. Preserve section identities and all existing substantive body text and per-agent files.

**Verify:** opening order; identical decision-first section order in contents, rail, and body across HTML/Markdown; consecutive displayed numbering without empty or duplicate entries; 5–12 decision sentences in successful outputs; rating defined on first introduction; existing HTML anchors still resolve to their original section identities; omitted sections have no dead links; each section's substantive content and per-agent files match the pre-change baseline for the same input, allowing the intended heading and ordering changes; HTML opt-out still works; direct HTML calls work; markup-injection protection and content-security policy remain intact.

### Task 4: Handle older exports, stale summaries, and failures honestly

**Files:** summary module, report writers, `tests/test_report_evidence_integrity.py`, `tests/test_publication_records.py`, summary tests.

An older saved state without an editorial summary exports offline. Show deterministic process/rating/evidence context and a concise statement that the full narrative summary is unavailable for this saved run; then show the contents and intact report. Do not pad this failure/legacy fallback to pretend it satisfies the successful 5–12-sentence narrative contract.

If current presentation validation changes the final rating, target availability, or other digest inputs, do not display stale generated prose. Retain the saved summary record for traceability and render the same truthful fallback without a hidden regeneration call. A frozen evidence snapshot never gains a newly generated summary. Do not retroactively modify old saved reports in bulk.

**Verify:** legacy state; absent/malformed summary; stale rating/target/source digest; historical immutable publication re-export; a failed summary versus a corrupted publication (only the former is nonfatal); no network on all export routes; no mutation of caller input, original publication, evidence, or decision identity.

### Task 5: Prove the reading experience and commit the audit candidate

**Files:** relevant tests, a short README export-description update, and `docs/reviews/2026-11-06-report-executive-summary-acceptance.md` during implementation.

Render the representative report into a separate temporary output directory. Inspect desktop, narrow/mobile, and print views; verify that the process paragraph is first, the decision is readable, contents are visible, the final portfolio decision is the first full report section, links work, and long narrative/tables still fit. Compare summary text against every contributing section, especially the final adjudication and target limitation. Use a known reviewed fixture response for offline tests, clearly identifying it as a fixture rather than evidence of live generation quality.

If authorization and a cost limit are provided for a live editorial proof, run only the summarizer against the retained report using the existing configured client; a full market-data/research rerun is unnecessary. Record model, input scope, elapsed time, usage when available, output, and the source-comparison assessment. No paid model calls are authorized by the request to write this plan. Without that proof, report live provider behavior and real generated-summary quality as unverified; do not hide that limitation behind passing mocked tests.

Run focused tests first, followed by the local default suite and repository lint once the implementation is stable. The full local suite is warranted because finalization is shared with publication, memory, and checkpoint completion. Existing remote CI matrix/release gates still apply when separately authorized; a local Python run does not establish that matrix passed.

Suggested commands from the implementation repository root:

```sh
.venv/bin/python -m pytest -q tests/test_report_summary.py tests/test_reporting.py tests/test_report_html.py tests/test_report_presentation.py
.venv/bin/python -m pytest -q tests/test_publication_graph.py tests/test_publication_records.py tests/test_rating_integrity.py tests/test_report_evidence_integrity.py tests/test_stream_publication.py tests/test_checkpoint_lifecycle.py tests/test_checkpoint_resume.py
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
git diff --check
```

Add new integration test filenames to the focused invocation. Classify failures before rerunning expensive checks; preserve valid evidence and do not weaken existing assertions to accommodate changed layout. Update layout expectations only where this plan intentionally changes the opening.

Inspect the complete diff and commit the candidate and its acceptance evidence on the isolated branch. Record the base and candidate SHAs, checks, render artifacts, deviations, and limitations for the auditor. Keep private reports, credentials, temporary renders, and unrelated changes out of Git.

### Task 6: Independent build audit and gap-closure build

Run the independent audit and close confirmed material findings in this same worktree before reporting complete.

1. Give an independent Claude reviewer the governing plan, exact base and candidate commits, complete implementation diff, and relevant test and render evidence through the authorized audit route. Have the reviewer check the actual implementation against the acceptance criteria, especially summary fidelity, report order, publication integrity, and offline re-exports. The advisory audit inside the report pipeline has a separate purpose. Record reviewer identity, scope, limitations, findings, and reviewed SHA in the acceptance record. Honor existing access, data-sharing, and spending authority. If the required route is unavailable or needs additional authorization, identify the precise blocker and leave the audit outstanding.
2. Check each finding against source and observed behavior. Record the disposition and evidence. For every confirmed material in-scope gap, including the supported portion of a partially confirmed finding, implement the smallest complete correction in this worktree. Obtain missing proof when the gap is in the evidence. When no material gaps are confirmed, record that result without manufacturing a code change.
3. Commit the corrections, rerun affected tests and render checks, and repeat broader verification where the changes affect its validity. Have the independent reviewer verify material closures against the corrected commit. Resolve any remaining confirmed material gap before completion. Record audited and final SHAs, findings and dispositions, verification by revision, and residual limitations. Deliver a clean committed branch and the final acceptance record.

## Acceptance checklist

- [x] A successful new report starts with the requested process paragraph, 5–12-sentence decision narrative, visible contents, then the full report with the final portfolio decision first.
- [x] Contents and body share the order: final portfolio decision, analysts, research, trading, risk, evidence; section numbering is consecutive and links preserve their section targets in both formats.
- [x] The rating is canonical and immediately defined; all present major sections contribute to the summary.
- [x] Actual pipeline execution is described accurately, including skipped or incomplete steps.
- [x] Both formats reuse the retained summary; saving/re-exporting cannot trigger model calls.
- [x] Underweight versus provisional Sell, absent final target, conditional valuation, and limited evidence remain accurately distinguished.
- [x] The complete body, per-agent files, canonical decision, publication/evidence records, trading memory, and evaluation behavior remain substantively unchanged.
- [x] Legacy, failure, REVIEW, and stale-summary paths are explicit and preserve the usable report.
- [x] Desktop/mobile/print inspection, focused tests, default suite, lint, and diff inspection are recorded with their actual results.
- [x] Live generation quality is either demonstrated under separate authorization or explicitly reported as unverified.
- [x] An independent Claude build audit of the committed candidate is recorded. Every finding has an evidence-backed disposition, all confirmed material in-scope gaps are closed, and any material fixes have independent closure verification on the corrected revision.
- [x] Implementation changes and acceptance evidence are committed; release actions remain separate.

## Open decisions and exclusions

No further product decision is needed to implement this design once the plan is approved. The one optional operational decision is whether to authorize a bounded paid summarizer proof against the retained DOCN report; recommend it before installation to assess prose quality beyond mocks.

Excluded: changing ratings or research prompts, adding a new investment agent, fetching new evidence, changing portfolio authority, changing model defaults, redesigning the full report, adding new export formats, bulk backfilling historical summaries, and building generalized summarization/caching infrastructure.
