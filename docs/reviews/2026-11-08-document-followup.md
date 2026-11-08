# R2 document follow-up — in progress

R2 starts on Machine 2 in `/Users/zipp/.codex/worktrees/document-followup/TradingAgents`, branch `codex/document-followup`, from exact fetched/confirmed staging `78e3611ffb3fd6d8672acc2c15f54489cc258ae6`. R1 is integrated and pushed under the user's 24-hour advance approval, with all seven exact-SHA CI jobs passed: https://github.com/zippirot/TradingAgents/actions/runs/42457304605. Its completed independent Claude Fable audit found zero Critical/High/Medium; three verified Low observations remain recorded in the R1 report. Production remains `9ade69bf155d1b25699d3aecfff3c1b07752aff0`; R1/R5 worktrees are preserved.

The existing approved plan owns this build: R2.1 query normalization/ranking; R2.2 deterministic relevance status and honest card wording, with RM answer judgment unavailable until Na; R2.3 question/returned-passage deduplication. No new vendor/model call, numerical evidence authority, paid product comparison, or prompt behavior is added. Source identity, cutoff, whole-block limits, named-note years and multi-instrument reservations remain required. Existing sealed saved follow-ups/publications retain their original identities; new retrieval semantics must not rewrite historical records or silently reuse older checkpoint context.

User advance authority is recorded through `2026-11-09T05:20:03Z` and covers necessary stage integration/push and independent-audit retries within unchanged caps. It does not waive acceptance/audit gates, raise budgets, expand scope or authorize production release. No new approval stop is needed for routine work within that interval.

Focused baseline: 32 existing document-followup/search/acquisition tests passed in 2.29s (`/tmp/r2-baseline-focused.log`). The public source-only DOCN fixture and original four query strings replayed through the exact baseline Git blob reproduce the audit's wrong rankings: bull-1 and bull-2 top-rank lease block-226, bear-1 top-ranks release block-24, bear-2 top-ranks block-226. All four legacy statuses are `found`. Exact queries, source/locator/hash, bounded top excerpts, corpus/input hashes and predecessor integration/CI receipt are in `2026-11-08-document-followup-baseline.json`. The original state hash remains `d9505e263d70b0e59aba03d6f75c250c7c6d320e22070cbc5002876811e27f2b`; no private memory or full model report is copied. No network/model call or source-store write occurred.

Implementation, post-change four-question replay, actual report/state delivery and failure/restart checks, complete default suite, Ruff and required frozen-manifest Claude Fable audit remain pending. This baseline is not build acceptance or whole-plan completion.


## First complete implementation candidate — full acceptance pending

Query normalization now removes question/date/form filler before scoring, preserving only-date queries, instrument-identifying years, meaningful negations and numeric horizons. Body phrase bigrams outweigh isolated words; bodies outweigh headings. Existing keyword/section search, source IDs/cutoff/whole-block limits and named-note reservation stay covered. Both real RPO questions now top-rank Q3 10-Q block-148 with $799,707/$345,111 under the filing's scale. All four before/after rankings will be recorded without claiming that the other two full questions are answered.

New sealed follow-up schema2 uses `relevant_passages_found` only when all normalized content words occur in one returned body, otherwise `no_relevant_passage`; unavailable/invalid input remain distinct. Ranking and relevance share the same conservative terms. These statuses never judge an answer. Raw original questions, IDs and exact unvalidated source text remain retained. The report/card stops using passage counts as a result, always shows retrieval status and explicitly says `RM answer judgment unavailable`. It still reports only citations actually present in the final decision text.

Equivalent or contained near-identical phrases share one canonical lookup using the most complete original query; each original question/role/ID remains in its own result with shared-lookup provenance. Distinct instrument years and opposing negations cannot collapse. Context emits an exact source passage once and points repeated questions to it. Schema1 snapshots are validated/reused without rewriting, and their views say `legacy_relevance_not_assessed`; new relevance is not invented for historical publications. Existing graph source-signature mechanisms advance document_search/document_followup from2 to3, leaving predecessor checkpoints under their old identities.

