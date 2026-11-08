# R4 memory continuity build

In progress; independent acceptance, staging integration and whole Goal remain incomplete.

R4 starts from exact confirmed staging `78e3611ffb3fd6d8672acc2c15f54489cc258ae6` in `codex/memory-continuity`. R1 was accepted and all seven staging checks passed. The approved plan explicitly permits R2/R4 parallel worktrees after R1. R2 is undergoing its frozen independent audit. No reset or rebase has occurred; accepted R2 staging will be explicitly merged before R4 combined acceptance.

Baseline: 214 focused tests passed in 3.25 seconds. A disposable copy of the private publication store contains nine strictly loaded publications and their evidence, with 32 metric conditions. The baseline manifest records every file hash, legacy condition ID, aliases and serialized condition hash. The source store was read only and unchanged. See the adjacent baseline JSON for hashes and local evidence location; private payloads are excluded from committed evidence.

The pending-memory defect was reproduced with four failing behavior tests: a rerun retained the first publication; a delayed first projection overwrote latest-run intent; settlement lacked an identity guard. The implementation keeps replacement and settlement under the existing memory file lock and orders publication selection/projection under the existing publication lock. Settled lessons remain immutable. Evaluation primary flags are independent and unchanged.

The original REVIEW compatibility test expected the first pending Buy to survive a later Sell. Its pending-only expectation is updated to approved D2 (latest pending Sell); its assertions preserving both historical REVIEW entries remain intact. The surrounding settlement/memory checks passed after this adjustment.

Condition schema, PM output, persistence and next-run rendering are being verified together. Known metadata limitation: validated evidence disallows future filed dates/financial periods, so code may identify a future requested condition period without inventing a filing date; exact supported behavior and unavailable metadata will be recorded in final proof.

No phase-one product proof makes paid calls or writes production data. Audit calls use the separately authorized frozen executor within its existing caps. Amendment 1 host work remains R1/R3/Na; R4 introduces no new default horizon.

R4.1 implementation commit: `fb1ab03f` (final candidate still pending). The surrounding memory/publication/settlement/CLI checks passed 168 tests in 3.01 seconds (`/tmp/r4-memory-focused.log`). Additional threaded projection, actual-graph settled rerun and partial-tail replacement tests passed in a 15-test focused run. A process-only negative control disabled only the projection ordering lock: the threaded test then reproduced loss of the latest publication; the real lock passed. No source file was modified for this negative control.

R4 condition candidate `29f5e579` implements metric/price/event PM output, per-condition rejection reasons on the card, immutable persistence and plain prompt rendering with the rationale limit at 1,000 characters. Existing metric serialization and measurement IDs use the legacy representation. The combined focused checks passed 354 tests in 4.61 seconds; Ruff over `tradingagents`, `tests` and the native proof passed.

Review rejected a proposed lower bound based on a carried thesis's `as_of`: that is a revision date, not a condition creation date, and incorrectly rejects a valid Friday close in a Sunday run. The guard was removed after reproducing the weekend case. Completed-close validation, currency matching and expiry checks remain. Whitespace-only event descriptions/confirming evidence are rejected.

The actual compiled-graph role fixtures exposed three assertions for the superseded first-run memory behavior; they now prove exactly one pending entry tied to the same latest publication/thesis while preserving original-only primary eligibility, kept dispositions and all role-specific checks.

Checkpoint identity must distinguish the new PM contract from a metric-only checkpoint. A regression failed with the existing `advisory_thesis=2`; the token is advanced to 3. The historical Build2 continuation fixture then failed because it deliberately addresses an exact old checkpoint. Its existing fixture-only signature adapter now maps 3 back to the original 2; no production resume identity, native pending-node, source hash, role, transport or spend assertions are bypassed. All 16 checkpoint/continuation tests passed in 10.53 seconds after this correction (`/tmp/r4-checkpoint-corrected.log`). The earlier failed drill is not counted as a pass.

The retained 09:10/16:41 proof resolves the exact UUIDs from copied records: `913554d4-32c0-409f-85de-6630f5e114bb` and `cfae95e9-0b34-41cc-b98c-b3b862a7d518`. It uses the 09:10 publication to seed memory because that full terminal state is unavailable; the 16:41 production `record_decision` call replays its retained terminal state. It is a scripted replay, not two new live analyses. Both immutable publication hashes remain unchanged; one pending memory entry and loaded thesis reference the 16:41 record. Both settlement orderings and same-publication retry pass. The additional private-copy scan loads all nine publications and evidence and compares all 32 legacy IDs/aliases/serialization hashes and 27 file hashes.

