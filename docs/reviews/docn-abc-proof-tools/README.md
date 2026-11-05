# DOCN bounded live CLI proof runner

This runner invokes the real `cli.main` in the task worktree. It uses the existing
shared ledger `results/docn-abc/cost_ledger.jsonl` and process lock
`results/docn-abc/runner.lock`. Different output names cannot reset spending or
attempt limits. No product source or saved user settings are changed.

## November 5 authorized extension

The retained first seven attempts committed **$18.410925** at the conservative
maximum token rates. The approved extension permits **four additional attempts**,
**11 lifetime attempts**, including retries, with **at most two Deep attempts**.
Prior attempt records without a depth field count as Shallow. The cumulative
live ceiling is fixed at **$68.410925**: the lesser of the original $70 live
allocation and $18.410925 plus the newly approved $50. The separate audit budget
is outside this runner. Codex usage is separate.

Before another paid attempt, the runner verifies that the seven-attempt baseline
and its committed amount remain in the ledger. It never rewrites old entries or
resets reservations. Failed/unknown paid requests retain their full reservations.

## Invocation and isolation

From the worktree root, choose an unused name and the preflight-qualified issuer:

```bash
mkdir -p results/docn-abc/live-08
.venv/bin/python docs/reviews/docn-abc-proof-tools/live_cli.py --execute --run-name live-08 --ticker DOCN --analysis-date 2026-11-05 --depth deep > results/docn-abc/live-08/cli.stdout.log 2>&1
```

`--depth shallow` sets **1 debate and 1 risk round**; `--depth deep` sets **5 and
5**. Both use four tool rounds per analyst, OpenRouter
`openai/gpt-6.1-terra-pro` in both tiers, 65,536 maximum completion tokens and zero
SDK retries. Symbols must be bounded market identifiers; dates must be canonical
and no later than today. The analysis timezone is explicitly `America/Denver`.

The normal CLI receives `--ticker <symbol> --date <date> --analysts
market,social,news,fundamentals --save --html --show --checkpoint`. Results,
cache/checkpoints, memory and preferences live under the new run folder.
Credentials are loaded privately from the original TradingAgents `.env`; only
`OPENROUTER_API_KEY` and `SEC_EDGAR_USER_AGENT` enter the process. Implicit dotenv
loading is disabled before application import.

Each execution claims its folder exclusively. A used ledger name, prior run
claim, report, cache, pricing or source manifest is rejected instead of
silently overwritten. A newly prepared folder may contain `cli.stdout.log`,
explicit seed receipts `seed-continuity.json` / `engineering-seed.json`, copied
`results/publications/**`, and `memory/trading_memory.md`. Symlinks are rejected.
Seeds are not execution evidence and must retain their origin and historical or
prospective-engineering labels. Retries use another unique run name and count
within the same lifetime limit; the runner does not erase prior proof artifacts.

## Cost guard and runtime evidence

Before each attempt, a free public OpenRouter catalog lookup checks the exact
model's base, long-prompt and cache rates. The runner rejects prices above $2.50
per million input tokens or $7.50 per million output tokens, unbudgeted fees and
unexpected endpoints/models. Serialized request bytes plus a framing allowance
and the output cap supply a conservative reservation. A trustworthy nonstream
usage response replaces that reservation with maximum-rate token usage; errors,
streams and missing usage retain the original bound. The ledger contains counts
and costs, not prompts or credentials.

`source_sha256.json` retains Git HEAD, Python/package paths, actual requested
ticker/date/depth/timezone, nonsecret model/round/cap settings and source hashes.
A transparent check on the real CLI configuration saves `actual_run_config.json`
and rejects a different debate/risk depth, model, backend or output/retry limit
before graph construction. `pricing_snapshot.json` retains public rate evidence.

A proof-only observer forwards each `TradingAgentsGraph.stream_run` item
unchanged and saves `executed_rounds.json`, including observed research/risk
count sequences and maxima. Expected node turns are **2 research / 3 risk** for
Shallow and **10 / 15** for Deep. It records completion or the exception type,
including partial counts on failure. These are observed graph counts; config
alone is not evidence that all rounds ran. This observer retains no prompt text.
The attempt-end ledger records request count, committed cost and whether the
original CLI preferences still match their initial hash.

## Offline checks

```bash
.venv/bin/python -m pytest -q docs/reviews/docn-abc-proof-tools/test_live_cli.py
.venv/bin/python docs/reviews/docn-abc-proof-tools/live_cli.py --ticker DOCN --depth deep --analysis-date 2026-11-05
```

The second command validates arguments only. It does not import application
configuration, load credentials, claim a directory, start the CLI or spend money.
A paid attempt requires `--execute` and all existing guards to pass.
