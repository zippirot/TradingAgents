# Funded case model, Stage 3 and Part B: evidence

Plan: `docs/superpowers/plans/2026-11-10-funded-case-model-plan.md` (Stage 3). Base `884e5331`.
The stop rule (valuation below 7 after Stages 1 and 2) was lifted by the user on 2026-11-11.
Proof source: saved runs `b7396f4f` and `fe8979c2`, repriced with no model call
(`docs/reviews/funded-case-proof-tools/replay_stage3-results.txt`).

## What changed

| Item | Change | Where |
|---|---|---|
| Funded statement | Every priced case carries one statement: cash, each obligation and shares, each from the filed opening balance to the period end, with what the analyst assumes and what code computes shown separately; then the value line and what the filing schedules inside the period that the case does not state. | `agents/valuation_cases.py` (`funded_statement`, called from `price_case`) |
| Where it is shown | As `funded statement: ` lines in each case's assumptions, which the Fundamentals section and an adopted case already print. No record changes shape. | same |
| Maturing notes | A note falling due inside the period that the case leaves in both borrowings and cash is named, with the statement that net obligations are the same either way. | `_maturing_notes` |
| No value moves | The statement only lays out figures the arithmetic already used. | tests and replay |
| Part B | The three parked commits (six-month view from dated events) brought onto this base; three conflicts resolved by keeping both sides. The manager's one resubmission now carries the hurdle correction, the role correction and the event-view correction together. | `agents/event_view.py`, `scenario_decision.py`, `decision_brief.py`, `decision_context.py`, `managers/portfolio_manager.py` |
| Proof tool | The private-checkpoint drill ignores `funded statement: ` lines, which are derived again on every replay. | `docs/reviews/valuation-build2-proof-tools/continue_cli.py` |

## Replay (ran)

Six cases across two real runs; no value moved.

- `b7396f4f` (Terra): the analyst left every balance as filed. The statement says so line by line
  ("analyst: no change stated"), shows what code did (2030 notes converted, leases carried), and names what is
  not stated: 320.5M USD of scheduled finance and equipment payments, and 312.3M USD of 2026 notes falling due
  2026-12-01.
- `fe8979c2` (Opus + Terra): the analyst stated operations, capex, finance payments, note repayment and share
  compensation. The statement shows each beside the two code steps (interest added back, new rent deducted)
  and ends "nothing the filing schedules inside the period is left unstated by the case".

Part B replay rerun on this base (`docs/reviews/event-view-proof-tools/replay-results.txt`): same behaviour;
the printed values moved by under 1 USD because Stage 2 changed the case values it starts from.

## Tests (ran)

Full suite and ruff on this base; six new tests in `tests/test_funded_statement.py`, including one that
rebuilds net obligations from the statement's own closing figures and holds it to the result within 0.1M, and
one for a company with nothing but cash and shares on an equity basis.

## Limits

- The statement shows a bridge; it does not create one. A case whose analyst states no cash changes shows
  opening cash equal to closing cash, with the unstated items named. Whether the analyst fills the bridge is a
  model behaviour (Opus did; Terra and DeepSeek did not in the saved runs).
- New equipment financing in the period is still not priced.
- Part B is a view from dated events, not a six-month price distribution. Event-kind conditions are never
  resolved by code.
- Not proven until a live run: the manager's event_view answers, and how a reviewer scores the result.

## Independent audit (ran)

Executor run f4692472 (openai/gpt-6-astra, 23 turns, 0.76 USD) on 884e5331..59fce263: three medium findings.
Each was checked by running before any change.

| Finding | Verdict | Closure |
|---|---|---|
| F1 A case that omits lease categories showed no lease balances | confirmed | Filed lease balances the case leaves out are shown from the lease-inclusive request already priced for the sensitivities. |
| F2 One repayment counted against two maturing notes | confirmed (narrow reach) | Notes taken earliest first; a repayment is used once. |
| F2 Partial repayment hides a maturity | not reproducible | The unchanged funding check already names it. |
| F3 A list where an event identifier belongs crashed the checker | confirmed | Identifier types are checked first; the answer is reported unusable. |

After closure: full suite 4,596 passed; ruff clean; replay shows no value moved. The closure was not re-audited.

## Follow-up after run 6cf38ab1: a bridge code can complete (ran)

Run 6cf38ab1 (Terra) showed the statement on every case with "analyst: no change stated" throughout, and the
manager again adopted no case. Three changes, approved by the user on 2026-11-11:

| Item | Change | Where |
|---|---|---|
| Code completes the bridge | Once a case states operating cash flow, code deducts the scheduled finance-lease and equipment payments the case does not state, and repays from cash a note that falls due inside the period and that the case leaves in borrowings. With no operating cash stated it does neither. | `agents/valuation_cases.py` (`scheduled_payments`, `applied_payments`, `repaid_notes`, `funded_cash`, `price_case`, `funded_statement`) |
| One request for an empty bridge | A priced case on a basis that uses cash, with no operating cash flow or no capital spending, is sent back to the analyst once. The completed cases replace the originals only if every case still prices and nothing outside the cash bridge changed; otherwise the submitted cases stand. A rejected submission still gets the validation correction instead: there is one request per run. | `agents/shared_valuation.py` (`_request_cash_bridge`) |
| Six-month view | Labelled a mechanical interpolation of the manager's own weights, not a forecast; the weight mix is moved out of the event lines; identical outcome weights across events are said. | `agents/event_view.py` |
| Citation check | A locator inside a citation ("D1/block-95") is no longer read as a figure; a long list of canonical values is cut to six. | `agents/citation_check.py` |

Checks: full suite 4,610 passed, ruff clean. `replay_stage3` on runs b7396f4f and fe8979c2: no value moved
(neither states operating cash without finance payments). Dry run on run 6cf38ab1's base case with operating
cash +900M and capex -400M added by hand: funding "assessed", payments -320.5M and note repayment -312.3M
applied by code, statement ends "nothing the filing schedules inside the period is left unstated", value 98.86
to 99.94. Not independently audited. Not proven until a live run: whether the analyst answers the request.
