# Operational audit and five-point report quality assessment

Date: 2026-11-06 · Completed locally on 2026-11-07. See [acceptance and independent closure](../../reviews/2026-11-07-operational-report-audit-acceptance.md).

**Independent audit: required**. The build goal includes an independent Claude audit of the implementation and verified closure of its material findings in the same isolated worktree.

## What the reader gets

At the end of each saved main analysis, answer: **Did this run produce the report it claims to have produced, and did anything go wrong that changes which parts I can rely on?** Generate one human-readable operational audit beside the main report. End both `complete_report.md` and, when requested, `complete_report.html` with the same short assessment and a visible, clickable **relative file path** as its last content line. The path must also make sense when printed or copied.

Illustrative footer for a run with an observed failure:

> **Operational quality: 3/5 — Degraded**
>
> **Meaning:** An operational problem reduced the reliability of identifiable parts of the report.
>
> **This run:** News retrieval timed out and its fallback failed, reducing support for the news analysis and conclusions that depend on it. The remaining required stages completed, and the saved decision matched the publication.
>
> **Rating inputs:** Stages: completed · Models/tools: news retrieval failed · Run identity: matched · Report integrity: verified · Audit coverage: sufficient.
>
> **Full operational audit:** `./operational_audit.md`

Keep the verdict, one-sentence definition, one or two sentences on consequences, five compact input results, and the path. The full audit opens with the same verdict; identifies the run, ticker, analysis date and publication where available; shows expected versus observed execution; and explains each material incident: **what happened, what record shows it, whether it recovered, and what output it affected**. Show useful counts and elapsed time only when observed, with their scope. No incident list is necessary on a clean run.

This is separate from the stock rating, quality of financial evidence, and the existing model-generated advisory audit. Do not repeat valuation assumptions, market risks, missing disclosures, disagreements, or findings already explained in the research. If a service failure caused an existing caveat, describe the operational cause once and point to the affected section. A successful run can produce limited financial evidence or a non-actionable REVIEW and still earn 5/5.

## Scoring contract

Use deterministic rules and one shared definition table. Evaluate the most serious supported finding first; **do not average** inputs, count warnings as votes, or apply an investment rating. Mandatory checks depend on the selected analysts, actual graph route, and requested export formats.

| Score and name | Definition displayed to the reader | Deciding evidence or example |
| --- | --- | --- |
| **5/5 — Strong** | Required work completed, integrity checks passed, and no material operational problem remains. | All required checks are supported. Routine, fully recovered retries or an intentional skip do not lower the score. |
| **4/5 — Good** | A minor operational issue occurred, with evidence it did not materially affect the report. | An optional ancillary operation failed, or an unusual fallback was needed; the required inputs and outputs are demonstrably intact. Lack of evidence of harm alone is insufficient. |
| **3/5 — Degraded** | An operational problem reduced the reliability or completeness of identifiable parts of the report. | One analyst lost an input to a service failure, or the executive summary is unavailable while the full research and its decision are intact. Name the affected sections and dependent conclusions. |
| **2/5 — Low confidence** | A significant unresolved problem or missing essential evidence prevents establishing the reliability of important parts of the report. | An expected stage has no trustworthy completion record and its effect on the decision cannot be bounded, or the claimed publication cannot be independently checked in a standalone export. State what is unknown; do not assert corruption. |
| **1/5 — Compromised** | A confirmed critical failure makes the report unreliable as a representation of this run. | Evidence proves mixed-run inputs or an unexplained conflict with the authoritative decision. A legitimate, disclosed difference between historical publication and current validated presentation is not this failure. |

**Unrated — audit unavailable** is a separate outcome, not a sixth score. Use it when there is no usable run audit at all (e.g., an old state with no execution observations), or the auditor itself failed. Explain why. When there is a usable audit and a particular essential check is unknown, use **2/5** unless a confirmed critical failure takes precedence. Missing optional timing or SDK-internal retry counts do not alone cap a score. Show the scope of observation; never print “zero retries” when the actual count is unknown.

The five inputs are (1) required stage completion, (2) model/tool execution and recovery, (3) run, settings, input and checkpoint consistency, (4) publication and export integrity, and (5) audit coverage. Use observed results or explicit “unknown” / “not applicable” for each. A machine event belongs under the input it affected. A failed write, process restart, truncation, or timeout can matter; a slow run, high CPU use, or long gap between timestamps does not by itself establish lost work. No host monitoring or performance thresholds.

## Starting point and delivery estimate

This follows the [executive-summary and contents plan](2026-11-06-report-executive-summary.md). Implement on an isolated branch **containing the verified predecessor implementation**; confirm its actual commit, finalization hook, summary statuses and renderers before editing. If that build is not ready, leave this plan queued rather than implementing the predecessor here. Current planning baseline: `/Users/zipp/Documents/ChatGPT/Tauric/TradingAgents`, branch `codex/installed-staging-89aae49-with-pins`, commit `e48207008874e05680d3fa28357682834f52e38f`. Preserve the installed checkout, existing plans and user reports.

