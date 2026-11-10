# Build 2, like-for-like multiple and funding bounds: evidence

Plan: `docs/superpowers/plans/2026-11-10-decision-quality-gap-plan.md` (Build 2). Base: Build 1 at `af56f635`.
Proof tool: `docs/reviews/like-for-like-proof-tools/replay.py`; output in `replay-results.txt` beside it.
No network or model call was made.

## What changed

| Plan item | Change | Files |
|---|---|---|
| 1 Like-for-like reference | For a case on the borrowings-less-cash basis, the company's own history is restated on that basis from reported balances at each past quarter end (equity value plus borrowings less cash, over the preceding twelve months' revenue). A case on the equity basis uses the retained equity series. The case's own multiple is placed directly in that range. A quarter without one reported borrowings and one reported cash balance is left out and named. Fewer than three usable quarters, or any other obligation basis, falls back to the earlier equity restatement and says why. | `agents/case_reference.py` |
| 2 The multiple as a stated change | The reference line states the case's multiple beside the multiple today's price implies on the same basis. The per-share effect of that change is in Build 1's return split. | `agents/case_reference.py` |
| 3 Peer coverage | Not changed. See "Not done". | |
| 4 Funding basis | Two open questions about each case's cash bridge are bounded from the filing, per share: interest inside the scheduled lease payments (if operating cash flow is already after interest, the case is too low by up to that amount), and rent on leases that have not commenced (if operating cash flow leaves it out, the case is too high by a low-to-high range). Printed with each case and shown to the Portfolio Manager. Case arithmetic is unchanged. | `agents/valuation_cases.py`, `agents/shared_valuation.py`, `agents/scenario_decision.py` |

## Replay of run d58117ef (ran)

Own history on equity value plus borrowings less cash, over trailing revenue:

| Quarter end | Multiple |
|---|---|
| 2024-12-31 | 5.38x |
| 2025-09-30 | 4.84x |
| 2025-12-31 | 6.06x |
| 2026-03-31 | 9.62x |
| 2026-06-30 | 16.46x |
| 2026-09-30 | 14.08x |

Low 4.84x, median 7.84x, high 16.46x; today's price implies 8.19x. Left out: 2025-03-31 and 2025-06-30 (no
reported borrowings balance retained for those dates).

| Case | Multiple | Saved report said (equity over forecast revenue, against an equity/trailing series) | Now, on the same basis |
|---|---|---|---|
| Base | 4.7x | between the median and the high | below the low |
| Downside | 3.0x | between the low and the median | below the low |
| Upside | 6.0x | between the median and the high | between the low and the median |

Funding figures, base case (as corrected after the audit, below): if operating cash flow is already after lease
interest, the case is too low by at most 1.13 USD a share, about 0.34 if interest falls evenly across payments;
if rent on leases not yet commenced (2026-11 to 2028-06) is not in the operating cash flow figure, a
level-payment sensitivity puts the case 0.00 to 2.57 USD a share too high. The rent range is not a bound.

Unchanged on the same replay: every case price, the weighted value today (63.64), direction (below) and
operational score (5). The five 2026-11-09 runs keep their operational scores; the two with priced cases on
this basis now read "below the low" on the same basis.

## What this means for a reader

All three analyst cases in the saved run use a multiple at or below the bottom of what the company has
traded at on the same basis over the six usable quarters, and well below what today's price implies. The
earlier report could not show that, because it compared unlike figures. This build states it; it does not
say which multiple is right. Six quarters that include a sharp run-up are a thin reference.

## Checks

- Full suite at the audited commit: 4,427 passed, 10 skipped, 1 deselected; after closure 4,431. `ruff check .`: clean.
- New tests (`tests/test_like_for_like.py`, 16): restated history from reported balances; placement in each
  band; the same case in a different band under the old comparison; equity basis; unsupported bases;
  missing, duplicated and non-USD balances; too few quarters; interest and rent bounds; a period ending
  after the commencement window; unusable terms; equity-basis cases carry no bounds.
- One existing test expectation was updated: an unavailable position now also carries the reason no
  same-basis history could be stated.

## Plan adjustments

1. **No forward-revenue history was needed.** The plan proposed history on forward revenue. A case applies
   its multiple to revenue of the twelve months ending at its period end, so the matching history is each
   quarter's value over the preceding twelve months' revenue, which the retained filings already support.
2. **Funding basis is bounded by code, not declared by the analyst.** The plan had the analyst state whether
   operating cash flow is before or after interest and rent. That adds a prompt field and trusts the answer.
   The filing gives enough to bound both effects, so the report states the bounds and that the case does not
   say which applies. No prompt or case schema change.
3. **No rule rejects a multiple outside the range.** The position is stated to the manager and the reader.
   Adding a gate was not needed to meet the plan and would add friction.

## Not done

- **Peers on the same basis, and the two excluded peers.** Peer balances are not retained in run state, so a
  same-basis peer reference needs new retrieval and cannot be proven on saved runs. The two excluded peers
  were excluded for a multi-class share structure and for missing quarterly revenue in filings; neither is a
  quick fix. Peers remain on the equity basis, shown individually as before.
- **History for the lease-inclusive bases.** Past finance-lease and equipment balances are not retained.
- **Borrowings for two quarters** (2025-03-31, 2025-06-30) are not in the retained facts.

## Not verified

- A live run, including how the analyst and manager use the new reference.
- Remote CI (unpushed).

## Independent audit and closure (2026-11-10)

Audit of `ea5549c6` by GPT-6 Astra (run d38f7c69, 22 turns, $0.67): three Medium findings, all on the funding
figures; none on the same-basis reference. No High or Critical.

| Finding | Verdict | Action |
|---|---|---|
| The interest figure spread remaining interest evenly across payments and called the result "up to". Interest can fall earlier than payments. | Confirmed, reproduced by a new test. | Fixed: the stated maximum is all imputed interest remaining on the schedule, capped at the payments the case deducts (1.13 USD a share on the base case). The even spread (0.34) is printed beside it, labelled as an assumption the filing does not state. |
| The rent range assumed level payments over the average term and called itself a bound from the filing. | Confirmed, reproduced by a new test. The filing's total, average term and window do not fix a payment pattern, and the only true maximum (the whole commitment) is useless. | Fixed in wording, not arithmetic: it is called a level-payment sensitivity, the assumption is stated, and the text says the actual figure can fall outside the range. |
| The double-counting sentence appeared even when a case deducted no finance payments. | Confirmed, reproduced by a new test. | Fixed: the interest figure is sized on the payments the case actually deducts (the lesser of stated and scheduled) and is omitted when it deducts none. |

Also added, from the auditor's requirement table: the same-basis multiple now sits beside each quarter's growth
and gross margin in the existing history line.

Closure checks (ran): full suite 4,431 passed, 10 skipped, 1 deselected; `ruff check .` clean; replay of d58117ef
shows the corrected wording and unchanged case prices, weighted value today (63.64), direction and score.

**Scope points the auditor flagged as needing the user's acceptance, not defects:** the three plan adjustments
above (no forward-revenue history, funding sized by code, no out-of-range gate) and peers not done.
