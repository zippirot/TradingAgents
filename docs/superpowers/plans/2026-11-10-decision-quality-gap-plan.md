# TradingAgents: decision-quality gap plan

Date: 2026-11-10. Status: decisions made 2026-11-10; Build 3 goes first. Nothing is built yet.
Repo: `~/Documents/ChatGPT/Tauric/TradingAgents`. Base: `staging` at `c4aa8a40`.
Evidence used: DOCN run `d58117ef` (saved state), the code at `c4aa8a40`, and ChatGPT's seven-part scoring.

## The problem in one paragraph

Decision quality has been flat at 7.5 to 8.0 for ten runs. Under ChatGPT's seven-part scoring, five parts
already score 7.5 to 9. Two parts, worth 40% of the score, sit near 5: **valuation and expected returns (5.5)**
and **portfolio construction (5.0)**. Recent builds worked on the parts that were already strong. This plan
works only on the two weak parts, measures each build against its own component, and stops if the
component does not move.

## What I found when I sized the valuation problem

All figures are from run `d58117ef`. Arithmetic is mine.

| Source of error in a case value | Effect on the base case ($77.22) |
|---|---|
| One turn of the multiple (4.7x to 5.7x) | about $16 per share |
| Not bringing a 2027 value back to today (at a 10% yearly required return) | about $8 per share |
| Rent on leases not yet started, one full year at full run-rate | about $2 per share |
| Lease interest counted twice (the audit's finding) | under $0.50 per share |

So the order of importance is: **the multiple, then the time basis, then funding detail.** The audit
finding that has drawn the most attention is the smallest of the four. The plan follows this order of
value, with one exception: the time basis is built first because it needs no new data and is the
cheapest large gain.

## What a finished decision should say

Illustration on the saved run, using a 10% yearly required return as a placeholder. Not a forecast.

| | Value at end of 2027 | Value today | Yearly return if bought at $78.30 | Manager's weight |
|---|---|---|---|---|
| Downside | $42.93 | $38.50 | about -41% | 30% |
| Base | $77.22 | $69.26 | about -1% | 55% |
| Upside | $103.25 | $92.60 | about +27% | 15% |
| Weighted | $70.84 | $63.53 | about -8% | |

Read against a 10% required return, the weighted case earns about 18 points a year less than required.
That is a stated, checkable reason for Underweight. Today's report can only say the weighted value is
"near" the price, because it compares a 2027 value with today's price directly.

Sizing would follow from the same table: in the downside case the position loses about half. If you
accept losing 1% of the portfolio in that case, the position can be at most about 2% of the portfolio.
That rule needs no knowledge of your holdings.

## Build 1: time basis and return (targets valuation, 25% of the score)

No new data sources. No extra model calls.

1. **Required return.** One setting: the yearly return you require from a stock like this. Default: the
   10-year Treasury yield retrieved for the run plus a fixed premium. Printed with its source and date.
2. **Value today and yearly return.** For every priced case, code computes the value brought back to the
   analysis date and the yearly return from the dated close to the case's period end. Both are printed
   beside the period-end value. Nothing is discounted silently.
3. **Rating check on the same time basis.** The existing check (rating versus weighted value) uses value
   today against the close, and states the return gap against the required return.
4. **Where the return comes from.** Each case's return is split by code into three parts: revenue
   delivery, change in the multiple from what today's price implies, and change in share count and net
   obligations. This shows that the base case is "guidance met, no change in multiple" and the upside is
   "guidance beaten plus a higher multiple".
5. **How sturdy the call is.** Code prints the weighted value under equal weights, and the upside weight
   at which the weighted value today would equal the price. This answers "what if the odds are wrong"
   without pretending the odds are measured.

Alternative rejected: forecasting a six-month price or a benchmark return. Both would be invented numbers.
A required return is one stated assumption that you set.

## Build 2: a like-for-like multiple and funding basis (targets valuation)

This is the larger and less certain build.

1. **Like-for-like reference.** Today a case's forward multiple on one debt basis is compared with a
   trailing multiple on a different basis. That mismatch caused two of the three audit flags in the saved
   run. Code will compute the company's own history and each accepted peer on the same basis as the case:
   same debt perimeter, and forward revenue where the following year's revenue is now known from filings.
   Growth and gross margin are printed beside each reference point.
2. **The multiple as a stated change.** Every case states its multiple as a change from the multiple
   today's price implies (for example "from 4.7x to 6.0x"), and the analyst must place it against the
   like-for-like reference. A multiple outside the reference range needs a stated reason.
3. **Peer coverage.** Two of four proposed peers were dropped for data reasons (a multi-class share
   structure and missing quarterly revenue). Fix what can be fixed from filings; report the rest plainly.
4. **Funding basis.** The analyst states whether projected operating cash flow is before or after lease
   interest and new-lease rent. Code then deducts principal only where interest is already counted, and
   shows rent on leases not yet started as a low-to-high range, because the filing gives no schedule by
   year.

Known limit: the history is short (eight quarters) and the peer set is small. This build makes the
multiple comparable and bounded. It does not make it statistically proven, and the report will say so.

## Build 3: sizing from the downside (targets portfolio construction, 15% of the score)

1. **A sizing rule that needs no holdings.** From the downside case's value today: the largest position
   weight for each 1% of portfolio you accept losing. Printed on every report that has a priced downside.
2. **With your portfolio file.** The sizing block built this morning already computes current weight,
   target weight and trade size when the file exists. It gains: loss in the downside case against your
   loss budget, the position's volatility, and how closely it moves with your other holdings, all from
   price history.
3. **Your part.** The file does not exist yet (`~/.tradingagents/portfolio.json`). The rule in item 1 works
   without it; item 2 needs your real numbers.

## How progress is measured

- **Component scores, not the total.** After each build, one paid DOCN run that you start, scored on the
  seven parts. Build 1 and Build 2 are judged on the valuation part; Build 3 on portfolio construction.
- **Proof before spending.** Each build is first proven by replaying saved runs with no model call, as was
  done today.
- **A second question, tracked separately: were the calls right?** The first five-session result on the
  Nov 5 call settles this week and the scorecard already exists. Running two other mid-sized companies
  would show whether the system can reach a rating other than Underweight. That is two paid runs and your
  decision; it is not part of the builds. Very large filers are known to stop early and are a separate,
  paused plan.

## Stop rules

- If the valuation part is still below 7 after Build 1 and Build 2, stop building. The honest conclusion
  would be that this design is a research tool with an opinion attached.
- If a build's replay proof does not show the intended change, it is not merged.
- No build in this plan changes prompts beyond the fields it adds, the debate design, or the models.

## What this plan does not do

- It does not calibrate the manager's odds. Only settled outcomes can.
- It does not prove the decisions make money.
- It does not address execution quality (10% of the score, currently 7.5) or agent handoffs (10%, at 8.0).
- It does not block a flagged case from being adopted as a price target.

## Decisions (made by the user 2026-11-10)

1. **Required return:** the 10-year Treasury yield retrieved for the run plus a fixed premium of 5 points.
2. **Order:** Build 3 first, then Build 1, then Build 2.
3. **Measurement run:** one paid DOCN run after each build, started by the user.
4. **Other companies:** not now. Get DOCN right first.
5. **Independent audit:** on each build.

### Adjustment that follows from building 3 first

Build 3's sizing rule needs the downside case's value today, which was a Build 1 item. Build 3 therefore
also adds the required-return setting and the value-today calculation, as one small shared piece of
arithmetic. Build 1 then reuses it for the rest of its work. The total work is unchanged; Build 3 grows
by roughly an hour and Build 1 shrinks by the same.

### Build 3 task list

- **3a Required return.** Setting `required_return_premium` (default 5 points). The run retrieves the 10-year
  Treasury yield through the existing FRED source and records its value and date. If the yield cannot be
  retrieved, the report says so and no value-today or sizing rule is printed; nothing is assumed.
- **3b Value today.** For each priced case: period-end value brought back to the analysis date at the
  required return. Stored on the case and printed beside the period-end value, labelled as arithmetic
  on a stated assumption.
- **3c Sizing rule without holdings.** From the downside case the manager accepted (lowest accepted value
  today when no case is labelled downside): the fall from the dated close, and the largest position
  weight per 1% of portfolio loss accepted. No rule is printed when no accepted case is below the close.
- **3d With the portfolio file.** The existing "Position and sizing" block gains: loss in the downside
  case against the loss budget, the weight that would keep that loss inside the budget, the position's
  volatility from price history, and its correlation with each other holding when their price history
  can be retrieved. Missing history is stated, not estimated.
- **3e Proof.** Replay run `d58117ef` offline with and without a sample portfolio file. Tests for each
  item, including no Treasury yield, no downside below the close, a rejected downside case, and a file
  with one and with several holdings. Full suite and lint. Independent audit, then closure.

## Estimates

| Build | Size | Build and verification | Recommended model |
|---|---|---|---|
| 1. Time basis and return | small | 1.5 to 3 hours | Claude Sonnet 5.5 (`claude-sonnet-5-5`), medium |
| 2. Like-for-like multiple and funding basis | medium | 5 to 9 hours | Claude Opus 5.5 (`claude-opus-5-5`), medium |
| 3. Sizing from the downside (first) | small | 3 to 4 hours | Claude Sonnet 5.5 (`claude-sonnet-5-5`), medium |

Build 2 gets the stronger model because it has to reconcile figures from different filings on one basis,
where a plausible but wrong match could pass local tests. Builds 1 and 3 are arithmetic with clear
checks. These are engineering judgments, not measured comparisons; continuing in this session's model is
acceptable for all three. Hours exclude waiting for your runs and decisions. Codex credits: not
applicable, the builds run in Claude Code.

My expectation, as a judgment only: Build 1 moves the valuation part from 5.5 to about 7; Build 2 to
about 8; Build 3 moves portfolio construction from 5 to about 7 without your file and higher with it.
That would put the total near 8.3 to 8.6. I would not promise 9.5.

## Audit declaration for Build 3

- Build size: small.

## Status and later decisions (2026-11-10)

Builds 3, 1 and 2 are built and their independent audits closed. Evidence:
`docs/reviews/2026-11-10-sizing-from-downside.md`, `docs/reviews/2026-11-10-time-basis-return.md`,
`docs/reviews/2026-11-10-like-for-like-multiple.md`.

Decided by the user after the builds:
- Build 3 item 3d (portfolio-file additions) left out for now.
- Build 2's three plan adjustments accepted: history on the trailing basis the cases use, not forward
  revenue; funding sized by code from the filing, not declared by the analyst; a multiple outside the range
  is shown, not blocked.
- Peer coverage on the same basis: accepted as not done; on hold.
- Merge to staging, push and launcher install approved. Production is not promoted.
