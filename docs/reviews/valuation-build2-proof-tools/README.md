# Valuation Build 2 + A3: Machine 2 proof operator

Use the task-local interpreter from the source checkout:
`RUNNER=docs/reviews/valuation-build2-proof-tools/live_cli.py`. Run
`.venv/bin/python "$RUNNER" --qualify` for local identity, dependency,
input and prior ledger fingerprints. No network or credentials are used.
Only the operator refreshes inputs, freezes the accepted candidate or starts a run.

1. After the independently reviewed source, runner and tests have been committed
   on the isolated candidate branch, create the private sibling directory
   `../private/build2-receipts/` (0700). Capture the current OpenRouter served
   endpoint metadata for both exact model IDs and the current key's usage and
   remaining limit into `reviewed.provider.json`. Retain the read-only HTTP
   observations privately. Never save API keys or request headers.
2. Provider JSON format (numbers illustrative; never use fixtures live):
   `{"observed_at":"<actual UTC ISO timestamp>","results":{"key":{"usage":"…","limit_remaining":"…"},"anthropic/claude-opus-5.5":{"endpoints":[…]},"openai/gpt-6.1-terra-pro":{"endpoints":[…]}}}`.
   Keep all actual endpoints and tiers; each includes its actual name and pricing
   (prompt, completion, cache overrides). The request bound charges worst-case
   input/cache pricing against serialized UTF-8 bytes plus framing and 16,384
   output tokens at the highest listed output price.
3. Review rates and prior history, then run `.venv/bin/python "$RUNNER" --freeze`
   once. It creates `../private/build2-candidate.json`; it does not claim a slot.
4. Before **each** attempt refresh account/endpoint data in
   `Build2-DOCN-N.provider.json` in the same directory (N = 1 or 2).
   Create `Build2-DOCN-N.session.json` with keys `session_date` (YYYY-MM-DD of
   latest completed NYSE session), `regular_close_utc`, `observed_at`,
   `nyse-calendar`, and `docn-chart`. Each of the last two is an object
   `{"url":"…","http_status":200,"retrieved_at":"…","path":"/absolute/path/to/retained/body","sha256":"…"}`.
   Use actual observations, post-close: official
   `https://www.nyse.com/trade/hours-calendars` and Yahoo
   `https://query1.finance.yahoo.com/v8/finance/chart/DOCN?interval=1d&range=1d`
   (query2 is also supported). The chart's regular session metadata confirms
   the exchange close time; it does **not** replace the actual CLI price. The
   saved canonical price may explicitly select an older valid completed close.
   Use an actual after-close weekday or the following weekend (Friday session);
   unqualified holiday or alternate source metadata needs investigation off-run.
5. Choose an explicit per-attempt cap based on reviewed rates, measured prior
   sends, current account headroom and remaining fresh authority. There is no
   mandatory $12 split. Two attempts together, including outstanding/unknown
   reservations, have at most $24. With private (0600) JSON credentials carrying
   OPENROUTER_API_KEY, SEC_EDGAR_USER_AGENT, FRED_API_KEY and ALPHA_VANTAGE_API_KEY,
   run `.venv/bin/python "$RUNNER" --run Build2-DOCN-1 --attempt-cap "$CAP" --credentials "$CREDS"`.
   Use a fresh process with no tracing/proxies or shared CLI configuration.
   Do not retry this command. A successfully claimed attempt counts even if
   credentials or CLI setup then fail. No automatic second attempt, third attempt,
   top-up or restart from checkpoints. If interrupted, preserve all files.
6. Inspect `../private/Build2-DOCN-1/` and `../private/build2-ledger.jsonl`,
   including the CLI state/reports, execution status, observed token coverage,
   unknown holds and independent feature assessment. An empty proposal is not
   feature proof. Establish why proof is incomplete before explicitly invoking a
   second attempt with its own refreshed receipt pair. Preserve all prior files.

For the remaining slot after the first completed, feature-incomplete run on
`0b81953`, leave the first candidate, reviewed provider file and ledger in place.
After the corrected descendant has been independently reviewed and committed,
place its fresh provider metadata in `../private/build2-receipts/reviewed-second.provider.json`
and run `.venv/bin/python "$RUNNER" --freeze-second`. This writes only the
exclusive second candidate receipt and checks the original terminal ledger
fingerprint. Requalify the clean source, then obtain the fresh slot-2 receipts
as in step 4. Launch once with `--run Build2-DOCN-2 --attempt-cap 12` and the
same explicit credentials argument. This uses the original ledger and retains
the full first-attempt exposure of $11.90770580, including $3.718112 unresolved.

### Approved checkpoint continuation

The continuation uses its own entry point, `continue_cli.py`. Its single claim
has a $12 limit and shares the original ledger under the newly approved $36
aggregate. The first two attempts committed $21.00409590, including $7.698176
in unknown reservations. The account headroom check also retains the linked
$12.037824 historical unknown holds.

1. On the reviewed clean Machine 2 commit, run
   `.venv/bin/python docs/reviews/valuation-build2-proof-tools/continue_cli.py --qualify`.
   It checks the approval, native resume qualification, terminal ledger bytes,
   prior model and source inputs, and the original application and CLI trees.
2. Capture fresh account usage/headroom and served endpoint rates/aliases in
   `../private/build2-receipts/Build2-DOCN-continuation.provider.json`, using
   the provider receipt shape above. The market session and price come from
   the original November 6 analysis.
3. Once, run
   `.venv/bin/python docs/reviews/valuation-build2-proof-tools/continue_cli.py --run --candidate "$REVIEWED_HEAD" --credentials "$CREDS"`.
   Use a private 0600 JSON file containing OPENROUTER_API_KEY. The claim precedes
   runtime creation and credential reading. The runner copies the checkpoint
   and input cache into `../private/Build2-DOCN-continuation/`, verifies the
   saved thread and pending Aggressive Analyst, and resumes with native graph
   input `None`. Only the ordered risk turns, audit and Portfolio Manager may
   send model requests. SDK retries stay disabled. The two existing bounded
   application fallbacks allow up to 13 sends under the same $12 cap.
4. Inspect the continuation's `continuation-result.json`, role entries in the
   shared ledger, CLI receipt, assessment and private reports. Callback coverage
   is partial across the process restart. Original settled usage, unknown holds
   and continuation usage are available in the ledger.
