# Portfolio review: build record

Plan: `docs/superpowers/plans/2026-11-11-tradingagents-portfolio-review-plan.md`. Branch `claude/portfolio-review-20261111`, from staging `4a65a981` (the plan named `95bfb14e`; staging had moved on by two commits that touch other files).

## What was built

- Portfolio file: `watchlist`, `limits`, and `sector` on a position. All three are left out of the file fingerprint and out of run state (the pinned fingerprint `8deac4f58a71` is unchanged).
- `tradingagents/portfolio_review.py`: latest rating per ticker, Level 1 direction, Level 2 amounts, rendering. No network, no model.
- `tradingagents review` (`cli/review.py`): free; saves under `<results_dir>/portfolio_reviews/`.
- `tradingagents batch` (`cli/batch.py`): the existing analysis once per ticker, setup questions asked once; `run_analysis` accepts preset selections.
- `LOCAL_SETUP.md` section and `docs/portfolio.example.json`.

## Choices made where the plan left room

- "At position limit" means within 5 percent below the limit (the same band used for "at standard"); above the limit is a Trim.
- A Trim sells whole units rounded up, so the position ends at or below its goal; purchases round down.
- A not-held stock rated Hold, Underweight or Sell is "No action" (plan default D2).
- A latest record of REVIEW is run again by `batch`, since it carries no rating.
- The repository had no portfolio template, so the example file is new. The user's own `~/.tradingagents/portfolio.template.json` was not changed.

## Verification

- Full suite: 4,723 passed, 10 skipped. `ruff check .` clean.
- New tests: `tests/test_portfolio_review.py`, `tests/test_portfolio_batch.py`.
- Real run, no spend: `tradingagents review --portfolio <made-up file: 60 DOCN held; MSFT and NVDA watched>` against this machine's saved records and live Yahoo closes on 2026-11-11. DOCN showed its saved Underweight and "Trim"; MSFT showed its saved Overweight and "Buy"; NVDA showed "No rating" with the batch command to produce it. Both sections rendered and the file was saved (then removed, since it described a made-up portfolio).

## Not run

- No paid batch run. `batch` is tested with the analysis replaced by a stub; its first real use will be the user's.
- The user's real portfolio file was not read.
