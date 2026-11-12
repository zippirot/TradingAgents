# Portfolio Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft, written 2026-11-11. Not approved, not started. Lives outside the repository until approved.

**Goal:** Turn the single-stock analyst into a portfolio tool: run the existing analysis over the user's holdings plus a watchlist, then produce one review that says what to do with each stock (Level 1, direction) and, separately, how much (Level 2, dollar amounts, work in progress).

**Architecture:** The existing per-stock run is not changed. A new batch command runs it once per ticker. A new review step is plain code with no model call: it reads the latest saved rating for each ticker from the existing decision record store, the user's portfolio file (positions, watchlist, limits) and a completed close per ticker, and prints two separate sections. Level 1 never depends on Level 2.

**Tech stack:** Python 3, pydantic, typer, pytest, ruff. No new dependency.

**Spec:** The decisions recorded in the next section (agreed in the "Tauric - How it works" session on 2026-11-11). There is no separate design file.

**Repository:** `~/Documents/ChatGPT/Tauric/TradingAgents`, GitHub `zippirot/TradingAgents`. Base: `origin/staging` at `95bfb14e`. Build in a new worktree `~/Worktrees/portfolio-review`, branch `claude/portfolio-review-20261111`.

## Estimates

| Item | Estimate |
|---|---|
| Build size | medium |
| Recommended model | Claude Opus 5.5 (`claude-opus-5-5`) |
| Reasoning effort | medium |
| Wall-clock | 3 to 5 hours of active build and verification |
| Codex credits | not applicable; this plan is written for Claude Code |

Reason for the model and effort: the work is deterministic arithmetic with clear contracts that tests can check fully, but it produces money figures, so it should not go to the cheapest model. The model choice is an engineering judgment, not a measured comparison.

## Decisions already made by the user

1. The review covers holdings plus a watchlist of candidates.
2. Limits (maximum per stock, maximum per sector, minimum cash) live in the portfolio file. The user enters the numbers there, never in chat.
3. Two separate levels. Level 1 is direction only and is built first. Level 2 is recommended dollar amounts, shown as a separate follow-up section and labelled as a work in progress.

## Defaults chosen in this plan (change before approval if wrong)

| # | Choice | Main alternative rejected |
|---|---|---|
| D1 | The watchlist lives in the same portfolio file, as a list of tickers. | A separate watchlist file. |
| D2 | A stock not held is a "Buy" only when its rating is Buy or Overweight. A not-held stock rated Hold gets "No action". | Treating Hold as "buy up to standard weight", which is what the rating scale means for a held stock. |
| D3 | Ranking is by rating first (Buy, Overweight, Hold, Underweight, Sell), then by the largest shortfall against target. | Ranking by expected return from the case weights, which are uncalibrated. |
| D4 | When a rating and a limit conflict, the review says so in words, for example "Hold (at position limit)". It never silently caps. | Silent capping. |
| D5 | A rating older than 30 days is still used but flagged "stale". The age is one field in the limits block. | Dropping stale ratings. |
| D6 | The batch command skips any ticker that already has a rating newer than the stale age, and lists what it will run before starting. It does not ask for a second confirmation. | A confirmation prompt per ticker. |
| D7 | Short positions (negative quantity) are listed as "short position, not reviewed". | Extending direction rules to shorts. |

## Global Constraints

- The per-stock run, its prompts, its default models and its default depth are not changed.
- The review makes no model call and costs nothing to run. Only the batch command spends money, one full analysis per ticker.
- Privacy: review output is written only under the local results folder. Limits, watchlist, positions and amounts are never written to a publication record and never enter a run's agent prompts.
- Portfolio fingerprints must not change for any existing file. `tests/test_portfolio_sizing.py` pins `8deac4f58a71`; the new fields are excluded from `fingerprint()` and from `inputs()`.
- Every figure in the review is labelled as arithmetic on the user's file, "not an order". The tool places no orders.
- No new gates, prompts or confirmations beyond what this plan states.
- Tests run with `~/Documents/ChatGPT/Tauric/TradingAgents/.venv/bin/python -m pytest -q -p no:cacheprovider -W ignore` and `-m ruff check .` from the worktree. Each task writes its failing test first.
- Never read or print the user's real `~/.tradingagents/portfolio.json` during the build. Use `~/.tradingagents/portfolio.template.json` or test fixtures.
- No merge, push, install, production promotion, paid model run or worktree removal without the user's explicit approval.