The three-kind proof uses an actual PM structured-output node with a scripted model, validated synthetic completed closes and synthetic canonical financial evidence. It records metric/price/event states as breached/met/unobserved respectively and rejects an invalid sibling event without losing valid conditions. The integration test separately proves literal event text reaches the next PM prompt and actual HTML export escapes markup. It establishes wiring and safeguards, not model judgment, real market performance or automatic event matching.

Frozen BASE source excerpts are in the adjacent source-excerpts JSON, with exact commit, path, line range and hashes. They distinguish historical source from observed execution. Final combined R2/R4 integration verification, independent Fable audit/closure and staging/CI remain outstanding.

Stable local source candidate: `d9ad53af` (full exact SHA and object IDs in the adjacent runtime/verification JSON). Complete default `python -m pytest -q` exited 0: **3,468 passed, 10 skipped, 1 deselected, 25 warnings, 100 subtests passed, 64.26 seconds** (`/tmp/r4-d9ad53af-full-pytest.log`). Skips are the optional unavailable Bedrock dependency and private historical inputs; none is claimed passed. Both standalone native proofs were repeated successfully on this commit, stderr empty, with network denied and no paid calls. The CLI proof exercised four attempts, interruption/resume, save failure/retry, compiled graph, publication, memory, and reopened JSON/Markdown/HTML. Controlled source replay stayed distinct from synthetic candidate calculations.

Execution adjustment within the explicit parallel-build permission: begin R4's local feature audit after its own decisive full acceptance, concurrently with R2's audit. R4's required technical predecessor is accepted R1, which exact base staging contains. This avoids an unnecessary audit wait; staging integration still proceeds R2 then R4, with an explicitly recorded merge of confirmed staging and combined verification before R3. No reset/rebase or audit waiver is authorized. Local audit cannot establish unperformed staging CI or production acceptance.

Independent audit is required and is **not yet complete**. Use the frozen-manifest executor and user-selected permitted Claude Fable alternative (`~anthropic/claude-fable-latest`), retaining plan-derived limits. Auditor receives the explicit frozen HEAD paths and diff, with no runtime, filesystem, raw private input or external-artifact access. Verification receipts are builder observations, not Claude reruns. The full private store and terminal state are not delivered; sanitized fixture source, exact input hashes, observed receipts and BASE source excerpts are supplied.

The R4.3 observation rule follows the original audit's concrete case: a requested condition measurement period ending after analysis cutoff is not yet reported. Strict evidence validation forbids a retained source with filed_date after as_of; it is not relaxed. Past-period unknown availability remains unknown; no publication schedule/date is inferred. The independent reviewer should assess this boundary and the supplied original audit separately from the plan's later filing-date wording.

Audit context selection: full current memory/thesis/settlement/publication/outcomes, price-observation and financial-evidence models, PM schemas/node, output enforcement, graph/setup/checkpointer, file locks, report/export/CLI, changed regressions and relevant legacy fixtures are supplied as explicit paths. To bound the packet, unchanged `review_terminal_state` and the synthetic PM fixture `state` are exact attributed function excerpts; full evidence-validation/valuation internals and the historical part-B audit are omitted. The R4 requirements, part-A/part-C original audit and baseline excerpts remain supplied. No independent re-audit of unchanged financial valuation internals is claimed. The final verification JSON maps paths to concatenated input lines, because the executor inserts no path headers.

Audit preparation found a manifest false positive in the public original part-C filename (its `risk-…` suffix matches the credential-like filename pattern). The complete unchanged part-C content is instead supplied as an attributed exact-BASE excerpt in the existing source-excerpts JSON, with its full file hash. The checker and source audit are unchanged; no secret or budget is involved. The failed preparation did not start a paid audit.

Independent R4 Fable audit completed normally at frozen `da2b14cd5bade8d7c23b0e3deb7fae2181158d0d`, run `eae4465e-a666-4e42-84d4-75c4d7098857`: requested/served `~anthropic/claude-fable-latest`,52 turns,$4.307448,1,588,616 ms, no soft limit, `reviewer_completed`. Initial audit/result/findings/gap-plan manifest validated at its frozen HEAD before corrections. One Medium and five Low were reported; no Critical/High. Local closure and integration remain incomplete.