Observed red checks: `/tmp/r2-followup-red.log` reproduced five result/status/card/dedup defects; `/tmp/r2-distinct-question-red.log` reproduced opposite-meaning lookup collapse before its correction; `/tmp/r2-checkpoint-version-red.log` showed old checkpoint identity; search/date reds are `/tmp/r2-search-ranking-baseline-red.log`, `/tmp/r2-search-date-red.log` and `/tmp/r2-search-iso-red.log`. The initial helper-import failure alone was not accepted as ranking proof; exact frozen baseline code was exercised against the recorded public fixture to establish the real wrong top blocks.

Combined focused group passes **58 tests, 3 skipped in4.28s** (`/tmp/r2-stable-focused.log`), including transcript routing, strict sealed source/relevance checks, negation/note identity, date-only/ISO/date-first normalization, legacy records and checkpoint identity. The skipped private legacy document/transcript fixtures remain unavailable; the new public-source proof runs separately. Repository Ruff/diff checks pass. No assertion was weakened: original source/hash/citation/omission tests remain, with status/wording expectations updated for the approved contract.

The first direct native source/state/report proof passed (`/tmp/r2-first-source-proof.json`). All four scripted original queries use three lookups; both RPO questions return block-148 first. All four FULL question bodies still lack some content terms, so `no_relevant_passage` is reported honestly; a separate actual keyword lookup proves the positive `relevant_passages_found` path. Source context deduplicates the RPO note and reaches the common downstream context builder. Existing application state writer and Markdown/HTML report/evidence exporters save/reopen exact sealed results in disposable stores. The actual original cfae95e9 schema1 snapshot validates and renders relevance-unassessed without a changed record/file hash. Sockets are denied and paid calls0. This executes real lookup/context/state/report functions directly, not a whole-graph CLI run; the separate existing CLI proof must run on the stable candidate for compiled graph/publication/memory/save/retry/checkpoint/source-replay coverage. No live model/provider compliance or RM answer judgment is claimed.

Next: freeze this candidate, run the complete default suite and both exact-commit proofs, inspect the complete diff, then required frozen-manifest Claude Fable audit/closure. R2 remains local/unpushed and incomplete.


## Complete-suite findings and compatibility correction

First committed candidate `71e662448b7f14da16cdae763383e52c1e6b8ea5`: complete default suite **3 failed,3460 passed,10 skipped,1 deselected,25warnings,100subtests in61.02s** (`/tmp/r2-71e66244-full-pytest.log`). Both direct source/state/report and real CLI compiled-graph/publication/memory/save/retry/checkpoint/source-replay proofs passed on that candidate; they do not override its failed full suite. No independent audit was started.

Two failures were exact old-contract expectations. The report test expected the deliberately removed passage-count wording; it now checks the new unavailable RM-judgment wording while strengthening the actual hidden-citation guard (case-insensitive citation assertion and reference absent). The existing live-proof assessor revalidated results but recognized only legacy status found; it now recognizes validated schema2 relevance outcomes with retained source passages, without calling them answers. Its real retained-source/report test covers both full lexical matches and honest partial matches, still requires all source/report/state checks and still rejects missing persisted evidence.

The historical Build2 continuation first could not locate its copied native checkpoint because its explicitly frozen test signature had not mapped R2's document_search/document_followup3 tokens back to the original2 tokens. The test fixture now freezes those two historical tokens only; current R2 thread-identity regression remains strict, and both current-R1/current-R2 resume-compatibility claims are explicitly false. No production continuation runner, checkpoint or ledger was changed. Native pending-node/ID/role/round/accounting/source/retained-state assertions remain intact.

After restoring the historical fixture identity, its next ValueError exposed a **real compatibility gap**: analyst search journals had no recorded ranking version, and retained_search_packages re-ran every captured query under the new R2 scorer. Read-only inspection of the copied checkpoint found5 unversioned journal entries and reproduced `Document search passage differs from retained source`. This was not dismissed as fixture noise. New journals now record search_version3. Missing/explicit version2 uses the exact pre-R2 terms, plural matcher, score and selection behavior through a bounded legacy replay function sharing the same guarded search core. Unknown versions are rejected. Current search remains version3; original journal entries are neither reranked nor rewritten, and source/corpus/text/hash/issuer/cutoff/whole-block/call-budget validation is not weakened. Transcript replay retains its unchanged source-specific validator.

