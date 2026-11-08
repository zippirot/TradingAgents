# R5 observability acceptance record

## Authority and baseline

Governing requirements: `docs/superpowers/plans/2026-11-07-tradingagents-workflow-gap-closure-plan.md`, Build R5. Machine 2 worktree `/Users/zipp/.codex/worktrees/workflow-gap-r5/TradingAgents`, branch `codex/workflow-gap-r5`; exact fetched local/GitHub staging predecessor `8920ffac07d1063001291799e99963403955582a`. Preparation-only requirements commit `4a4c723f895501df232ad1a00c5dc1ffdfa37475`. No merge/push, installation, live-data mutation or paid product calls are authorized for this local code-build proof.

The native Goal is active. Its requested notifier key is `thread:01a1b86a-d32d-7852-a6ae-c06d24f933aa:goal:1794097364`; opt-in is enabled and both privacy-minimal dry-run bodies were verified. No incident/test push was sent; provider/phone delivery is not claimed.

## First vertical milestone

Actual CLI proof: `docs/reviews/operations-cli-proof.py`, run with the existing Python 3.12 environment from this checkout. Source prices copied read-only from the existing private DOCN CSV, with unchanged SHA-256 `de15f4df70171544b21842a43576111f01ccc0da75f67234e23a9a92c6fd869c`. All runtime writes went to the temporary root named in `2026-11-07-observability-early-runtime.json`. Sockets were denied and credentials replaced with a synthetic sentinel.

The actual `cli.run.run_analysis` → `TradingAgentsGraph` → compiled graph → publication/memory → saved-state → report-export path passed normal completion, interactive save failure/retry and interruption/resume. Four attempts; three distinct published runs and state archives; source unchanged; sentinel absent from retained files/output. New trace files were observed for 15 stages on complete fresh runs, nine stages in the interrupted attempt and seven stages in the resumed attempt; transcript contained a pointer per observed stage. Trace-file permissions were 0600, stored outside report exports.

This was an **early milestone**, not final R5 acceptance. The recorded runtime source fingerprint is `sha256:d4aa543d84cd4725a1f1f4dd1bf0269441523c74d65c5d29f932c9ac5d442e52`; later metrics corrections are not covered by that run. The provider-boundary `OfflineModel` does not emit model callbacks; this native run proves stage tracing, while real LangChain model callback events are separately exercised using `FakeListChatModel` in `tests/test_attempt_trace.py`. No live-model/provider, complete DOCN filing acquisition, or controlled replay is claimed by this receipt. Split actions are explicitly simulated as zero, as in the predecessor proof.

## Implemented and focused verification

- R5.1: reproduced LangGraph's actual `map_task_result_writes` envelope. Before correction, three ToolMessages became the literal `$writes` key. Stream extraction now unwraps multi-write message batches in order without changing the original objects or graph state.
- R5.2: reproduced sanitized run logs omitting both Trader and TimeoutError. Structured warnings now carry separately allowlisted diagnostic fields; arbitrary arguments and exception messages remain redacted. The sentinel/prompt exclusion test passes.
- R5.3: saved/reopened state now retains `past_context` and `memory_note`. Actual node wrappers emit transcript pointers identifying stage, attempt, run and returned state keys. They do not duplicate raw node state into the transcript.
- R5.4: reproduced ignored usage from a failed attempt's returned LLMResult; callback accounting now accepts a genuine receipt on error and deduplicates a repeated receipt for the same call. Stored metrics explicitly identify `graph_only`; the existing rendered usage footer already discloses exclusion of the post-graph editorial summary. Missing usage remains unavailable/partial.
- R5.5: initial private attempt/stage tracing and model provenance are wired into actual CLI callbacks and node wrappers. Default-off, concurrent stage ordering, interruption/restart separation, secret exclusion and metadata-without-full-trace probes pass. Requested and actual returned model IDs remain distinct; unavailable actual identity is null. No retention service or database was added. Traces may be manually deleted by removing an attempt's `trace/` directory after evidence is no longer needed; report exports do not include it.

Observed red regressions: three logging/retained-state probes failed before their corrections; the graph-boundary metric and failed-attempt receipt probes also failed for their missing behavior. Trace probes initially could not import the new absent API, then passed against the implementation. Focused runs: 55 passed for stream/log/state/structured-agent suites; 40 passed for trace/operational/stream/log/state suites; 36 passed for token/run metrics, trace/log/stream suites. These are separate focused runs across development revisions, not one complete passing suite. The initial prepared-checkout baseline was 62 passed. Focused Ruff passed after import ordering correction. Final suite/source validation remains required.

Current combined milestone check: **133 passed in 3.01s** across token/run metrics, attempt tracing, run logging, stream publication, document-state replay, operational capture, structured agents and headless CLI tests. Full repository `ruff check .` and `git diff --check` passed. Log: `/tmp/workflow-r5-milestone-pytest.log`. This focused milestone is not the required final full suite or independent audit.

## Remaining acceptance

R5.6 controlled replay and pre-baseline snapshot isolation are **not implemented**. Before final acceptance, exercise source acquisition outside model tools, tool Command state effects/current call IDs, current candidate computations against frozen raw sources, and explicit mixed-input replay misses. Complete realistic tool failure/restart/privacy checks, repeat the full native path on the final candidate, run the required full pytest/Ruff checks, freeze a clean committed candidate, then run the required independent Claude Fable audit and verified gap closure through the repository executor. No independent audit has started and no final R5 acceptance is claimed.

The code-review graph reported zero indexed files for this checkout; important claims were checked directly against current source and the installed LangGraph multi-write producer. No graph coverage was assumed.