Medium finding is partially confirmed: checked nominal test names did not match actual functions, and CI lacked a sanitized raw pre-R4 publication/evidence fixture pinning immutable full hashes and kind-less compatibility. Existing portable tests already covered isolated legacy metric identity/shape and alias/disposition preservation, so the statement that guarantees rested solely on private proof was broader than supported. The confirmed gap is corrected by two deterministic synthetic legacy publications/evidence produced with exact BASE78 code, plus four portable tests. They cover kind-less loads, all four raw file SHA pins and embedded hashes, BASE metric serialization/measurement IDs, aliases, kept dispositions, current next-run carry, and a labelled serializer fault-injection control. No private records were copied into fixtures.

Main independently loaded both golden records/evidence through the unmodified BASE78 source checkout, asserted its imported package path and HEAD, compared the four fixture bytes against the original disposable generation outputs, and checked original model serialization/ID values against the manifest. Receipt `/tmp/r4-legacy-base-validation.json` pins BASE module and fixture-manifest hashes. Generator ran as an inline command; its transcript was inspected, but no original generator script/stdout file was retained and no such artifact hash is invented. The private baseline nine-record/32-condition scan remains an additional proof.

Every R4 checked acceptance entry now names an actual existing test path/function, resolved with Python AST. Only test-name traceability changed; all behavior, legacy identity, privacy and safety criteria remain. New portable fixture tests use the plan's original names for the three legacy record/identity/hash requirements.

Low dispositions: batch outcome updates have no captured-entry guard, but only two test callers exist and production settlement uses the guarded single update; broader batch API work is deferred. A newly stated price condition without validated instrument quote currency is visibly rejected; prior retained conditions with missing/incompatible closes remain unobserved. The boundary is preserved rather than inferring instrument currency from model prose or filing reporting currency. Docs-only source equivalence between d9ad53af and initial frozen da2b14cd was checked with zero-byte Git diff; corrected combined checks and exact-published-SHA CI will follow. The future-period rule matches original part-A ML3 wording, while future filed-date metadata remains forbidden by evidence validation; no filing schedule/date is invented.

The introduced unlinked direct-call link-loss Low was reproduced through real `store_decision`: a no-ID call replaced a linked pending entry and erased its publication link (`/tmp/r4-unlinked-red.log`). A minimal guard now preserves an established link when no replacement publication identity is supplied. Verified newer linked reruns still replace, and unlinked-only legacy behavior remains. Main focused checks:35 passed in2.28s; Ruff/diff passed. This is an in-scope identity correction, with no new workflow or user gate.

R2 is independently closed and integrated at exact staging `ccecd32599fe63754e2b2c4de3f17fac88139b2c`; CI run42465206951 passed all7 jobs. R4 will explicitly merge that confirmed staging into this existing feature worktree, combine only the overlapping historical-fixture version mappings, then run corrected combined focused/native/full checks before actual Fable closure. No reset or silent rebase is planned or performed.

Original independent report below is immutable audit output with its stated frozen-only limitations, not a new builder scope or an independently rerun test claim.