- **Build size:** extra medium. **Recommended model:** GPT-6 Astra (`gpt-6-astra`), **medium** reasoning. The hard part is following one run across parallel analysts, a possible restart, an immutable publication and a later export. A plausible but wrongly attributed success could pass isolated scoring tests. This is an engineering judgment under the project’s model policy.
- Allow approximately **12–22 active hours** after the predecessor is ready. This includes the original 10–18 hours for implementation and verification plus 2–4 hours for the independent audit, one bounded round of fixes and a closure check. The estimate assumes the predecessor’s shared finalizer and offline graph fixtures can be reused. Further material corrections may take longer. External waits are excluded. Codex credits cannot be estimated credibly without comparable measured runs.
- The feature requires no new service, model call, external storage, credentials, or paid verification. Use existing local mechanisms; the audit must also work offline when re-exporting.

## Implementation milestones

### 1. Define the record and prove the rating rules

Add a small `tradingagents/operational_audit.py` module for a versioned, bounded execution record, pure scoring function and shared assessment. Keep the original run observations separate from checks made while exporting. Record only the identifiers needed for attribution, stage/category, expected and observed outcome, sanitized reason code, recovery, affected scope and evidence locator. A locator should identify a check, stage or structured field the implementer can trace; never copy raw prompts, tool arguments, exception messages, payloads, credentials, endpoint URLs or personal filesystem paths. Preserve the count and worst severity if repeated events are grouped or details are capped.

**Verify:** table-driven examples for all five scores and Unrated; a critical finding outweighs four passes; a recovered routine retry is distinguishable from a minor incident and exhausted recovery. For example, an otherwise consistent saved report whose execution record proves a required stage consumed a different run's input scores 1/5 even if the export faithfully reproduces the decision. Vary financial evidence status and investment rating while holding execution fixed: the operational score must not change. Every scored case must explain its decisive input in plain language.

### 2. Capture what actually happened on both run paths

Use `tradingagents/graph/setup.py`, `graph/analyst_execution.py`, `agents/state.py`, and `graph/trading_graph.py` (paths under `tradingagents/`) to capture small, run-scoped observations at actual graph and analyst completion boundaries. Reuse retained settings, completed debate turns, tool evidence, acquisition outcomes and the predecessor's editorial status. Record when a required stage returned an unusable output, even if its node exited successfully. Derive expectations from the selected graph and the route taken: on the insufficient-evidence branch, downstream debate and decision calls are intentionally bypassed. A final REVIEW rating alone does not prove that branch was taken.

Record application-visible model/tool outcomes where they are known, including timeouts, rejected/malformed results, actual response truncation and retries or configured vendor fallbacks. In particular, `tradingagents/dataflows/router.py` knows which vendor failed and which, if any, answered. Distinguish an operational outage from an answered request with no matching market data. Account for direct acquisition and sentiment prefetch as well as tool-using analysts. A limit on how much tool evidence the advisory audit retains is **not** proof the analyst received truncated input. Preserve existing retry budgets, vendor order, graph behavior, and exception propagation. Do not add calls to “check” a provider.

Both the streaming CLI (`cli/run.py`) and Python invocation must produce equivalent evidence, including without the optional CLI statistics callback. Its model-start count is not a completion count and does not expose provider-internal retries. Capture retry events when the application or an existing supported hook exposes them; otherwise disclose the blind spot. No SDK patching, raw-log scraping or inference from missing errors. Where a provider-specific signal is unavailable, rely on verified application-level outcomes only for the claim they support.

Carry observations through checkpoints with the existing run identity. Parallel analysts must not overwrite each other; a replay must not double-count completed work. A new attempt can resume the same run; a new run of the same ticker/date must not inherit its observations. Existing `record_attempt_event` records may corroborate a linked attempt, but a date-based log or a dangling “started” entry cannot identify a crashed stage or prove its cause. If history is incomplete after a restart, record partial coverage. If execution stops before a report exists, preserve the existing failure/checkpoint behavior; do not fabricate a report to carry a score.

**Verify:** exercise both execution paths with local fake providers; parallel analysts, intentional skip, actual returned error despite a completed tool call, fallback recovery and exhaustion, response truncation versus excerpt truncation, partial restart and a second independent run. Include a failure before completion and ensure the original exception still reaches the caller.

### 3. Bind observations to the publication and check the actual export

Use the shared `record_decision` / `_log_state` and report writer. Retain execution observations and the predecessor's editorial outcome in saved state under their own fields. Bind the record to the run ID, normalized ticker, analysis date and verified publication identity when available. Check retained settings from that run, not the graph settings of whoever re-exports it. Reject stale, malformed or mismatched audit data as proof; distinguish a mismatched **audit record** from independently demonstrated corruption of the **report**.

`tradingagents/reporting.py` and `tradingagents/memory/publication.py` already verify the saved publication, decision and original evidence snapshot. Reuse those checks; do not create a second authority. **Keep new observations out of `run_metrics` and `evidence_snapshot`: both participate in publication identity today.** Do not alter decisions, trading memory, evaluation, original hashes or historical records. For a historical export, identify the original execution separately from the current validated presentation. Check that the actual Markdown/HTML decision, section identities and requested companions correspond to the intended prepared view and run. Merely finding files with the right names in a reused directory is not proof.