Legacy equivalence is checked against exact frozen baseline78e3611 outputs/errors: current ranking first disagreed in8/10 cases (`/tmp/r2-search-legacy-red.log`); 28 backend tests and36 additional direct result/error comparisons pass (`/tmp/r2-search-legacy-all-green.log`, `/tmp/r2-search-legacy-differential.log`). Public original-journal tests first failed for the actual changed ranking and now prove legacy reuse unchanged, current-journal version3/current ranking, and rejection of tampered/unknown-version entries (`/tmp/r2-legacy-journal-red.log`).

The related source/consumer/assessor group passes **92 tests in7.00s** (`/tmp/r2-legacy-and-consumers-focused.log`). The historical native continuation now passes **1test in10.55s** (`/tmp/r2-private-continuation-corrected.log`), with no paid transport. Corrected direct proof also passes on the actual original cfae95e9 journal/snapshot, preserving record and input hashes (`/tmp/r2-corrected-precommit-source-proof.json`). An intermediate attempt to inspect an earlier disposable pytest checkpoint found it had been purged by subsequent pytest retention; no original store was affected and no pass is inferred from that unavailable copy. The successful native drill and actual original snapshot proof provide the required evidence.

This is a minimal in-scope recovery: versioned exact historical replay rather than accepting arbitrary source blocks or weakening validation. A fresh complete suite and both affected native proofs will run on the corrected committed source because application replay behavior changed. Earlier passing results are preserved as historical, not combined into a complete passing run.


## Corrected decisive local checks

Corrected committed source `88acc5047529671cd3976a3b939d4041f03dd1f1` passes the complete default suite: **3478 passed,10 skipped,1 deselected,25warnings,100subtests in66.88s**, `/tmp/r2-88acc504-full-pytest.log`. Full repository Ruff/diff checks pass. Both exact-commit proofs passed freshly: `/tmp/r2-88acc504-source-proof.json` (four original queries/three lookups, current RPO notes, context dedup, keyword positive control, state/report reopen, actual legacy snapshot AND original journal exact replay unchanged) and `/tmp/r2-88acc504-cli-proof.json` (four actual CLI compiled-graph attempts, publication/memory/save-retry/checkpoint/source replay, sockets denied, credentials isolated). The earlier failed complete run remains historical, not combined into this pass.

The four-query replay is intentionally reported as retrieval, not question answering. RPO questions now return Q3 block148, Q2 block149 and FY25 block1084 instead of lease tables/release rounding. The other two questions retrieve financing/payment material, but their top rows do not establish all requested concepts or a full answer; their explicit no_relevant_passage statuses and exact dated top excerpts are retained in runtime JSON. The keyword control is relevant_passages_found. These limitations are supplied for independent review, not silently called resolved model judgments. Raw source inputs/corpus hash stay identical before/after.

Runtime JSON binds fresh source and CLI receipts. Source-excerpts JSON supplies all15 distinct before/after returned SEC blocks in full, plus exact BASE scorer and historical-validator code excerpts with commit/path/line/SHA provenance. No private memory, original model reports or credentials are copied. Compressed public fixture bytes and original private snapshots remain referenced by hashes; the frozen runner cannot independently decode/read those or rerun tests.

Final acceptance coverage explicitly names the plan's RPO/keyword tests and adds the all-returned-passages assertion for bull1 (not merely the top-ranked block), which passes on the current code. This extends test coverage without changing application source; the complete suite will be repeated on that final test revision before freezing independent review. The passing native proofs at88acc504 remain reusable only while exact application/CLI/fixture/script/dependency OIDs remain equal, recorded in the verification receipt. R2 independent audit/closure and staging integration remain pending.


## Final pre-audit candidate and supplied context

Final test revision **e40a3df6606e86962a58b6425091353763f454a0** passes **3479 tests,10 skipped,1 deselected,25warnings,100subtests in68.09s** (`/tmp/r2-final-acceptance-full-pytest.log`). This is a complete single-revision run including the all-returned RPO regression and all repaired legacy/proof/report guards. Full repository Ruff and complete-range diff checks pass. No independent audit was launched on either failed/evolving candidate.

