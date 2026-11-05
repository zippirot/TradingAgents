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

Remaining first-slice work: compact accepted-evidence presentation, separate
bounded narrative, readable prior decisions, integrated negative/positive tests,
and one authorized real CLI proof. No first-slice acceptance or full-suite success
is claimed. No paid calls have run under this Goal.

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

Final independent audit, full build checks, remaining A/B/C implementation and
all runtime acceptance remain outstanding.
