# TradingAgents: case stability before Part B (plan)

Date: 2026-11-10. Approved by the user the same day ("1 yes / 2 ok / 3 agree").

## Why
Run 36c26c9d (12:50, after Part A) priced the same evidence 28% higher than run 7822a890 (11:00): the
analyst anchored its multiples on a different reference (8.19x trailing instead of 4.67x on 2027 revenue)
and moved all three multiples up by a third. The rating stayed Underweight with a weighted value above
the close and no reason was required. The valuation has no stable anchor between runs.

## What is built
1. **Earlier cases carried forward.** The fundamentals analyst is shown its own cases from the last
   decision and the filings retained since, and is told to keep each value unless a new fact changes it
   and to name that fact. Read from saved records; no model call. When cases change with no new filing,
   the "since the last decision" block says so to the manager and the reader.
2. **Rating check on the return gap.** Inside the existing 10% band, a bearish rating on accepted cases
   that return more than the required return (or a bullish rating on cases that return less) must give a
   reason, through the existing single resubmission.
3. **What a flag means.** A case named by an accepted audit finding that corrects another role's
   statement about it is described that way, and is not counted or worded as a disputed case.

## Decisions recorded
- The starting point is the 12:50 case set (6x / 4x / 8x), which is the last publication.
- Part B stays built and parked until a run on stable cases scores valuation at 7 or better.

## Adjustment made at build time
The plan as described to the user said an unexplained change would be "sent back once". That would add a
paid analyst call and a second correction path to the replay logic. Built instead: the instruction in the
analyst's existing prompt, plus the plain label when cases change with no new filing. If the next run
still moves the cases without a new fact, the send-back is the next step.

## Limit
This makes runs consistent, not correct. The 6x / 4x / 8x multiples remain judgment.

## Estimates
- Build size: small.
- Recommended model: Claude Sonnet 5.5 (`claude-sonnet-5-5`), medium effort; narrow changes with clear checks.
- Wall-clock: 2 to 3 hours including the independent audit.
