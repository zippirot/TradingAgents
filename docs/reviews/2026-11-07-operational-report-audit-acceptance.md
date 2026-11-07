# Operational report audit acceptance

Implementation began November 7, 2026 on `codex/operational-report-audit` in the managed isolated worktree. The verified predecessor is `fd010a03ba33091860e3baf03c92eb5fb4c91e8c`. The governing plan was copied into this branch and committed as `ee0467ad` before implementation.

## Implementation evidence

The first new graph regression failed because neither API nor streaming completion retained operational observations. The implementation records run-bound node completions and application-visible failures in `operational_observations`, using a replay-idempotent reducer. The original evidence snapshot allowlist excludes this field. Observations include the actual Evidence Check route, so an intentional REVIEW bypass has different expectations from an ordinary full run.

Application-visible vendor fallback and exhaustion, direct SEC acquisition exceptions, social retrieval failures, malformed structured-output fallback and tool/model response failures are observed at their existing boundaries. Records contain allowlisted reason codes and bounded scopes. Provider exception messages and raw payloads are excluded. A callback records response truncation where the provider supplies its finish reason. Provider-internal retry counts remain unknown.

The five-point score uses explicit reason classifications. Stale or malformed observations cannot establish a clean result. Each rendered assessment includes the score, definition, consequence, five observed inputs and a relative link. The linked Markdown audit identifies execution coverage and finding locators. A destination lock serializes saves to the same directory. Existing differing audit files retain their contents while a subsequent export gets its own companion filename. Audit-only failure yields Unrated with no stale link. Required report/publication failures still propagate.

## Offline verification

The predecessor baseline passed 93 focused tests. Capture and surrounding graph, vendor and checkpoint regressions passed 39 tests before source/advisory incident coverage was added. Later focused capture, score and exporter checks passed 28 tests. Repository Ruff and whitespace checks passed on the integrated candidate.

`tests/test_operational_capture.py` exercises both invocation and streaming graph execution through scripted upstream models. Its finalization proof supplies a deterministic editorial response and an empty advisory finding response at the upstream boundaries. The real graph, summary validator, publication, finalizer, report writer and assessor run. The clean case scores 5/5 and the induced news vendor failure scores 3/5 in Markdown, HTML and the linked audit. These are injected offline proofs. The legacy graph fixture has no document corpus, so this proof chooses its vendor tools without making a fabricated document query. Existing document-tool regressions continue to exercise that feature independently.

`tests/test_operational_audit.py` covers all five levels, Unrated, critical precedence, intentional REVIEW skips, stale/malformed or incomplete observations, parallel merge/replay and deterministic rating authority. `tests/test_operational_export.py` covers links, unchanged input state, reused destinations, concurrent saves, audit failure, required write failure, direct HTML and Markdown-only export.

The stable-candidate default suite passed **3,032 tests**, with 10 skips, 1 integration deselection, 100 passing subtests and 24 warnings in 39.31 seconds. The skipped checks require the optional Bedrock dependency or private retained DOCN inputs. The command was `.venv/bin/python -m pytest -q --tb=short`. Repository Ruff and `git diff --check` passed. The independent Claude audit remains pending. Required visual/portable-folder inspection and any audit corrections must be completed before goal closure.


## Independent audit and correction build

Claude Fable completed run `3bc83cff-9f85-4809-9c15-d2267678b118` against `fd010a03..d3cb1e0e` in 19 turns at $0.83006825. The complete returned record is retained without editing in `2026-11-07-operational-report-audit-claude-initial.json`. This was a frozen diff review. Claude did not execute repository tests and could not inspect unchanged dependencies or external render artifacts.

| Finding | Disposition in the correction build |
| --- | --- |
| Unconfigured vendor discovery lowers the grade | Partially confirmed. Default discovery can enumerate optional unconfigured providers, so successful discovery now carries no incident. An explicitly selected provider whose credentials are missing still produces a finding. Exhausting every provider still records that the requested input could not be acquired. |
| Structured-output failure mislabeled as a routine retry | Confirmed. A successful free-text fallback after a failed structured invocation now records fallback_recovered, graded 4. Unsupported structured output discovered at model construction continues through its ordinary supported text path. |
| Direct HTML render claims verified export integrity | Confirmed. In-memory rendering without a publication claim now reports not applicable. A claimed publication without store verification remains unverified. |
| Truncation, checkpoint and independent-run proofs missing | Confirmed. Added a real model callback truncation test, a deliberately interrupted graph with retained observation checks after resume, a new same-ticker/date invocation, and saved-state observation checks. |
| Reducer can reject differing run identity | No current application defect was demonstrated. Rejecting foreign identities is required for the mixed-run integrity boundary. The tests retain this rejection and prove ordinary checkpoint resume succeeds. An audit record whose identity differs during offline export produces a low-confidence assessment. |
| Completion evidence pending | Confirmed procedural state at the audited candidate. Rendering evidence and correction checks are being recorded here. The goal remains open until independent closure on the corrected commit. |

The correction fixture initially attempted to read state through the uncheckpointed graph before recompilation. It failed with No checkpointer set. Separating begin_checkpoint from get_state corrected the fixture setup. The complete 41-test feature/router correction group then passed. Repository Ruff and whitespace checks passed. The final corrected source passed **3,040 tests**, 10 skips, 1 integration deselection, 100 subtests and 24 warnings in 42.09 seconds using `.venv/bin/python -m pytest -q --tb=short`. Repository Ruff and whitespace checks passed. Earlier intermediate suite results are superseded by this stable-source run.

## Rendered and portable output proof

The real finalization test fixtures were exported outside the repository at `/Users/zipp/Documents/ChatGPT/Tauric/output/operational-report-audit-proof/d3cb1e0e/clean` and `degraded`. Both directories were copied from their original temporary export locations and reopened. The final main-document relative links still resolved to the matching score in the audit file.

Browser security rejected a local-file preview. A local static LibreOffice HTML-to-PDF conversion and pdftoppm rendering produced `complete_report.pdf` and `last_page.png` in each proof directory. Both images were inspected. The final footer shows 5/5 Strong or 3/5 Degraded, the correct definition, consequence, all five inputs and a readable relative audit path with no clipping or overlap. PDF link metadata confirms the relative audit-file annotation. The converter produced A4 output. This proves readable static content and links, with browser-specific CSS and Letter layout unverified. WeasyPrint was unavailable because the host lacks Pango. The project has no added rendering dependency.


The related direct Yahoo-price path catches transport failures and returns an unavailable placeholder. Added an observation for that typed transport failure and a regression proving its sanitized capture. The existing application-visible Yahoo retry wrapper now records a recovered retry only after a successful response. A three-attempt local rate-limit fixture verifies that event. Retry budgets and delays retain their existing behavior.

The committed `2026-11-07-operational-report-audit-synthetic-proof.json` retains actual sanitized observations, run settings and publication identity for the clean and degraded real-finalization fixtures. It includes the actual Markdown/HTML footer excerpts, full linked audits and SHA-256 hashes of all three original artifacts. These are synthetic offline outputs, provided for independent source-to-score-to-export tracing. The observed row maps are the same maps saved by the shared finalizer.

Independent closure requested against the full predecessor-to-corrected candidate. Verify each disposition above and trace the two committed synthetic proofs. The available initial audit is completed, and this acceptance record truthfully leaves the closure gate open until the review returns. Distinguish that expected procedural state from an implementation defect.