## Review Focus

Inputs the decisions imply but that are easy to miss. Each has a test in the task named.

1. A large company's latest record is REVIEW (no rating) until the large-filer build lands. The review must show "No rating (analysis stopped at REVIEW)" and keep going. Task 2.
2. Position market values plus cash do not agree with `portfolio_value` in the file. The review states both figures' basis and uses `portfolio_value` for weights, with a one-line warning when holdings alone exceed it. Task 3.
3. A ticker has no completed close, or its currency differs from the file's. That ticker is listed with the reason; the others are still reviewed. Task 3.
4. Sector is unknown for a ticker. It is excluded from the sector limit and the review says so. Task 3.
5. Funds run out part-way down the buy list. Level 2 shows the unfunded remainder with the reason instead of overspending or dropping the row. Task 4.

## File structure

| File | Responsibility |
|---|---|
| `tradingagents/portfolio.py` (modify) | Portfolio file model: add watchlist, limits, optional sector per position. |
| `tradingagents/portfolio_review.py` (create) | Pure functions: latest rating per ticker, Level 1 direction, Level 2 amounts, rendering. No network, no model. |
| `cli/review.py` (create) | Gathers inputs (records, closes, sectors), calls the pure functions, prints and saves the review. |
| `cli/batch.py` (create) | Runs the existing analysis once per ticker with one set of answers. |
| `cli/main.py` (modify) | Registers the `review` and `batch` commands. |
| `cli/run.py` (modify) | `run_analysis` accepts preset selections so a batch asks the setup questions once. |
| `tests/test_portfolio_review.py`, `tests/test_portfolio_batch.py` (create) | Tests. |
| `LOCAL_SETUP.md`, `~/.tradingagents/portfolio.template.json` source in repo (modify) | How to fill in watchlist and limits; how to run. |

---

### Task 1: Portfolio file accepts watchlist, limits and sector

**Files:** modify `tradingagents/portfolio.py`; test `tests/test_portfolio_review.py`.

**Interfaces, produces:**

```python
class Limits(BaseModel):
    max_position_weight: float | None  # gt 0, le 1
    max_sector_weight: float | None    # gt 0, le 1
    min_cash_weight: float | None      # ge 0, lt 1
    rating_max_age_days: int = 30      # gt 0

class Position:  # existing, add
    sector: str | None = None

class PortfolioContext:  # existing, add
    watchlist: list[str] = []
    limits: Limits | None = None
    def review_tickers(self) -> list[str]  # held tickers then watchlist, upper-cased, no duplicates
```

- [ ] Step 1: Write failing tests:
  - `test_existing_file_keeps_its_fingerprint_with_new_fields_present`: a legacy file plus `watchlist`, `limits` and a position `sector` has the same `fingerprint()` as without them.
  - `test_inputs_never_carry_watchlist_or_limits`: `"watchlist" not in ctx.inputs()` and `"limits" not in ctx.inputs()`.
  - `test_limits_reject_out_of_range`: `max_position_weight: 1.5` raises `ValueError` through `load_portfolio`.
  - `test_review_tickers_orders_held_then_watchlist_without_duplicates`.
- [ ] Step 2: Run them; expect failures on missing fields.
- [ ] Step 3: Add the fields; exclude `watchlist`, `limits` and position `sector` from both `fingerprint()` payload branches and from `inputs()`.
- [ ] Step 4: Run the new tests and `tests/test_portfolio_sizing.py`; all pass.
- [ ] Step 5: Commit.

