# DOCN bounded live CLI proof runner

Live attempt `live-01` is complete; current acceptance and spending are recorded
in `../2026-11-04-docn-gap-closure-progress.md`. The runner stores each attempt's
output under `results/docn-abc/<run-name>` (default `live-01`). Its shared cost
ledger and process lock are at `results/docn-abc/cost_ledger.jsonl` and
`results/docn-abc/runner.lock`, so different run names cannot bypass the budget.
It imports the real `cli.main` and invokes the real CLI flags, with a local HTTP
transport guard. No product source is modified.

From the worktree root, after review, run exactly:

```bash
mkdir -p results/docn-abc/live-01
.venv/bin/python docs/reviews/docn-abc-proof-tools/live_cli.py --execute > results/docn-abc/live-01/cli.stdout.log 2>&1
```

The command may be repeated for up to seven attempts total across run names.
`--run-name live-02` starts a separate output folder; each invocation, including
a checkpoint resume, counts as one attempt. The runner sets one research
debate round, one risk round, four tool rounds per analyst, OpenRouter
`openai/gpt-6.1-terra-pro` in both tiers, 65,536 maximum completion tokens,
and zero SDK retries. The CLI flags are `--ticker DOCN --date 2026-11-04
--analysts market,social,news,fundamentals --save --html --show --checkpoint`.

Credentials are read privately from the existing TradingAgents `.env`: only
`OPENROUTER_API_KEY` and `SEC_EDGAR_USER_AGENT` enter the process. The package's
implicit dotenv loader is disabled before import. Results, cache (including
SQLite checkpoints), memory log, and CLI preferences are routed to `live-01`.

The guard reserves a conservative per-request upper bound from serialized UTF-8
request bytes, an added chat framing allowance, and the 65,536 token completion cap using $2.50 per million input
tokens and $7.50 per million output tokens. It blocks a request that would
exceed the $70 cumulative ceiling. Successful nonstream responses with usable
token counts are settled; failures, missing usage, and streams keep their full
reservation. The ledger contains counts, token usage, and costs but no prompt
or credentials. The separate $30 audit budget is outside this runner.

Before each paid attempt, the runner reads OpenRouter's public model catalog,
checks the exact model's base and long-prompt/cache rates against those caps,
rejects unbudgeted per-request fees, and saves `pricing_snapshot.json` in that
run folder. Optional paid web search is blocked in serialized model requests.

`source_sha256.json` records Git HEAD, the Python executable and package path,
nonsecret model/round/cap settings, all tracked and untracked CLI/application/test
Python source, project test configuration, and runner file hashes.
The shared ledger records the original CLI preference file hash before the run
and whether it remained unchanged at the end. The CLI saves its own reports, message log, and
checkpoint state beneath `live-01` when executed.

Offline checks:

```bash
.venv/bin/python -m unittest discover -s docs/reviews/docn-abc-proof-tools -p 'test_live_cli.py' -v
.venv/bin/python docs/reviews/docn-abc-proof-tools/live_cli.py
```

The second command is a dry setup check and does not start the CLI or spend
money. A paid attempt requires the explicit `--execute` flag.
