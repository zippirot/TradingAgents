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
