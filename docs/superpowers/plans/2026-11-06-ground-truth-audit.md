# Optional Ground Truth Audit for research reports

November 6, 2026 · Implementation authorized November 7, 2026

## What the reader gets

During setup, before research starts, ask **Ground Truth Audit?   Yes / No** with **No selected every time**. Use the prompt text “Check the finished report against its sources. Adds time and may increase model charges.” Enter accepts No. A Yes on Friday must never become Monday’s default.

**No** runs the current research workflow, including its existing financial checks and advisory review. It makes zero additional audit calls. **Yes** checks the material factual claims in the report the reader actually receives, including the final Portfolio Manager reasoning, tables, and any executive summary. Near the beginning, show the audit outcome, the corrections that matter to the decision, any unresolved claims, and a link to the detailed evidence. The official-use benefit is being able to inspect the source for a claim and see exactly where the evidence runs out.

In the DOCN pilot, the research describes “four sessions” and lists three closing prices. The audit should locate the passage, inspect the dated market rows, count the observations, and correct the wording if the rows support the correction. It should separately check any claimed percentage change. Finding the same statement in several agents’ reports adds no independent evidence.

## Scope and planning estimate

The inspected checkout is at `e48207008874e05680d3fa28357682834f52e38f`. Its November 6 DOCN Markdown export contains 46,979 words. The saved financial validator accepted 30 structured facts. The existing advisory review flagged ten potential issues against bounded inputs and runs before the Portfolio Manager. Reuse those records and validators. Relabeling the current audit would leave the final recommendation and substantial portions of the research uncovered.

Build this as one per-run option, a final factual review, and its report output. Use the configured model client and existing source adapters. The separate [executive summary plan](2026-11-06-report-executive-summary.md) supplies another reader-facing section when available. The [operational audit plan](2026-11-06-operational-report-audit.md) assesses execution quality. Ground Truth Audit has its own result. Neither other plan is a prerequisite for prototyping against the current report. Before integration, check which changes have landed and use their actual shared finalization and rendering paths.

| Planning item | Estimate |
| --- | --- |
| Build size | Large |
| Implementation model | GPT-6 Astra (`gpt-6-astra`), medium reasoning |
| Reason for model | Evidence must refer to the correct source, date and financial definition, and corrections must reach the same report version the reader sees. Plausible mistakes across those boundaries can pass a local numerical test. This is an engineering judgment. |
| Active implementation and verification | Approximately **22–38 hours**, assuming the existing source clients, report fixtures and finalizer can be reused. Includes the DOCN pilot, integrated checks, independent Claude audit and one bounded round of fixes and re-verification. The upper end allows for recommendation reassessment and integration with the executive summary. Material redesign or further correction rounds may extend the estimate. Excludes approval and provider waits. |
| Codex credits | No credible range from the available measurements for this workload. |
| Extra cost and time per report | No additional audit requests with No. With Yes, length, unique claims, gaps in retained sources and provider speed determine the increase. Measure actual calls, tokens when available, elapsed time, coverage and any known charges during the pilot. Use those measurements for a runtime estimate. |

## Parallel development and integration

Ground Truth Audit develops in its own worktree from verified staging Build A, `77ebc8abc30757f4bab0c106df9e3b56cd12aebf`, while Build C works on settlement and publication history. Local work can proceed independently. When separately authorized integration occurs, integrate one branch at a time. The branch integrated second verifies the combined publication and report behavior on the resulting staging revision. Later filing-fact and CLI/report changes also require this compatibility check. In particular, a Ground Truth finding must still identify the exact delivered claim after re-export. Current goal authority ends with local verified commits.

## Product decision for the build

The user selected **one Portfolio Manager reassessment before publication**, followed by validation and re-audit, on November 7. Apply it when a verified factual correction undermines the recommendation. Preserve the original reasoning in the audit detail. The setup screen has one Yes/No question.