```json
{
  "base_commit": "78e3611ffb3fd6d8672acc2c15f54489cc258ae6",
  "head_commit": "da2b14cd5bade8d7c23b0e3deb7fae2181158d0d",
  "requested_model": "~anthropic/claude-fable-latest",
  "served_model": "~anthropic/claude-fable-latest",
  "status": "completed",
  "actual_turns": 52,
  "reviewed_files": [
    "docs/reviews/2026-11-08-memory-continuity-baseline.json",
    "docs/reviews/2026-11-08-memory-continuity-runtime.json",
    "docs/reviews/2026-11-08-memory-continuity-source-excerpts.json",
    "docs/reviews/2026-11-08-memory-continuity-verification.json",
    "docs/reviews/2026-11-08-memory-continuity.md",
    "docs/reviews/memory-continuity-proof.py",
    "docs/superpowers/plans/2026-11-07-tradingagents-workflow-gap-closure-plan.md",
    "tests/test_build2_continuation_proof.py",
    "tests/test_checkpoint_resume.py",
    "tests/test_memory_pending_replacement.py",
    "tests/test_publication_graph.py",
    "tests/test_review_memory_backtest.py",
    "tests/test_thesis.py",
    "tests/test_thesis_condition_kinds.py",
    "tests/test_thesis_graph_roles.py",
    "tests/test_thesis_integration.py",
    "tradingagents/agents/managers/portfolio_manager.py",
    "tradingagents/agents/output_validation.py",
    "tradingagents/agents/schemas.py",
    "tradingagents/graph/trading_graph.py",
    "tradingagents/memory/log.py",
    "tradingagents/memory/settlement.py",
    "tradingagents/memory/thesis.py"
  ],
  "summary": "Audited the frozen R4 memory-continuity build (base 78e3611f \u2192 head da2b14cd, 23 changed paths) strictly from the provided request.json. The implementation is substantively sound and matches approved D2 and the R4 requirements: same-day reruns atomically replace pending memory entries under the existing file lock with publication-ordered selection (latest directional published record) under the shared publication lock; settled entries and lessons are immutable, settlement carries an expected-entry identity guard wired into the production pass, and idempotent retries leave bytes untouched. The three-kind condition schema (metric/price_level/event) preserves exact legacy metric serialization and measurement identity (no 'kind' key persisted for metric; identical Decimal tuple ID normalization), rejects invalid conditions with disclosed reasons, observes price conditions only against validated currency-matching completed closes, leaves events as open unobserved questions, renders prompts as plain text with escaping deferred to HTML export, and advances the checkpoint signature (advisory_thesis=3) so metric-only checkpoints cannot resume into the new contract \u2014 each proven by new or updated tests visible in the diff. Findings: one medium (plan checkboxes [x] reference nonexistent test names, and the legacy-hash/kind-less-load guarantees are carried only by the private non-CI proof rather than committed sanitized fixtures) and five lows (unguarded batch_update_with_outcomes race, new price conditions dropped when no validated quote exists, link-severing replacement for unlinked direct API callers, receipts attaching to d9ad53af rather than HEAD, and the documented filing-date-vs-period-end deviation). Nothing found contradicts the builder's claims; staging integration, R2 merge, and combined acceptance remain outstanding as the builder discloses.",
  "limitations": [
    "Static audit of the single frozen request.json only: no code execution, no test reruns, no repository/filesystem/network access; all pass counts, hashes and proof outputs are builder-attested receipts, not independently reproduced.",
    "The frozen requirements blob concatenates listed files without path headers; attribution relies on the builder-supplied path-to-lines map in the verification JSON and content recognition, so file-boundary attribution carries residual uncertainty.",
    "Private-store proofs (9 publications, 32 legacy condition IDs/aliases/hashes, the 09:10/16:41 UUID replay) reference local paths and a private baseline manifest that are outside the frozen evidence and cannot be verified here.",
    "Receipts for the full suite (3,468 passed) and both native proofs were produced at commit d9ad53af; the three subsequent commits to HEAD da2b14cd are described as docs-only but this could not be confirmed from the frozen diff alone.",
    "Unchanged modules (publication, settlement internals, price observation, files locking) were reviewed only as frozen HEAD text for interaction with the diff; no independent re-audit of their internals is claimed.",
    "Staging CI, R2 integration/merge, and combined acceptance are explicitly outstanding per the builder's own review document and were not assessed."
  ],
  "findings": [
    {
      "severity": "medium",
      "title": "Plan acceptance checkboxes marked [x] cite test names that do not exist at HEAD; legacy publication hash/kind-less-load guarantees rest only on the private non-CI proof script, with no committed sanitized legacy-record fixture test",
      "path": "docs/superpowers/plans/2026-11-07-tradingagents-workflow-gap-closure-plan.md"
    },
    {
      "severity": "low",
      "title": "batch_update_with_outcomes lacks the expected_entry identity guard, retaining the stale-lesson-attaches-to-rerun race R4.1 fixed for the single-update path (test-only callers at HEAD, but exported API on the same class)",
      "path": "tradingagents/memory/log.py"
    },
    {
      "severity": "low",
      "title": "Newly stated price_level conditions are rejected ('stated but not retained') whenever the run lacks a validated price observation, so a validly stated condition is not carried forward, in tension with R4.2's carry-every-condition goal (disclosed on card)",
      "path": "tradingagents/memory/thesis.py"
    },
    {
      "severity": "low",
      "title": "store_decision called without a decision_id can replace a publication-linked pending entry for the same day, severing the memory-to-publication link for direct API callers (graph flow itself always resolves a linked latest record first)",
      "path": "tradingagents/memory/log.py"
    },
    {
      "severity": "low",
      "title": "Full-suite pytest and native-proof receipts attach to candidate d9ad53af, not frozen HEAD da2b14cd; the trailing commits are builder-described as docs-only and were not independently confirmable from the frozen diff",
      "path": "docs/reviews/2026-11-08-memory-continuity-verification.json"
    },
    {
      "severity": "low",
      "title": "R4.3 'not yet reported' rule keys off measurement period end vs analysis date rather than the plan's 'filing date' wording; deviation is documented and justified by strict evidence validation, flagged by the builder for reviewer assessment",
      "path": "tradingagents/memory/thesis.py"
    }
  ],
  "classification": {
    "declared_build_size": "large",
    "effective_build_size": "extra large",
    "escalation_reasons": [
      "Frozen scope changes more than 10 files or more than 500 lines."
    ]
  },
  "progress": {
    "observed_events": 4587,
    "last_activity_at": "2026-11-08T08:50:12.377Z",
    "last_activity_kind": "stdout"
  },
  "ledger": {
    "soft_budget_usd": 50,
    "hard_budget_usd": 80,
    "soft_turn_limit": 100,
    "turn_limit": 160,
    "wall_clock_limit_minutes": 360,
    "actual_cost_usd": 4.307448000000001,
    "actual_elapsed_ms": 1588616,
    "soft_limit_reached": false
  },
  "stop_reason": "reviewer_completed"
}
```