### Task 2: Latest rating per ticker

**Files:** create `tradingagents/portfolio_review.py`; test `tests/test_portfolio_review.py`.

**Interfaces:**
- Consumes: records as returned by `tradingagents.memory.publication.scan_records(config)["records"]` (keys used: `ticker`, `requested_as_of`, `sequence`, `canonical_rating`, `evidence_status`, `run_id`).
- Produces:

```python
def latest_ratings(records: list[dict], tickers: list[str], today: date, max_age_days: int) -> dict[str, dict]
# per ticker: {"status": "rated" | "review" | "none", "rating": str | None,
#              "as_of": str | None, "age_days": int | None, "stale": bool, "run_id": str | None}
```

The latest record is the one with the greatest `requested_as_of`, ties broken by greatest `sequence`. A rating outside `portfolio.RATINGS` gives status `review`.

- [ ] Step 1: Failing tests: newest record wins over an older one; a same-day revision with higher sequence wins; latest REVIEW gives `status == "review"` even when an older Buy exists; no record gives `"none"`; a 31-day-old rating with `max_age_days=30` has `stale is True`.
- [ ] Step 2: Run; expect "function not defined".
- [ ] Step 3: Implement.
- [ ] Step 4: Run; pass.
- [ ] Step 5: Commit.

### Task 3: Level 1, direction

**Files:** modify `tradingagents/portfolio_review.py`; test `tests/test_portfolio_review.py`.

**Interfaces:**
- Consumes: `latest_ratings` output; `PortfolioContext`; `quotes: dict[str, dict]` (each as from `get_price_observation`, keys `close`, `session_date`, `currency`); `sectors: dict[str, str | None]`; `tradingagents.portfolio.sizing` for current and target weight.
- Produces:

```python
def direction_review(book: PortfolioContext, ratings: dict, quotes: dict, sectors: dict) -> dict
# {"rows": [{"ticker", "held": bool, "rating", "rating_status", "stale", "as_of",
#            "current_weight": str | None, "target_weight": str | None, "sector": str | None,
#            "direction": "Buy" | "Add" | "Hold" | "Trim" | "Exit" | "No action" | "Not reviewed",
#            "note": str, "rank": int | None}],
#  "sector_weights": {sector: str}, "cash_weight": str | None, "warnings": [str]}
```

Rules, in this order:
1. No usable close, currency mismatch, short position, or rating status `none` / `review`: direction "Not reviewed", note gives the reason.
2. Not held: "Buy" when the rating is Buy or Overweight, otherwise "No action".
3. Held, with a target weight (standard weight and `rating_weights` present): target 0 gives "Exit"; current below target by more than `AT_STANDARD_BAND` gives "Add"; above by more than the band gives "Trim"; otherwise "Hold".
4. Held, no target weight available: Buy or Overweight gives "Add", Hold gives "Hold", Underweight gives "Trim", Sell gives "Exit"; note says weights were not supplied.
5. Limit notes, using current weights only (no allocation): current weight above `max_position_weight` gives "Trim" with note "above position limit" whatever the rating; current weight at the limit turns "Add" into "Hold" with note "at position limit"; a sector at or above `max_sector_weight` turns "Buy" and "Add" in that sector into "Hold" (held) or "No action" (not held) with note "sector at limit"; unknown sector is excluded and noted.
6. Warnings: cash weight below `min_cash_weight`; holdings' market value above `portfolio_value`; any stale rating.
7. Rank: rows with direction Buy or Add, ordered by rating then largest shortfall to target.

- [ ] Step 1: Failing tests, one per rule above, with exact fixtures. Include all five Review Focus cases 1 to 4 (REVIEW record; holdings above `portfolio_value`; missing close and currency mismatch each leave other rows intact; unknown sector excluded and noted). Example:

```python
def test_top_rated_stock_at_position_limit_is_hold_with_a_reason():
    review = direction_review(book(max_position_weight=0.10, held={"AAA": weight(0.10)}),
                              {"AAA": rated("Buy")}, quotes("AAA"), {"AAA": "Technology"})
    row = review["rows"][0]
    assert row["direction"] == "Hold" and "at position limit" in row["note"]
```

- [ ] Step 2: Run; fail.
- [ ] Step 3: Implement `direction_review`.
- [ ] Step 4: Run; pass.
- [ ] Step 5: Commit.

### Task 4: Level 2, recommended amounts (work in progress)

**Files:** modify `tradingagents/portfolio_review.py`; test `tests/test_portfolio_review.py`.

**Interfaces:**
- Consumes: the `direction_review` result, `PortfolioContext`, `quotes`.
- Produces:

```python
def amounts_review(direction: dict, book: PortfolioContext, quotes: dict) -> dict
# {"status": "available" | "unavailable", "reason": str | None,
#  "rows": [{"ticker", "direction", "units": str, "amount": str, "resulting_weight": str, "note": str}],
#  "cash_before": str, "cash_after": str, "cash_floor": str}
```

Method, stated in the output:
1. Unavailable, with the reason, when `portfolio_value`, `cash`, a standard weight or `rating_weights` is missing.
2. Sells first: "Exit" sells every unit; "Trim" sells down to the lower of target weight and `max_position_weight`.
3. Funds available = cash, minus `min_cash_weight` times `portfolio_value`, plus sale proceeds; never below zero.
4. Buys in Level 1 rank order. Wanted amount = lower of target weight and `max_position_weight`, minus current weight. It is then capped by the sector's remaining room under `max_sector_weight` (counting earlier rows) and by remaining funds. Whole units, rounded down.
5. Any shortfall is kept on the row with its reason: "not funded", "partly funded", "capped by sector limit", "capped by position limit".
6. Level 1 rows are never altered by this function.

- [ ] Step 1: Failing tests: sells fund buys; cash floor is respected to the cent; funds running out leaves the lower-ranked row "not funded" with units 0 (Review Focus 5); sector cap partly fills a row; units are whole and rounded down; missing `cash` gives `status == "unavailable"`; the input `direction` dict is unchanged after the call.
- [ ] Step 2: Run; fail.
- [ ] Step 3: Implement with `Decimal` throughout.
- [ ] Step 4: Run; pass.
- [ ] Step 5: Commit.

### Task 5: Rendering and the `review` command

**Files:** modify `tradingagents/portfolio_review.py` (`render_review`); create `cli/review.py`; modify `cli/main.py`; test `tests/test_portfolio_review.py`.

**Interfaces:**

```python
def render_review(direction: dict, amounts: dict, *, fingerprint: str, generated: str) -> str   # markdown
def run_review(portfolio_path: str | None, as_of: str | None) -> Path                            # cli/review.py
```

`run_review` loads the portfolio (default path as the analysis does), reads records with `scan_records(DEFAULT_CONFIG)`, gets each ticker's close with `get_price_observation(ticker, as_of)`, takes sector from the position's `sector` or `get_company_profile(ticker).get("sector")`, calls Tasks 2 to 4, prints the markdown, and saves it to `<results_dir>/portfolio_reviews/<YYYY-MM-DD>-<HHMMSS>.md`. A failed price or profile fetch for one ticker becomes that ticker's "Not reviewed" reason. Damaged record files reported by `scan_records` are listed as a warning.

Output layout:
1. Heading with date, file fingerprint, and "arithmetic on your portfolio file; not an order".
2. Warnings.
3. **Level 1: Direction.** Table: ticker, held, rating and date (with "stale" where flagged), direction, note. No amounts.
4. **Level 2: Recommended amounts (work in progress).** Table: ticker, direction, units, amount, resulting weight, note; then cash before, cash after, cash floor; then the method in three lines. When unavailable, one line giving the reason.
5. A list of tickers with no rating, with the batch command that would produce them.