The user authorized **$50 total** for the paid DOCN pilot and independent Claude review, including retries and closure. Track provider-confirmed costs and conservative reservations against this aggregate cap. Unknown cost remains reserved until reconciled. Obtain further authorization before exceeding $50. Reserve funds for the required initial and closure audits.

An unsupported claim and a demonstrated error have different consequences. A source gap alone cannot establish a replacement number, a new rating, or a buy/sell instruction. Keep the existing evidence, target, sizing and trading-memory safeguards. An incomplete audit can accompany a usable research report, with the limitation visible at the top.

## Implementation milestones

### 1. Establish a reference audit on the DOCN report

Use a read-only copy of `y/complete_report.md`, `y/evidence.json`, `y/quality.json` and `y/diagnostics.json` in a private test directory. Trace the ten existing flags to source records and record a disposition for each. Add independently selected material claims from the final decision, tables, and later passages outside the earlier review window. Cover a supported figure, a calculation, an unsupported causal explanation, a correctly attributed forecast, and a source that was unavailable at the analysis cutoff. Verify disputed pilot findings directly against the original filing or dated market rows where available. The earlier reviewer’s output supplies leads.

Record the exact report passage, expected outcome, source location and reasoning for each reviewed example. Keep a small, shareable fixture for regression tests. The private report and raw provider payloads stay outside Git. This milestone establishes a reference set for evaluating the auditor. The implemented audit must still process the entire pilot report in milestone 5.

### 2. Carry a one-run choice from setup to finalization

Use `cli/selections.py` for the question, `cli/main.py` for the matching `--ground-truth-audit` / `--no-ground-truth-audit` flags, and `cli/run.py` for config propagation. Python callers can use the same boolean run setting. Omitted on a noninteractive run means No. Keep the choice out of the remembered defaults in `cli/prefs.py`. Record an enabled choice with its run and distinguish enabled runs in checkpoint identity. Treat absent and false equivalently for legacy callers and ordinary resumes.

Both the streaming CLI and Python runs converge at `TradingAgentsGraph.record_decision`. Run additional audit work only for a newly completed opted-in run. Saving to a second directory, displaying a report, and re-exporting an older decision use the saved outcome without triggering the audit. An opted-in display-only run should show its result even if the user declines to save a report.

Test that pressing Enter after a prior Yes selects No, explicit flags bypass the prompt, and ordinary headless runs still work. Instrument the test provider and require zero incremental audit calls on every No path. Exercise an opted-in CLI and Python completion through their normal entry points.

### 3. Check the complete report against dated sources

Start from the prepared report sections in `tradingagents/reporting.py`, including prose restored for display by `prepare_report_state`. Use the text and tables actually delivered, with headings and locations a reader can find. Inventory each substantive section and split long sections at paragraph or table boundaries while retaining headers and units. Account for every section and chunk, including the final paragraph. Check material claims about the company, market and events, plus every factual premise used for a rating, target, risk or sizing conclusion. Keep repeated occurrences linked to the same result only when period, definition and qualifiers match.

Use the existing configured model to identify factual assertions and assess whether a cited passage supports their wording. Include qualitative claims and causes. Compare extracted claims with numbers, dates and table rows found in the original text to expose omissions. Each chunk must return a valid disposition, including chunks with no material factual claims. Missing chunks or unaccounted-for material figures lower coverage. Processing every chunk establishes text coverage, not a guarantee that the model identified every assertion.

Select evidence according to what the sentence asserts.

- **Reported facts and disclosures.** Resolve existing fact or document IDs to the underlying SEC record, filing passage or table cell. Check issuer, period, units, accounting basis, source date and qualifiers. For a missing passage, use existing trusted source adapters and the original analysis cutoff. A later restatement or later news cannot validate an earlier claim as known at the time.
- **Market observations and calculations.** Use dated, completed market rows and existing deterministic calculations in the financial evidence, valuation and KPI modules. Match the denominator, share definition, adjustment basis and rounding. Recompute from the source inputs. A matching number with the wrong definition is a finding.
- **News, estimates and interpretation.** Verify exactly what a named source reported. Keep attribution visible for vendor estimates and management guidance. Mark a forecast or hypothesis as such and check its factual premises. If the accessible sources do not establish the underlying event or its cause, report the limit.

