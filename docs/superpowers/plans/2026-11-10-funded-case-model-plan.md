# TradingAgents: funded case model (design and staged plan)

Date: 2026-11-10. Status: for approval. Nothing is built.
Base: staging and launcher at `f17e04f8`. Production stays at `55edfd7e`.

## The outcome in plain words
Today each valuation case is "revenue times a multiple, less net debt, divided by shares". The cash,
debt, lease and share figures at the end of 2027 are estimated separately by the analyst, and code only
writes caveats beside them ("too high if new rent is left out", "interest may be counted twice",
"notes assumed unconverted"). The decision then rests on a value the report itself says is incomplete.

After this build, code works those figures out together from the filing and a short list of stated
assumptions, so each case is one consistent statement: opening balances, what happens during the
period, closing balances, value per share. The caveats become numbers inside the case.

## What it is not
- Not a new valuation method. The value is still revenue times a multiple the analyst chooses. That
  judgment stays, and a reviewer can still object to it.
- Not calibrated probabilities. Weights stay subjective until outcomes settle.
- Not the other-company source work (on hold). See "Overfitting" below.

## Design

### 1. Leases rolled forward by code (Stage 1)
Inputs, all already read from the filing: finance-lease and equipment balance, the maturity schedule
(payments by year and total imputed interest), and leases not yet commenced (total, average term,
commencement window).
- Closing lease balance = opening balance, less the principal part of scheduled payments in the
  period, plus the present value of leases that commence in the period.
- Where the filing gives no schedule for new leases, code uses two stated assumptions: level payments
  over the average term, and commencement spread evenly across the window. The earliest and latest
  possible commencement are shown as a low and high beside the central figure.
- The "finance_equipment" and "all_leases" values stop holding lease balances flat.

### 2. One answer on operating cash flow (Stage 1)
The analyst must state whether their operating cash figure is before or after lease interest and
whether it includes rent on newly commenced leases (two required yes/no fields with a default the
prompt explains). Code then deducts what is missing and nothing twice. The sentence "the case does not
say which applies" goes away.

### 3. Shares and convertible notes worked out by code (Stage 2)
- Share-sale programme: shares issued = cash raised divided by the assumed price, checked both ways.
- Convertible notes: for each note still outstanding at the period end, if the case's own value per
  share is above the note's conversion price, the note is treated as converted (shares added, debt
  removed, never both), less any capped-call offset the filing states. Otherwise it stays as debt.
  Because the value per share depends on the share count, code solves the two together.
- This needs each note's conversion rate and cap read from the filing by code. Today that exists for
  the 2026 notes only; the 2030 terms came from a document search. Reading them by code is part of
  this stage.

### 4. One funded statement per case, and the six-month view (Stage 3)
- The card shows, per case: opening and closing cash, borrowings, leases and shares, with each line
  marked filed, assumed by the analyst, or computed under a stated assumption.
- Part B (six-month event view, built and parked) is brought up to date and installed with this stage.

## Overfitting: how the build guards against it
- No company name, ticker, date or amount in the code. Everything company-specific comes from the
  filing readers.
- Each feature must work when its input is absent: a company with no finance leases, no leases awaiting
  commencement, no convertible notes or no share-sale programme gets a plain "not applicable" line.
- Tests include a second, made-up company with a different shape (no leases, one convertible above
  its conversion price) and a third with nothing but cash and shares.
- Known limit: only DOCN passes the source checks today, so the model can be proven on real filings
  for one company only until the source work is done.

## Effects to expect
- Case values will change once when the model goes in, by my earlier sizing a few dollars a share
  (new rent lowers them; removing double-counted interest raises them; conversion of the 2030 notes
  lowers them). The rating check may read differently on that run. The "since the last decision"
  record will say the method changed.
- The carried-forward cases and weights keep working; the analyst's inputs gain the two yes/no fields.

## Measurement and stop rule
- After Stages 1 and 2: one DOCN run by the user. Judge on ChatGPT's valuation component.
- Stop rule: if valuation is still below 7 after Stages 1 and 2, stop and do not install Stage 3's
  Part B; report what the reviewer still objects to.
- Each stage gets the independent audit and its findings closed before any install request.

## Not proven until a live run
Whether the analyst fills the new fields sensibly, and how the reviewer scores the result.

## Estimates
- Build size: large.
- Stages: 1 medium (8 to 12 hours), 2 medium (8 to 12 hours), 3 small to medium (4 to 6 hours).
- Wall-clock: 20 to 30 hours of build and verification in total, excluding the user's runs and decisions.
- Recommended model: Claude Opus 5.5 (`claude-opus-5-5`), medium effort, or continue in this session's
  model. Reason: interacting contracts (pricing, funding checks, carry-forward, the rating check) where
  a plausible but wrong rule could pass local tests. Engineering judgment, not a measured comparison.
- Paid cost: about $0.50 per stage for the independent audit; no model calls in the build itself.
- Codex credits: not applicable.

## Decisions for the user
1. Build Stage 1 now? Recommended: yes.
2. Convertible notes: treat a note as converted when the case's value is above its conversion price
   (recommended), or keep the analyst's choice and only show the difference?
3. Stop rule at valuation below 7 after Stages 1 and 2? Recommended: yes.