Both native proofs actually ran on **88acc5047529671cd3976a3b939d4041f03dd1f1**. Exact package, CLI, public fixture, proof scripts, baseline-input file and dependency-config OIDs match e40a3df6; only final acceptance tests/naming and evidence documents differ. The verification JSON binds both revisions, tree/blob OIDs, raw log SHA-256, environment, source/CLI commands, input/output hashes and limits. No claim is made that native proofs reran on the later test/docs commit, and separate complete-suite results are not aggregated.

The frozen executor will receive54 explicit committed instruction/plan/CI/source/schema/caller/consumer/test/proof/evidence paths. It receives the Git diff and trimmed HEAD contents joined with one newline, without filename headings. The final verification file supplies 1-based decoded line ranges and raw SHA-256 for the preceding53 files; it does not self-hash. Source excerpts contain15 complete public returned blocks and four exact BASE excerpts (including the entire original scorer) so historical replay and strict old/new validation are inspectable without live repository access. No public gzip decompression, private-original access, external-log reads, GitHub queries or independent test execution by Claude is claimed. Supplied runtime receipts are builder observations.

All R2 implementation/decisive local checks are complete; required independent feature acceptance remains pending. User24-hour approval allows necessary subsequent integration/push under unchanged caps after review, not an audit/CI waiver. R4 is technically independent under the approved plan and may use its own exact-confirmed-staging worktree; R3/Na/Nb remain dependent and unstarted.

Independent Claude Fable audit, 2026-11-08: completed normally at frozen `14b4301d708721e40e9f95a6a56f029945a63c49`, run `320f9714-d5c4-4669-805f-1d6ec1dc906e`, base accepted R1 `78e3611f`. Requested/served `~anthropic/claude-fable-latest`, the user-approved permitted alternative; no cap override. Actual 48 turns, $6.14689375, 2,336,589 ms, soft limit not reached, stop `reviewer_completed`. Artifact directory: `/Users/zipp/Documents/ChatGPT/Tauric/audit-artifacts/docs/superpowers/audits/2026-11-08-workflow-gap-r2-fable-1`. Initial manifest/result/findings/closure-plan validation passed while HEAD was still frozen. This validates the audit record, not closure of its findings.

The audit supports local R2 behavior and reports **one Medium and four Low**, no Critical/High. The Medium is a latent test-only defect: two skipped private replay HTML/CLI assertions retain the old retrieval caption. The renderer no longer emits it; the original Nov6 private state/root is unavailable here. A portable invocation of the same actual decision-node/report/CLI path with hash-checked public sources and sanitized state is being prepared to expose and cover the gap. No private acceptance pass is claimed. This finding remains **open pending correction and independent closure**.

Disposition of Low observations: the never-answered test checks dictionary keys and will be tightened alongside the regression repair; conservative all-question-term body relevance is preserved and transparently reported (Na owns RM interpretation); corpus-authentic exact-block validation without re-running filing ranking is pre-existing and deferred under the narrow-scope rule; no R2 remote CI exists yet, and source/proof receipts span docs-only commits. Live `git diff --exit-code e40a3df6..14b4301 -- cli tradingagents tests pyproject.toml` plus both native scripts exits0, confirming unchanged tested source. The frozen reviewer cannot independently execute Git. Corrected-candidate checks and exact published-SHA CI remain separate required gates.

Additional post-freeze static evidence: default `ruff check` exited0 on both frozen R2 and R4 candidates. It was not automatically supplied in the earlier frozen packet.

The complete original R2 independent report follows as audit output, **not builder assertions or a new scope expansion**. Reviewed-files is the executor's inventory; the stated selective inspection and frozen-only limits remain.