Use `tradingagents/agents/evidence_validation.py`, `tradingagents/dataflows/financial_evidence.py`, the existing SEC and market adapters, and the calculation specific to the claim. Put the additional orchestration in a focused audit module. Keep a result for each distinct material claim with its occurrences, outcome, source ID and locator, supporting excerpt or calculation, and correction where warranted. Reject invented citations, quotes missing from the cited passage, references for another issuer or period, and source URLs proposed solely by a model. Treat report and source text as untrusted data.

Group related claims so the reviewer receives the relevant evidence within its context limit. Start with retained originals, retrieve missing evidence through existing trusted adapters where possible, and reuse common inputs. Set finite request, token, retry and elapsed-time limits before the first pilot. Use the authorized pilot ceiling for that run, then calibrate production defaults from the measurements. Count correction and recheck calls within the same budget. Reaching a limit produces partial coverage and identifies unfinished sections. Never silently truncate and then report completion.

### 4. Resolve findings, finalize the decision, and bind the result to the delivered text

Present demonstrated factual corrections where the claim appears and qualify unsupported explanations. Preserve the original wording in the audit detail. Keep source-backed facts, attributed statements, calculations and assumptions distinguishable in the official reading view. Show unresolved material issues next to the affected conclusion. Use the existing language setting for reader-facing explanations and preserve source quotations in their original language.

If the reassessment policy is selected, use the opted-in new-run path after the Portfolio Manager produces a candidate and **before** the existing publication and memory writes. Supply the verified corrections and affected reasoning to the Portfolio Manager once. Run the normal publication validators on the resulting candidate, regenerate dependent decision text or summary, and recheck changed claims. A remaining material conflict yields “Recommendation needs review.” If the annotation-only policy is selected, apply corrections to the reading view and show the impact beside the original rating. The auditor itself has no rating authority. Existing insufficient-evidence REVIEW runs retain their safety behavior.

Capture the report version using the run identity, as-of cutoff, evidence identity and a digest of the exact substantive reader-facing sections. Include the summary if present. Exclude formatting-only timestamps and the audit’s own generated status from the digest. At finalization, reconcile every substantive section against the delivered version and check any late-added or changed passages, including outcome-history text. When the executive-summary feature is present, its planned generation happens after publication. For reassessment, check the underlying recommendation before publication, then check the actual generated summary against that decision and its cited evidence before showing an audit result. Correct any summary-only misstatement and recheck it. If later finalization reveals a new material issue with an already published decision, disclose it and flag that recommendation for review. Historical publication and trading-memory records remain immutable.

Persist the audit detail with the matching run using the existing state-log and strict file-writing mechanisms. Reuse a completed, matching audit on retry or re-export. A changed section, a different evidence snapshot, a mismatched run, or a missing audit cannot inherit an earlier success. Distinguish a provider failure, a genuine contradiction, and a stale result. An audit-only failure leaves the research available with an explicit incomplete/unavailable status. Existing publication integrity and required-write errors retain their current failure behavior.

In Markdown, HTML and the final CLI display, use the same concise assessment. Show material unresolved issues first, then corrections, checked versus unreviewed sections, and the main evidence limits. Provide a reader-followable audit detail with passage locations, source links and arithmetic. Represent the outcomes “completed,” “completed with findings,” “partial” and “unavailable” according to the recorded coverage and findings. “Completed” describes the review performed. A confirmed unresolved contradiction must remain visible even if all sections were processed. A later offline export must never show a link to another run’s audit in a reused directory.

### 5. Prove that Yes is useful and No stays inexpensive

