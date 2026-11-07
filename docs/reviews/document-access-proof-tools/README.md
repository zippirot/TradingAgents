# CAT final-slot proof draft

After the repaired B candidate is committed and clean on M1, preserve the original approval **as an archive** and prepare a draft against the existing ledger. Do not replace the active approval or candidate while preparing the draft.

```sh
cd /Users/zipp/Developer/tradingagents-document-access-20261106/build-a
.venv/bin/python docs/reviews/document-access-proof-tools/draft_final_slot.py \
  --original-approval /Users/zipp/Developer/tradingagents-document-access-20261106/private/document-access-proof-approval-original-93a1ae5.json \
  --provider-metadata /Users/zipp/Developer/tradingagents-document-access-20261106/private/document-access-reviewed-provider-metadata.json \
  --output-dir /Users/zipp/Developer/tradingagents-document-access-20261106/private/cat-final-slot-drafts
```

The named archive must be a byte-preserved copy of the original approval and remain available for the eventual CAT verification. The command reads the old candidate, archived approval, historical ledgers, and current shared ledger. It writes only `cat-candidate-draft.json` and `cat-approval-draft.json` in the chosen draft directory; it makes no provider, source, model, or paid call and does not claim CAT. The approval draft deliberately has blank approval identity, timestamp, and user instruction, so it cannot authorize a run.

Review the frozen candidate hash, archived approval hash, exact ledger prefix hash, unchanged $72 aggregate and $24 CAT slot, route caps, model IDs, and November 6 analysis session before seeking fresh user approval. The eventual approved record must bind the exact new candidate and runner hashes and fill the approval fields from that fresh instruction. A newly observed CAT account/endpoint receipt is still required immediately before the one remaining claim. DOCN and MSFT attempts remain consumed, and the original ledger allowance is reused without a top-up.