```json
{
  "base_commit": "78e3611ffb3fd6d8672acc2c15f54489cc258ae6",
  "head_commit": "14b4301d708721e40e9f95a6a56f029945a63c49",
  "requested_model": "~anthropic/claude-fable-latest",
  "served_model": "~anthropic/claude-fable-latest",
  "status": "completed",
  "actual_turns": 48,
  "reviewed_files": [
    "docs/reviews/2026-11-07-evidence-assembly.md",
    "docs/reviews/2026-11-08-document-followup-baseline.json",
    "docs/reviews/2026-11-08-document-followup-runtime.json",
    "docs/reviews/2026-11-08-document-followup-source-excerpts.json",
    "docs/reviews/2026-11-08-document-followup-verification.json",
    "docs/reviews/2026-11-08-document-followup.md",
    "docs/reviews/document-access-proof-tools/live_cli.py",
    "docs/reviews/document-followup-proof.py",
    "docs/superpowers/plans/2026-11-07-tradingagents-workflow-gap-closure-plan.md",
    "tests/test_build2_continuation_proof.py",
    "tests/test_document_access_proof_guard.py",
    "tests/test_document_followup.py",
    "tests/test_document_retained_replay.py",
    "tests/test_document_search_legacy.py",
    "tests/test_document_search_reporting.py",
    "tests/test_filing_search_backend.py",
    "tests/test_filing_terms_graph.py",
    "tests/test_transcript_tool_integration.py",
    "tradingagents/agents/document_access.py",
    "tradingagents/agents/document_questions.py",
    "tradingagents/dataflows/filing_search.py",
    "tradingagents/graph/trading_graph.py"
  ],
  "summary": "Independent frozen-manifest audit of R2 \"Document follow-up that finds the right passage\" (TradingAgents), base 78e3611f (R1 staging, seven-job CI receipt) \u2192 head 14b4301d (local, unpushed), 22 changed files. VERDICTS \u2014 Merge integrity: GREEN as supplied; the frozen diff is coherent, matches changed_paths, and the audited HEAD application code is exactly base+diff. Feature acceptance (local): SUPPORTED \u2014 R2.1 (query normalization: expanded stop/filler lists, date-span stripping with named-note year and only-date preservation, bigram\u00d77/body\u00d73 over heading\u00d71 scoring, requested-form boost), R2.2 (deterministic relevant_passages_found/no_relevant_passage via passage_matches_query; card shows retrieval status plus 'RM answer judgment unavailable'; passage-count wording removed), and R2.3 (equivalence/containment lookup grouping with negation and instrument-year guards; context passage dedup with shared-lookup provenance) are each implemented and covered by the exact plan-named tests, which exist at HEAD with meaningful assertions (block-148/$799,707/$345,111 top-rank; lease-table regression; keyword preservation; one-slot dedup; context dedup). Backward compatibility is handled honestly and defensively: schema-1 follow-up records validate/reuse without rewriting and render legacy_relevance_not_assessed; analyst search journals gain search_version (missing\u21d22) with exact legacy-ranking replay (replay_legacy_filing_evidence with frozen legacy terms/contains/scoring, pinned by 10 whole-result SHA-256 regression hashes generated from the exact BASE blob), tamper and unknown-version rejection tests, and a run-signature bump (document_search/document_followup 2\u21923) with checkpoint-identity separation and historical Build2 fixture token mapping. The R2 proof obligation (four logged DOCN questions, before/after top passage and status) is recorded in the baseline/runtime/source-excerpts JSONs and the review markdown, with all 15 distinct returned SEC blocks supplied verbatim; both RPO questions now top-rank the Q3 RPO note, and the builder honestly reports all four full questions as no_relevant_passage rather than claiming answers. Full-suite health: builder receipt only \u2014 3479 passed/10 skipped/1 deselected at test revision e40a3df6, with the earlier 3-failure candidate 71e66244 disclosed and its genuine journal-replay compatibility gap fixed rather than suppressed; receipts are not bound to frozen HEAD 14b4301 (docs-only delta asserted, unverified) and cannot be independently rerun here. Remote CI: NOT GREEN \u2014 no exact-R2 CI exists (branch local/unpushed, explicitly disclosed); the seven-job receipt covers only the R1 base SHA. FINDINGS: one medium (stale pre-R2 wording assertions left in the skipped private replay test, a latent failure at the next private acceptance run), four low (key-membership 'answered' test weakness; relevance gate stricter than one plan reading, disclosed; pre-existing absence of lookup replay in schema-2 record validation; receipts not bound to final HEAD / no remote CI). No critical or high findings; no evidence of weakened validation, rewritten historical records, invented relevance, or network/paid-call violations. R2 remains a local candidate: this audit supports local feature acceptance with the named corrections and leaves staging integration/exact-SHA CI as required next steps.",
  "limitations": [
    "Frozen-evidence-only audit: evidence restricted to request.json (base 78e3611ffb3fd6d8672acc2c15f54489cc258ae6, head 14b4301d708721e40e9f95a6a56f029945a63c49, 22-file diff, HEAD contents of 54 requirements paths). No test execution, no repository/network/GitHub access, no decompression of the gzip DOCN fixture; corpus/fixture hashes, pytest/Ruff logs, CI run 42457304605 and native-proof receipts are builder-supplied evidence, not independently rerun.",
    "BASE source was available only as the diff plus four attributed excerpts in the source-excerpts JSON (including the complete original scorer); other BASE files (e.g., prior document_access.py internals) were reconstructed from the diff only.",
    "Private artifacts (original cfae95e9 snapshot/journal at ~/.tradingagents, /Users/zipp/Developer private replay inputs, /tmp logs) are referenced by SHA-256 only; the three private retained-replay tests, five private price tests, private transcript and Bedrock tests were skipped in the builder's full suite, so the medium finding on stale assertions is source-grounded, not reproduced.",
    "Full-suite and native-proof receipts bind commits e40a3df6/88acc504, not frozen HEAD 14b4301; HEAD-vs-e40a3df6 docs-only equivalence is asserted via commit narrative and OID tables but not independently verifiable here.",
    "The ~974k-char requirements blob was inspected selectively (all changed modules in full; unchanged large modules such as sec_documents.py, evidence_validation.py, reporting.py inspected at the followup/search touchpoints via targeted searches), so unchanged-file coverage is risk-selected, not exhaustive.",
    "Spot-checked integrity: decoded requirements line count (17,117) and the audit_context_map ranges reconcile; diff file list matches changed_paths; per-file raw SHA-256 values in the context map were not recomputed."
  ],
  "findings": [
    {
      "severity": "medium",
      "title": "Stale pre-R2 wording assertions left in private replay test will fail once private inputs are available: 'source passages retrieved; final-decision citation not verified.' is asserted against HTML (decoded line 14428) and CLI output (line 14448) in test_retained_docn_passages_reach_actual_decision_nodes, but HEAD render_document_followups no longer emits that string (it now emits 'Retrieved source text, not accepted evidence; final-decision citation not verified.'). The markdown clauses in the same hunk were updated while these two clauses were not; the test skips without the private DOCN root, so the 3479-pass suite could not catch it. Latent test defect only \u2014 no runtime behavior affected \u2014 but it breaks the retained-replay regression coverage the plan relies on at the next Machine-1/private acceptance run. Smallest correction: update the two assertions to the new renderer wording; verification: run the private replay test where inputs exist.",
      "path": "tests/test_document_retained_replay.py"
    },
    {
      "severity": "low",
      "title": "test_retrieval_never_reports_answered checks dict keys, not text: `all(\"answered\" not in r for r in results)` tests key membership in each result dict, so it can never detect an 'answered' claim inside status values, reasons, or rendered card text. The preceding status-set assertion partially compensates, but the named guard does not test what its name promises. Correction: assert against rendered card/context strings or against status values.",
      "path": "tests/test_document_followup.py"
    },
    {
      "severity": "low",
      "title": "Relevance gate is stricter than one plan reading of R2.2 ('every non-stop content word of at least one query phrase'): passage_matches_query requires every content term of the entire question in one passage body, so genuinely on-topic top passages (e.g., bear-1's Q3 RPO note block-148 containing $799,707/$345,111) are labeled no_relevant_passage because words like 'reason'/'portion' are absent. This is conservative, deterministic, never over-claims, and is explicitly disclosed in the runtime receipt and limitations; but until Na (RM judgment) it systematically under-reports relevance for long natural-language questions. No code defect; flag for Na design or a documented phrase-level interpretation decision.",
      "path": "tradingagents/dataflows/filing_search.py"
    },
    {
      "severity": "low",
      "title": "Schema-2 follow-up validator does not replay the filing lookup for non-transcript results: _check_retained verifies each passage is block-exact against the retained corpus and that the sealed status matches _relevance(), and verifies lookup grouping, but (unlike retained_search_packages for the analyst search journal, and unlike the transcript branch) it does not re-run search_retained_document_sources to prove the passages are the deterministic search output. A resealed record could substitute other corpus-authentic, relevance-consistent blocks. This property is carried forward unchanged from schema 1 (pre-existing at BASE per the supplied 78e3611 excerpt), so it is not an R2 regression; recorded as an observation, with bounded correction being a lookup replay in _check_retained for schema-2 filing results.",
      "path": "tradingagents/agents/document_questions.py"
    },
    {
      "severity": "low",
      "title": "Acceptance receipts are not bound to the frozen HEAD: the full-suite receipt (3479 passed/10 skipped/1 deselected) binds test revision e40a3df6 and both native proofs ran at 88acc504 with matching application/CLI/fixture/script/pyproject OIDs; frozen HEAD 14b4301 is a later docs-freeze commit with no suite or proof receipt of its own. The docs-only delta is asserted by commit message/verification narrative and is plausible (the base\u2192HEAD diff contains the audited application code), but it is not independently verifiable in the frozen evidence. Also, no exact-R2 remote CI exists (branch local/unpushed) \u2014 explicitly disclosed; the seven-job CI receipt applies only to base R1 staging 78e3611. Bounded verification to close: rerun the suite (or record tree-OID equality for non-docs paths) at the exact HEAD, and exact-SHA CI after push.",
      "path": "docs/reviews/2026-11-08-document-followup-verification.json"
    }
  ],
  "classification": {
    "declared_build_size": "large",
    "effective_build_size": "extra large",
    "escalation_reasons": [
      "Frozen scope changes more than 10 files or more than 500 lines.",
      "Frozen scope changes more than 30 files or more than 2,000 lines."
    ]
  },
  "progress": {
    "observed_events": 7107,
    "last_activity_at": "2026-11-08T08:28:42.869Z",
    "last_activity_kind": "stdout"
  },
  "ledger": {
    "soft_budget_usd": 50,
    "hard_budget_usd": 80,
    "soft_turn_limit": 100,
    "turn_limit": 160,
    "wall_clock_limit_minutes": 360,
    "actual_cost_usd": 6.146893749999999,
    "actual_elapsed_ms": 2336589,
    "soft_limit_reached": false
  },
  "stop_reason": "reviewer_completed"
}
```

Audit correction, before independent closure: the original decision-node proof was invoked with a portable mixed fixture. Its public corpus bytes are hash checked by `docn_workflow_fixture`; acquisition is the Nov7 corpus, projected to a strictly validated Nov6 as_of only after asserting every filing date is at or before Nov6. Initial state and RM/risk/PM replies are scripted. This is not the unavailable original Nov6 private-state replay and is not a historical market-information claim. The private `_retained_corpus`, expected state hash and source hashes are unchanged. Network socket connection APIs are denied.

Observed red: `/tmp/r2-public-node-caption-red.log` reaches the actual RM/risk/PM, report tree and HTML and fails the old caption assertion. A preceding casing-only citation assertion also used obsolete exact case and now compares the same phrase case-insensitively, matching the existing sibling assertion. Both stale HTML/CLI caption assertions now require the renderer's exact current wording. CLI text is normalized only for Rich wrapping and box borders. The portable wrapper invokes the same original test function so future caption drift cannot hide behind missing private inputs.

The weak never-answered key-membership assertion is replaced by exact observed retrieval statuses and card/context checks: relevant/no-relevant statuses, RM judgment explicitly unavailable, no answered claim on the card, and the context's explicit caution that retrieval does not mean a question was answered. No application/runtime source changes.

Main focused acceptance after strict corpus validation and socket denial: 27 passed, two private-input tests skipped, 4.17 seconds (`/tmp/r2-audit-correction-focused.log`); default Ruff and diff check pass. Full default pytest and independent Claude closure still pending. The earlier 21-pass supporting run is preserved as narrower evidence, not substituted for this candidate's checks.