1. Run synthetic cases through the normal setup, finalization and export paths. Seed wrong dates and units, a fabricated source reference, an unsupported causal claim, a changed valuation denominator, and an error appearing only in the last paragraph of the final decision. Include true facts, properly qualified forecasts and legitimate analyst disagreement. Confirm each planted material error is surfaced and the supported controls retain the correct wording.
2. Exercise incomplete evidence, malformed model output, provider failure, exhausted budget, a legacy report, an interrupted save, a repeated export and a stale audit. Compare the report, decision, memory and immutable evidence for the applicable rating policy. For reassessment, exercise both an unchanged rating and a changed rating, one decision publication, and a revised conclusion that still has a gap. For annotation-only, prove the original rating remains the published rating.
3. Verify equivalent findings and working source references in CLI, Markdown and HTML, including Markdown-only export. Check the same report with No through the standard path. Re-run existing coverage for headless flags, preferences, publication, evidence, checkpoints, re-export and output presentation. Run the repository default suite and lint because finalization is shared.
4. Run the entire retained DOCN report into a separate directory with the implemented audit. Compare the results to the independently adjudicated reference cases, inspect a sample of supported claims and unflagged prose, and investigate missed material errors and false alarms. Record coverage, unexpected findings, blind spots, runtime and provider usage. A local fake provider proves integration. Assess actual model quality using an explicitly authorized, spend-capped pilot before describing the feature as proven for official use. This plan authorizes no provider spend.

Run the focused checks followed by the repository suite in the future implementation worktree.

```sh
python -m pytest -q tests/test_ground_truth_audit.py tests/test_cli_headless.py tests/test_cli_prefs.py tests/test_cli_config_precedence.py
python -m pytest -q tests/test_publication_graph.py tests/test_verified_reexport.py tests/test_checkpoint_resume.py tests/test_reporting.py tests/test_report_html.py
python -m pytest -q
python -m ruff check .
git diff --check
```

Use the implementation worktree’s verified Python environment. Add the integration test filenames actually created. Record the tested commit, fixture provenance, pilot evidence and limitations in the repository’s existing review records.

### 6. Obtain the mandatory independent Claude build audit

After the applicable milestone 5 acceptance checks pass, commit the stable candidate on the isolated branch. Give a Claude reviewer who did not implement the feature the approved plan, the baseline and candidate commit IDs, and the authorized test evidence and representative report outputs. This review is required for build completion regardless of the Yes/No setting offered to report users.

Have Claude compare the implementation and actual outputs against the acceptance criteria. In particular, independently trace a corrected claim and a claim marked supported back to their dated inputs, inspect coverage of the final recommendation, check the evidence for zero extra calls on No, and examine the approved rating policy, publication, memory and re-export behavior. Record the reviewed commit range, checks performed, findings, and any limits in the repository’s existing review records. If Claude cannot complete the required audit within authorized access or spend, report the unfinished audit and keep the build goal incomplete.

### 7. Complete the gap-closure build and verify closure

1. **Triage every finding against the approved plan.** Reproduce it against source, a test or an actual report. Where proof is missing, run the smallest check that resolves it. Give each finding an evidence-backed disposition. Record disputed and out-of-scope items with the reason. A confirmed acceptance failure stays open until fixed.
2. **Build and verify the fixes.** Make focused local commits for confirmed in-scope gaps. For each correction, repeat the check or report scenario that exposed it and run the affected regressions. Preserve valid earlier evidence with its original commit identified, and repeat any full-suite or pilot check required by acceptance or invalidated by the change.
3. **Obtain independent closure.** Return the fixes, before-and-after evidence and exact corrected commit to Claude to verify that the findings are resolved and check for regressions in the affected behavior. Repeat for any remaining confirmed gaps. If the initial audit finds no confirmed gaps, record that verdict against the tested commit. No correction commit is needed in that case.

**Mark the build goal complete only when** required acceptance has passed, the independent Claude audit is recorded, every confirmed in-scope gap has verified closure, and the isolated branch is clean with implementation and evidence committed. The handoff gives the final commit, the audited and tested commits, verification results, each finding’s disposition, and any remaining limitations. Missing required proof or an outstanding material finding keeps the goal incomplete. Local completion grants no merge, push, installation or release authority.