Build one assessment from the retained observations and the current export checks. Verify the report content independently of its new footer, then render that same assessment into the audit and both formats. Use the existing strict file replacement helper where relevant. Verify the final outputs against the expected content and resolved audit path before returning success; avoid circular hashes in which the score must contain the checksum of itself. A publication integrity exception or required report write failure remains an export failure, even if the scorer could classify the cause as 1/5. Never bypass an existing check to display a score.

**Verify:** same-run re-export offline, changed exporter settings, another run with the same ticker/date, stale observations, legitimate revalidation, foreign or corrupted publication, legacy state and an export without the publication store. Save/load must preserve usable observations. Compare original publication, evidence and memory before/after export; assert no model or network calls. Inject a disk/write failure and verify it is not reported as a successful export.

### 4. Write the audit and finish both main documents

Write `operational_audit.md` in a fresh export folder and pass its actual relative path plus the same assessment into the Markdown and HTML renderers. Keep the predecessor's opening, decision-first body, contents, existing section identities and HTML opt-out intact. Format the audit as a readable verdict, the five input results, material findings and observation limits. Use fixed vocabulary and escaped values; honor the report's established language handling without adding a translation call. The audit requires no new JSON export, dashboard, CLI switch, or user confirmation.

Write the matching audit before exposing a new footer that links to it. For a reused destination with a different existing audit, use a distinct local companion filename so an interrupted save cannot repoint a previously written footer to another run’s audit. Use only writer-chosen safe relative filenames. An audit-only computation or sidecar failure must not erase a valid research report: display **Unrated — audit unavailable** and the reason. Link an explanatory audit if one was actually written; otherwise omit the link instead of linking to a stale or nonexistent file. A direct HTML render without an export destination must not promise a sidecar on disk.

**Verify:** parse both final documents to check the last assessment’s score, name, exact definition, consequence, all five actual input results and the working relative path. Open the output offline, move the folder, and check the link and print readability. Test Markdown only, reused folder, sidecar failure, direct render and untrusted text escaping. Confirm a failed editorial summary affects only the stated scope; existing research caveats and advisory findings do not reappear in the footer.

### 5. Verify and commit the build candidate

Use synthetic local fixtures and temporary output folders. Produce at least one complete clean export and one with a deliberately failed or recovered operation through the real graph/finalization and file writer using fake upstreams. Inspect the artifacts as a reader and trace each score to its observed inputs. Also render a representative legacy export: absence of telemetry must remain visible. Never overwrite a real user report for a test.

Run the new focused tests plus the applicable existing suites, particularly `tests/test_run_metrics.py`, `tests/test_vendor_routing.py`, `tests/test_checkpoint_resume.py`, `tests/test_evaluation_attempt_log.py`, `tests/test_publication_graph.py`, `tests/test_verified_reexport.py`, `tests/test_reporting.py`, `tests/test_report_html.py`, and the predecessor’s summary regressions. Run the repository default suite and lint once stable: `.venv/bin/python -m pytest -q`, `.venv/bin/python -m ruff check .`, and `git diff --check`. Broad verification is warranted because observation capture touches shared execution and export paths. No live provider run is needed for acceptance; distinguish injected faults from observed production behavior.

Record the baseline, tested revision, fixtures, commands, results, representative footer and limitations under `docs/reviews/`. Inspect the complete change and commit the stable candidate and its acceptance evidence on the isolated branch.

### 6. Run the independent Claude build audit

Run the independent audit and close confirmed material findings in this same worktree before reporting complete. Give a Claude reviewer who did not implement the feature the plan, the full change from the predecessor commit to the candidate commit, the acceptance evidence and representative synthetic exports. Use the approved review route and its access and spending limits.

Have Claude trace one clean score and one degraded score from actual run observations through the scoring rule to the saved Markdown, HTML and linked audit. Check whether an interrupted or different run can borrow a passing result, whether partial evidence is graded honestly, and whether the feature preserves publication integrity. Record the reviewed commits, checks, findings and limitations under `docs/reviews/`. If the review cannot finish, record what remains and keep the goal open.

### 7. Build and verify the audit fixes before completing the goal

Check each finding against the source, outputs and acceptance criteria. Record its disposition and evidence. For every confirmed in-scope acceptance gap, including the supported part of a partially confirmed finding, implement the correction in this worktree and commit it. Record why any rejected finding does not apply. Track optional suggestions separately.

For each fix, reproduce the issue where practical, rerun the affected checks, and regenerate any affected report and audit examples. Preserve the required full-suite gate and identify which revision each result covers. Give Claude the corrected commit, the findings and the before-and-after evidence for an independent closure check. Repeat for any confirmed material gap that remains. If the first audit finds no material gaps, record that verdict against the tested candidate.

**Complete the build goal only when** required acceptance passes, the independent Claude audit is recorded, every confirmed material gap has verified closure, and the branch is clean with the implementation and evidence committed. Report the final commit, the audited and tested revisions, each material finding and its disposition, and remaining limitations. Existing boundaries on push, PR, merge, installation, deployment, worktree removal, historical backfill and paid runs still apply.
