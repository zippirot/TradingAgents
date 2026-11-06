# A7 comparison runner: offline contract

`pilot.py` provides the isolated A7 comparison protocol. It makes no network or
model calls. The six paid CLI runs and six blind reviews are **not authorized**
by any approval for the earlier Part A or Part B proof.

## Fixed experiment

`SLOTS` is `A, B, B, A, A, B`, with two research and risk rounds and all four
analysts. A uses `openai/gpt-6.1-terra-pro` for both tiers. B uses
`openai/gpt-6.1-sol` quick and `anthropic/claude-opus-5.5` deep. A manifest
must name its ticker, analysis date, UTC cutoff, source and prompt versions,
tool and context caps, reviewer model and exact settings, and all eight frozen
source/starting-state files with SHA-256 hashes. The reviewer is named in the
separate A7 `Approval`; no model or budget default grants spending authority.

Use a task-specific ledger and result directory. `PilotRunner.run_slot(slot,
execute_run)` claims each slot durably before invoking the callback. A failed
slot remains consumed. The callback receives `BudgetGuard`, must reserve before
each paid request and settle only from validated provider usage, and returns
the saved state, actual run scope, common and starting-state hashes, peer
request hashes, model-call count, cost and completion flag. The runner checks
these against the manifest and request ledger; it refuses duplicate launches.
Unknown costs retain their full reservation. SDK retries must be zero. The
adapter must not use a different retry layer or replace a failed attempt.

`FrozenSourceGateway.common(domain)` replays retained bytes and rechecks their
hash. `FrozenSourceGateway.peer(ticker, cutoff_utc)` captures a new peer's raw
response once through a supplied cutoff-bound callback, then replays identical
bytes for that request in every run. Its `request_hashes` go in the run result.
There is no network fallback for uncaptured requests. All runs must share the
same gateway peer directory, but have separate results, cache, memory and
preferences. Each starts from the same frozen memory and prior publication.

After six complete runs, `PilotRunner.run_reviews(review)` creates six opaque,
shuffled payloads, writes a private mapping, and claims each review before its
callback. The callback gets only retained evidence, analysis and debates plus
the fixed rubric and a review-only guard. It returns a score, findings, exact
reviewer model/settings and settled cost. A failed review is not relaunched.
`live_adapter.review_saved_output()` is the guarded HTTP callback: it sends one
nonstream OpenRouter JSON request for the approved reviewer at temperature 0
and 4,096 output tokens, validates an integer 0–5 score and bounded findings,
and requires settled provider usage. Reasoning is left at the provider default
and its observed usage is retained in the wire ledger. Pass this function through
a callback that supplies the explicit reviewer model, key, settings and wire
guard; no review model or credential is inferred from product preferences.
The mapping is returned only after all six scores are saved. `summarize_runs`
reports per-run primary metrics, min–max spreads and pilot-only measure
assessments. It never produces a composite winner; incomplete/confounded
results are marked uncontrolled. Own-audit counts are not ranking metrics.

## Live CLI adapter and paid-execution boundary

`live_adapter.py` supplies the real CLI execution boundary. `CliSpec` fixes
models, depth and caps; `configure_isolated_env` and `verify_cli_config` set
and check actual CLI settings without changing saved preferences;
`install_starting_snapshot` copies fixed memory and prior-publication files;
`FrozenSourceCapture` writes request-keyed source maps before model runs;
`FrozenVendorReplay.installed()` patches the CLI's source entrypoints and
rejects any request missing from frozen maps; `installed_http_guard()` wraps
both HTTPX client generations before model requests leave the process;
`execute_cli()` requires a prior `ExecutionClaim` from the separate proof
ledger or approved A7 slot, then runs `cli.main` under all those hooks. The HTTP guard accepts
only exact OpenRouter chat-completions requests, approved model IDs, a fixed
output cap and no paid add-ons. It reserves a per-request upper bound from
serialized byte length, framing, the full output cap and **supplied** route
rates. It settles only a response with matching model, valid usage and actual
provider cost. Unknown or failed costs stay reserved. The separate
`ProofAttemptLedger` enforces the approved $10 maximum across at most one Part
A and one later explicitly authorized Part B attempt; it reads no older proof
ledger. There is no CLI entrypoint with implicit execution or approval.

Each execution claim is consumed once before CLI startup. `CliSpec` carries
the fixed A7 analysis and market observation cutoffs; the latter is applied at
graph state creation and checked in the saved state. The config is rebuilt
after isolated environment setup, so earlier imports cannot reuse stale
defaults. Isolation disables dotenv loading and moves yfinance's cache into
the run workdir before product imports and source fetches. The Part A/B live proof uses real bounded sources and therefore
passes `source_replay=None` with `allow_unfrozen_sources=True`; an A7 comparison
requires `FrozenVendorReplay` and a network gate that blocks unmatched sockets
and curl requests. The real CLI is expected to exit through Click with status
0; the adapter then reads its flat `full_states_log_<date>.json` and verifies
the observed rounds, model calls, four analysts and audit record.

Each frozen vendor domain file is a JSON object mapping
`manifest_hash({"name": function_name, "args": arguments, "kwargs": keyword_arguments})`
to the retained JSON response value. For example, price history, indicators
and verified snapshots live in `prices_indicators`; analyst news/social/tool
responses live in `news_social`; SEC and consensus calls use their named
domains. Memory is raw Markdown bytes. Prior publication is a JSON object
`{"files": {"records/<name>.json": "<base64 bytes>", ...}}`. Peer captures
are separate raw JSON responses from the existing `_fetch_peer` path, keyed by
ticker and the fixed UTC cutoff, then replayed for the same request.

`conservative_route_rates(metadata, model_ids)` computes rate caps over every
served endpoint, long-context tier and cache-write variant in retained provider
metadata. `resolved_model_ids` lists exact IDs and dated aliases from those
same endpoints. Supply both outputs explicitly to the wire guard; it accepts
no silent model substitution. Metadata must be refreshed before the paid run.

The historical `docn-abc-proof-tools/live_cli.py` fixes Terra Pro, depths 1/5
and an older budget. Do not use its budget authority here. Before paid use,
the primary task must prepare and verify the complete source maps; inspect
for any source path outside the patched entrypoints; provide a cutoff-bound
new-peer capture callback; refresh account usage and exact provider route
prices; name the common reviewer and settings; compute the whole six-run plus
six-review budget including failed calls; and obtain separate A7 spending
approval. `build_pilot_receipt()` turns `execute_cli()` output into `run_slot`'s
required saved-state receipt (including actual depth/analyst counts, resolved
provider, reasoning/cache/truncation observations, source and starting-state
hashes). Offline tests run the actual CLI and graph with scripted model calls,
fake HTTP responses, and isolated source-capture/replay workdirs. They cover
both an unmapped issuer and a synthetic mapped DOCN filer with complete
accounting inputs, quarter history, default and newly proposed peers, and an
unavailable consensus row. These fixtures do not prove the private DOCN source
package or real provider response behavior. No paid request occurred.