Explicit R2 integration into R4: fresh fetch confirmed canonical staging `ccecd32599fe63754e2b2c4de3f17fac88139b2c` with all7 exact-SHA CI checks passed, production unchanged `9ade69bf155d1b25699d3aecfff3c1b07752aff0`. R4 correction parent is `52718fa206cb2be0ec985bb9535451c6735ecff6`. A real merge of confirmed staging into this feature branch, preserving both histories, had one textual conflict in the historical Build2 offline signature adapter. Resolution preserves all original-only mappings: source brief5→3, advisory thesis3→2, document search3→2, follow-up3→2, and removal of the old operational-delivery token only inside the historical fixture. Production retains advisory_thesis3/document_search3/document_followup3, so it does not resume old checkpoints. No application-source conflict occurred, and no reset/rebase was used.

Combined focused checks on this merge content:60 passed,2 unavailable-private-input tests skipped in13.45s (`/tmp/r4-r2-combined-focused.log`); complete default Ruff and diff check passed. Original source/budget/pending-node/role assertions in the historical native continuation are unchanged and pass. Full suite and fresh affected native proofs on the committed combined candidate remain next; no current independent material closure is claimed yet.

Corrected combined stable source **`8ad5e1727deefa15d3f7b4c2da3e535da2ed7074`**, with exact accepted R2 staging `ccecd32599fe63754e2b2c4de3f17fac88139b2c` as an ancestor: complete default pytest **3,505 passed,10 skipped,1 deselected,25 warnings,100 subtests passed in71.01 seconds**, terminal exit0. Both native proofs were repeated on this exact commit, terminal success JSON and empty stderr. The retained continuity proof loads all9 baseline publications/evidence, matches32 legacy IDs/aliases/serialization hashes and27 file hashes, leaves original cfae state hash unchanged and links one pending memory entry to latest cfae publication/thesis. The actual CLI/compiled graph proof completes4 attempts, interruption/resume, save failure/retry,3 distinct immutable published runs and reopened reports, with no secret found. Model/vendor boundaries remain scripted/recorded; TCP connection entry points are patched, not a generic network sandbox.

The current native receipts, source/test/proof OIDs, full-suite log hash, exact BASE golden-fixture validation,14 resolved acceptance references and all7 accepted R2 CI results are in adjacent runtime/verification JSONs. Initial d9ad53af receipts remain separately labelled historical. This is one complete3505-pass run, not an aggregate. Current full source/test/proof objects will be checked unchanged at the docs-freeze HEAD.

Independent R4 closure is required and remains pending. Closure audit base is the exact accepted R2 staging commit; it covers the full resulting R4 delta, original findings/dispositions and current corrections in this same worktree. To bound the packet, the unchanged long `tests/test_memory_log.py` body is omitted from closure context (supplied to initial audit); current replacement/race/partial/idempotence/unlinked-link regressions, production log/settlement source and golden legacy fixtures are supplied in full. No original private input payload or missing historical pass is substituted. Production and whole Goal acceptance remain separate.
