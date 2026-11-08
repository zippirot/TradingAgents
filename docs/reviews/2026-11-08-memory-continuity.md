# R4 memory continuity build

In progress; independent acceptance, staging integration and whole Goal remain incomplete.

R4 starts from exact confirmed staging `78e3611ffb3fd6d8672acc2c15f54489cc258ae6` in `codex/memory-continuity`. R1 was accepted and all seven staging checks passed. The approved plan explicitly permits R2/R4 parallel worktrees after R1. R2 is undergoing its frozen independent audit. No reset or rebase has occurred; accepted R2 staging will be explicitly merged before R4 combined acceptance.

Baseline: 214 focused tests passed in 3.25 seconds. A disposable copy of the private publication store contains nine strictly loaded publications and their evidence, with 32 metric conditions. The baseline manifest records every file hash, legacy condition ID, aliases and serialized condition hash. The source store was read only and unchanged. See the adjacent baseline JSON for hashes and local evidence location; private payloads are excluded from committed evidence.

The pending-memory defect was reproduced with four failing behavior tests: a rerun retained the first publication; a delayed first projection overwrote latest-run intent; settlement lacked an identity guard. The implementation keeps replacement and settlement under the existing memory file lock and orders publication selection/projection under the existing publication lock. Settled lessons remain immutable. Evaluation primary flags are independent and unchanged.

The original REVIEW compatibility test expected the first pending Buy to survive a later Sell. Its pending-only expectation is updated to approved D2 (latest pending Sell); its assertions preserving both historical REVIEW entries remain intact. The surrounding settlement/memory checks passed after this adjustment.

Condition schema, PM output, persistence and next-run rendering are being verified together. Known metadata limitation: validated evidence disallows future filed dates/financial periods, so code may identify a future requested condition period without inventing a filing date; exact supported behavior and unavailable metadata will be recorded in final proof.

No phase-one product proof makes paid calls or writes production data. Audit calls use the separately authorized frozen executor within its existing caps. Amendment 1 host work remains R1/R3/Na; R4 introduces no new default horizon.

R4.1 implementation commit: `fb1ab03f` (final candidate still pending). The surrounding memory/publication/settlement/CLI checks passed 168 tests in 3.01 seconds (`/tmp/r4-memory-focused.log`). Additional threaded projection, actual-graph settled rerun and partial-tail replacement tests passed in a 15-test focused run. A process-only negative control disabled only the projection ordering lock: the threaded test then reproduced loss of the latest publication; the real lock passed. No source file was modified for this negative control.
