# TradingAgents: weight stability (plan)

Date: 2026-11-10. Approved by the user the same day ("1 yes / 2 yes / 3 yes").

## Why
Run b9dde628 (13:47, on the case-stability build) kept the three cases unchanged, as intended, but the
manager's weights moved from 50 / 35 / 15 to 45 / 45 / 10 with no new evidence. The Underweight then
passed the return check by one point of weight. Weights were the next unanchored judgment.

## What is built
1. **Earlier weights carried forward.** The Portfolio Manager is shown the weights it gave each case in
   the last decision and told to keep each unless a new fact changes it, naming the fact. Read from the
   saved card; no model call. The reader sees both sets, and a change with no new filing is labelled.
2. **A flag means the case's own inputs.** A finding counts as disputing a case only when it quotes the
   case's own inputs. A finding about any role's statement, the analyst's narrative included, is
   described as a correction of that statement.

## Decisions recorded
- Reference weights are those of the latest publication (45 / 45 / 10).
- After this build, stop building on valuation; move to the evidence work (settlement check, scoring
  decisions against their own range, company screen). The lease and dilution model stays on hold.
- Part B stays parked.

## Limit
Consistent is not the same as correct: the carried weights are still subjective.

## Estimates
- Build size: small.
- Recommended model: Claude Sonnet 5.5 (`claude-sonnet-5-5`), medium effort; narrow change with clear checks.
- Wall-clock: 1 to 2 hours including the independent audit.