Command: `tradingagents review [--portfolio PATH] [--date YYYY-MM-DD]`.

- [ ] Step 1: Failing tests: the Level 1 section contains no currency amounts; Level 2 is a separate heading containing "work in progress"; a saved file exists under `portfolio_reviews`; nothing is written under `publications`; one ticker's price failure does not stop the review (monkeypatched fetchers).
- [ ] Step 2: Run; fail.
- [ ] Step 3: Implement.
- [ ] Step 4: Run; pass.
- [ ] Step 5: Commit.

### Task 6: The `batch` command

**Files:** create `cli/batch.py`; modify `cli/run.py`, `cli/main.py`; test `tests/test_portfolio_batch.py`.

**Interfaces:**

```python
def run_analysis(checkpoint=None, portfolio=None, flags=None, selections=None)   # cli/run.py: use given selections, skip the questions
def run_batch(book: PortfolioContext, tickers: list[str] | None, date: str | None, refresh: bool) -> dict
# {"ran": [ticker], "skipped": [(ticker, reason)], "failed": [(ticker, reason)]}
```

Command: `tradingagents batch [TICKERS] [--portfolio PATH] [--date YYYY-MM-DD] [--refresh]`. With no tickers it uses `book.review_tickers()`. It skips tickers whose latest rating is not stale unless `--refresh`. It prints the list to run and the list skipped, with one line stating that each run is a full paid analysis, then starts. The setup questions (models, depth, analysts) are asked once and reused; reports are saved without asking and not shown. One ticker failing is recorded and the batch continues. It ends by running the review.

- [ ] Step 1: Failing tests with `run_analysis` monkeypatched: three tickers produce three calls with the same selections apart from the ticker; a fresh rating is skipped and `--refresh` runs it; an exception on the second ticker still runs the third and lands in `failed`; an invalid ticker is rejected before any run starts.
- [ ] Step 2: Run; fail.
- [ ] Step 3: Implement.
- [ ] Step 4: Run; pass.
- [ ] Step 5: Commit.

### Task 7: Documentation and acceptance

- [ ] Step 1: Add watchlist, limits and sector to the repo's portfolio template and to `LOCAL_SETUP.md`, with the two commands and a note that Level 2 is a work in progress.
- [ ] Step 2: Full suite and `ruff check .`; both clean.
- [ ] Step 3: Real acceptance without spending: run `tradingagents review --portfolio <a fixture file listing DOCN and MSFT>` against the saved records on this machine. Expected: DOCN shows its latest saved rating and a direction; MSFT shows its saved state truthfully (a rating, or "No rating (analysis stopped at REVIEW)"); both sections render; the saved file exists. Record the output in the build record.
- [ ] Step 4: Write the build record `docs/reviews/2026-11-11-portfolio-review.md` with what was run and what was not (no paid batch run).
- [ ] Step 5: Commit. Report the exact commit. Stop; merge, push and install need separate approval.

## Out of scope

- Placing orders or connecting a broker.
- Correlation-based sizing, optimisers, Kelly sizing. These wait for a settled track record.
- Changing what a rating means, or any prompt in the per-stock run.
- A page or PDF for the review; markdown and the terminal only for now.
- Automatic re-runs on new earnings. The review only flags stale ratings.

## Dependencies and risks

- Large companies stop at REVIEW until the large-filer coverage build (`~/Worktrees/large-filer-coverage`) is finished and merged. Until then the review is truthful but thin for those tickers. The two builds touch different files and can proceed in parallel.
- No past call has settled, so nothing yet shows the ratings are right. Level 2 turns unproven ratings into precise-looking amounts; the "work in progress" label and the method note are the mitigation.
- Batch cost is roughly 2 to 3 million tokens per ticker at the default depth, less at Shallow. A ten-ticker batch is a material spend that the user starts themself.
- Sector comes from Yahoo's profile, which can be missing or coarse. The per-position `sector` field overrides it.
