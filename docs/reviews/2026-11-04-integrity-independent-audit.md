# Independent report-integrity audit — 2026-11-04

The independent reviewer inspected the complete change from staging 3411158f91eb267aab8760fc90afbf43556eb0bb through milestone 5 and re-reviewed the affected milestone-6 source corrections. Coverage included SEC vintage/source selection, bounded filing retrieval, accounting tables and bridges, valuation, publication/streaming, CLI/report artifacts, memory, settlement and backtests. Review was read-only on Machine 1; it did not make paid calls or substitute for runtime acceptance.

## Material findings and closure

- Disclosure period/metric binding: a value for a different year, and then an EBITDA amount in a multi-metric sentence, could be assigned to revenue. Exact-span, single-claim and narrow metric/amount connector checks reject the reproduced cases while preserving supported ranges and dated table shapes. Independent re-review closed both examples.
- Rounded source values: exact equality falsely conflicted a rounded filing table with a compatible same-filing value. Only trusted parser quanta provide rounding allowance; incompatible vintages, absent precision and pairwise disagreement remain conflicts. Original facts remain available. Independently closed.
- Principal source definition: the equipment-scope paragraph initially certified wrong amounts and comparative-year cells. Selected amounts must match displayed precision and the current-period driver clause; wrong amount, prior/previous period and conflicting dates remain unclassified. Independently re-reviewed against recorded and mutated cases.
- Stale table context: a prior thousands-scale heading could cross unrelated whole-dollar prose. The reproduced parser false pass is closed by bounded context reset; actual tables retain their own scale/currency evidence.
- Actual source coverage: hidden XBRL, exhibit naming and keyword-only ranking omitted required evidence. Recorded fixtures verify visible-text extraction, same-accession press-release selection, source context and retention of required statement/debt/facility/cash-flow blocks within existing text budgets.
- Actual cash period: derived TTM displaced reported nine-month data. Primary selection prefers reported periods while preserving derived facts; reported annual behavior remains covered. Independently re-reviewed.

Recorded-source integration distinguishes carrying debt from lease/equipment obligations, present value from undiscounted maturities, gross financed acquisitions/proceeds from principal, and current from comparative equity movements. Unsupported prior-period capped-call movements remain visible gaps.

## Verification and limits

The candidate passed 1,762 offline tests, with one optional Bedrock dependency skip and one configured integration deselection. Changed Python files passed Ruff; dependency and diff checks passed. The retained live-source package passes all eight critical checks, with optional warnings. Exact source/test manifests and logs are recorded in milestone-6 evidence.

This is not universal semantic verification of arbitrary prose or complete-document coverage. Unsupported interpretations, excerpt limits and optional gaps remain visible. Real CLI source-complete, controlled failure/no-memory, restart/recovery and actual saved-report inspection remain required before goal completion.

## Live prompt follow-up

Independent read-only review of the literal named extraction fences and narrower quotation instructions found no material issue. Parser contracts and provenance checks are unchanged. Live compliance remains a required proof; prompt inspection alone does not establish it.

## Recorded operating-KPI context follow-up

The acceptance audit identified that the recorded release separates KPI value, period, definition and growth basis. The bounded same-document context implementation was reviewed independently against the actual source. Reproduced subject-substring/definition-name confusion, prior/forward qualifiers, overridden comparison bases, duplicate/missing source context and URL issuer identity were corrected with recorded regressions. Final narrow re-audit found no remaining material current-context finding. A missing definition remains an optional warning; arbitrary text cannot masquerade as a definition. Forty-nine context tests and the final 1,812-test offline suite pass. This is not a claim that live model extraction or all possible source prose is verified.
