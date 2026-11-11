# Funded case model, Stage 2: evidence

Plan: `docs/superpowers/plans/2026-11-10-funded-case-model-plan.md` (Stage 2 only). Base `d640de7a` (Stage 1).
Proof source: saved run `6fe6324b`, repriced with no model call
(`docs/reviews/funded-case-proof-tools/replay-stage2-results.txt`).

## What changed

| Item | Change | Where |
|---|---|---|
| Note terms read by code | Every "20XX Convertible Notes" the latest primary filing states as outstanding: principal, maturity, conversion price, and a capped call only when its strike equals the note's conversion price. A term stated two ways is left out, never chosen. No company or year in the code. | `dataflows/convertibles.py` |
| Conversion decided by code | A note still outstanding at the case's period end is converted when the case's own value per share is above its conversion price: shares added (net of capped-call shares, up to the cap), principal removed from borrowings, never both. Otherwise it stays as debt. Share count and value are solved together. Applied to the main value and to each lease-inclusive value at that value's own level. | `agents/valuation_cases.py` (`outstanding_convertibles`, `settle_convertibles`, `price_case`) |
| A case that treats a note itself | A conversion share change, or a debt cash change that names the note (new optional `instrument`), switches code off for that note. | `agents/valuation_cases.py` (`CashChange.instrument`) |
| Share sales | Shares and cash must both be positive; the implied price after costs is printed beside the case's value. | `agents/valuation_cases.py` (`price_case`) |
| Where it is shown | Each note's outcome is appended to the case's funding sentence, which the report and the manager's brief already print. | `agents/shared_valuation.py` (`_with_conversion`) |
| Analyst instructions | Leave an outstanding note in borrowings; code decides it. Name a note the case repays or converts early. | `analysts/fundamentals_analyst.py` |
| Terms source | Read from the pinned filing on every pricing, not stored in state, so saved runs reprice and no saved record changes shape. | `agents/shared_valuation.py` (`_funding_terms`) |

## Replay on DOCN's saved cases (ran)

Read from the 10-Q: 2026 notes, 312.3M USD, mature 2026-12-01, conversion 178.51 (mature inside the period, so not
decided here). 2030 notes, 153.2M USD outstanding, mature 2030-08-15, conversion 39.17, capped call 39.17 to 66.51.

| Case | Before | After | Shares | What happened |
|---|---|---|---|---|
| Base | 101.17 | 100.05 | 120.42M to 123.26M | 2030 notes converted: 3.91M shares added, 1.07M returned by the capped call, 149.6M USD leaves borrowings |
| Downside | 59.14 | 59.11 | 127.09M to 129.68M | same; 1.32M shares returned. Share sale: 58.80 a share after costs against a case value of 59.11 |
| Upside | 141.53 | 139.14 | 120.42M to 123.56M | same; 0.77M shares returned |

Lease-inclusive base values: with finance leases 95.62 to 94.68; with all leases 78.63 to 78.22.

The values fall because the notes are worth more as shares than as debt at these prices; the saved cases counted
them as debt only.

## Verification (ran)

| Check | Result |
|---|---|
| Full suite | 4,521 passed, 10 skipped |
| Ruff | clean |
| New tests | `tests/test_convertibles.py` (5), `tests/test_convertible_settlement.py` (12), share-sale tests in `tests/test_shared_valuation.py` |
| Independent arithmetic | The saved-checkpoint drill (`tests/test_build2_continuation_proof.py`) prices the converted case by closed form and agrees with the solver to twenty places |

## Changed existing checks

- `tests/test_shared_valuation.py`: the share-sale fixture sold shares and lost cash; it now raises cash, and a new
  test rejects the old shape.
- `docs/reviews/valuation-build2-proof-tools/`: the saved-checkpoint drill's independent price now includes
  conversion (closed form), and its record comparison leaves out the values conversion moves.

## Limits

- Capped calls covering notes already repurchased (DOCN's still cover the original 625M USD issue) are not valued;
  the offset is limited to the notes still outstanding. This understates value.
- The capped-call offset is its value at the case's price with no time value.
- Debt removed is the note's principal, or all the case still owes if less; carrying value per note is not read.
- A note the case repays early without naming it is still converted by code. The analyst is told to name it.
- Real-filing proof is DOCN only. Sentence patterns for other issuers' note disclosures are untested.
- Not tested with a live model: whether the analyst follows the new instruction.
