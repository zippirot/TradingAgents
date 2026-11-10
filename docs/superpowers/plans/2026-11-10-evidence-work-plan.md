# TradingAgents: evidence work, Reddit key and arithmetic check (plan)

Date: 2026-11-10. Approved by the user the same day (Part D of the next-step plan; Reddit key support;
"1 yes ... yes" for the audit and the arithmetic check). The other-company source plan stays on hold.

## What is built
1. **Reddit key.** With `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` set, the Reddit search runs through
   Reddit's authenticated API (application-only, public posts). Without them, the public feed as before.
   The secret and token are never logged or recorded for replay.
2. **D2.** The scorecard places each settled close at 21 and 63 sessions against the range the decision
   itself accepted and against its weighted value, both carried to the exit date at the decision's stated
   required return. Same sample rules as the existing scorecard.
3. **D3.** `python -m tradingagents.screen TICKER...` runs source collection and the required source
   checks with no model call. A crash it exposed in the source step is fixed.
4. **Arithmetic check.** A stated percentage that the two figures in its own sentence do not give is
   noted at the end of the analyst's report, by code, before the debate. Ambiguous sentences are left alone.

## Not in scope
Any valuation change; the other-company source readers; any send-back to an analyst.

## Estimates
- Build size: small.
- Recommended model: Claude Sonnet 5.5 (`claude-sonnet-5-5`), medium effort; four narrow changes with clear checks.
- Wall-clock: 3 to 5 hours including the independent audit.
