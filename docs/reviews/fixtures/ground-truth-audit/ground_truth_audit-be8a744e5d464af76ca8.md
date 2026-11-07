### Ground Truth Audit

Status **completed with findings**. Reviewed 4 of 4 report chunks. Contradicted claims 2, unsupported claims 0.

Code checks source quotations and the calculation proofs shown in the detail. Other arithmetic and source interpretation use model review.

**Recommendation needs review.** Material factual questions remain or reassessment was unavailable.

Material unresolved findings

- **contradicted** — “Revenue was 100 USD.” — 1_analysts/market.md@0:147 [Source](https://www.sec.gov/Archives/edgar/data/9999999999/999999999926000001/synthetic-verification-fixture.htm)
- **contradicted** — “The final paragraph claims gross margin was 99%.” — 1_analysts/market.md@0:147 [Source](https://www.sec.gov/Archives/edgar/data/9999999999/999999999926000001/synthetic-verification-fixture.htm)

The Full Ground Truth Audit contains all findings and source details.

Review used retained sources; independent source retrieval was not performed by this pass.

### Full Ground Truth Audit

Status: **completed with findings**.
Reviewed 4 of 4 report chunks.
Source quotations and arithmetic checks are distinct from model assessments of meaning.

- **Material to the recommendation — contradicted** — Revenue was 100 USD.
  Location: 1_analysts/market.md@0:147
  Compared with the explicitly fictional dated fixture passage.
  Correction: Revenue was 120 USD.
  Source: [synthetic-sec-shaped-source/synthetic-quarterly-figures](https://www.sec.gov/Archives/edgar/data/9999999999/999999999926000001/synthetic-verification-fixture.htm). Quote: Revenue was 120 USD.
  Source kind: filing passage; known at: 2026-11-03.
  Source qualifiers: {"date_scope":"Filing report date is metadata, not an inferred accounting period.","filing_form":"10-Q","filing_report_date":"2026-09-30","preceding_introductions":&#91;&#93;,"source_section":"Synthetic example"}
  Semantic assessment: model judgment.

- **Material to the recommendation — contradicted** — The final paragraph claims gross margin was 99%.
  Location: 1_analysts/market.md@0:147
  Compared with the explicitly fictional dated fixture passage.
  Correction: Gross margin was 25%.
  Source: [synthetic-sec-shaped-source/synthetic-quarterly-figures](https://www.sec.gov/Archives/edgar/data/9999999999/999999999926000001/synthetic-verification-fixture.htm). Quote: Gross margin was 25%.
  Source kind: filing passage; known at: 2026-11-03.
  Source qualifiers: {"date_scope":"Filing report date is metadata, not an inferred accounting period.","filing_form":"10-Q","filing_report_date":"2026-09-30","preceding_introductions":&#91;&#93;,"source_section":"Synthetic example"}
  Semantic assessment: model judgment.

- **hypothesis** — ## Executive summary

Completed analyst reports: market. The report shows that the retained portfolio text did not establish an actionable rating.

REVIEW means no actionable rating was established. The retained decision did not establish an actionable rating. Evidence quality is unvalidated; the report records no validated case adoption, and any case values remain conditional.

  Location: summary/summary.md@0:381
  Synthetic display framing. This fake reviewer establishes no real-world financial facts.
  Semantic assessment: model judgment.

- **hypothesis** — Synthetic verification fixture — not investment research.
REVIEW. Synthetic verification only.

### What the price implies

Unavailable: Legacy evidence was not validated; current source-only assessment unavailable.
  Location: 5_portfolio/decision.md@0:215
  Synthetic display framing. This fake reviewer establishes no real-world financial facts.
  Semantic assessment: model judgment.

- **hypothesis** — Synthetic verification fixture — not investment research.

Revenue was 100 USD.

Cash was 20 USD.

The final paragraph claims gross margin was 99%.
  Location: 1_analysts/market.md@0:147
  Synthetic display framing. This fake reviewer establishes no real-world financial facts.
  Semantic assessment: model judgment.

- **supported** — Cash was 20 USD.
  Location: 1_analysts/market.md@0:147
  Compared with the explicitly fictional dated fixture passage.
  Source: [synthetic-sec-shaped-source/synthetic-quarterly-figures](https://www.sec.gov/Archives/edgar/data/9999999999/999999999926000001/synthetic-verification-fixture.htm). Quote: Cash was 20 USD.
  Source kind: filing passage; known at: 2026-11-03.
  Source qualifiers: {"date_scope":"Filing report date is metadata, not an inferred accounting period.","filing_form":"10-Q","filing_report_date":"2026-09-30","preceding_introductions":&#91;&#93;,"source_section":"Synthetic example"}
  Semantic assessment: model judgment.

- **hypothesis** — Evidence status: &#42;&#42;unvalidated&#42;&#42;. Checks apply to cited source values and calculations; narrative interpretations are not all verified.

Legacy export — financial evidence unvalidated.

#### Warnings and gaps

- Legacy export — financial evidence was not validated
  Location: 6_evidence/summary.md@0:264
  Synthetic display framing. This fake reviewer establishes no real-world financial facts.
  Semantic assessment: model judgment.
- Coverage limit: Review used retained sources; independent source retrieval was not performed by this pass.


**Recommendation needs review.** Material factual questions remain in the delivered conclusion or its premises.