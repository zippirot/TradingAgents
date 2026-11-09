# Workflow gap closure — integrated staging acceptance

**Accepted on staging:** all seven builds and their approved keep/drop dispositions are complete at implementation acceptance `856314e4b1dae655e8de548445a19af8c299dd51`, with all seven jobs passing in CI42560106100 and final Nb Claude closure confirming zero open Critical/High/Medium. This final report records that observed acceptance. Its delivery commit changes documentation only; the exact delivery SHA/CI is recorded separately at completion. Staging remains unreleased.

## Accepted builds

| Build | Published staging SHA | Full pytest | Ruff | Actual Claude closure | Exact-SHA CI |
| --- | --- | ---: | --- | --- | --- |
| R5 | `730bbe04ce7ba382367463dccca57bc39b7e0e92` | 3358 passed | passed | `d017677d-9ee5-42bb-af5d-59eab4a26bd6`; 0 open Critical/High/Medium | 42444835247; all 7 jobs passed |
| R1 | `78e3611ffb3fd6d8672acc2c15f54489cc258ae6` | 3448 passed | passed | `707b0bd1-3db6-4bab-b414-fd1d22148a74`; 0 open Critical/High/Medium | 42457304605; all 7 jobs passed |
| R2 | `ccecd32599fe63754e2b2c4de3f17fac88139b2c` | 3480 passed | passed | `6d00d60f-38e8-4c98-8fc4-32e773c2d3e2`; 0 open Critical/High/Medium | 42465206951; all 7 jobs passed |
| R4 | `82703a98b9726692ced53d761a643e7772494bde` | 3505 passed | passed | `ad080c54-fb75-4f1e-bf1c-11d7c3c10c0b`; 0 open Critical/High/Medium | 42468253067; all 7 jobs passed |
| R3 | `c4b70a3618016fd630bee3c4ddf5b671c4d919bc` | 3561 passed | passed | `79fa9f11-4c1a-4cb5-a7f4-a5e0e88987d7`; 0 open Critical/High/Medium | 42480313072; all 7 jobs passed |
| R4-live-gap | `ed24ec18d6b50734f378617755f60800e1d66aee` | 3564 passed | passed | `2615a9a9-c9df-4be4-8230-94c7cff64726`; 0 open Critical/High/Medium | 42506300046; all 7 jobs passed |
| Na | `35e9ed10b0d97636d1b24819b29430c5444b291b` | 3585 passed | passed | `7617f414-e487-4fe5-8ddd-6e67f1fcf192`; 0 open Critical/High/Medium | 42543531994; all 7 jobs passed |
| Nb | `856314e4b1dae655e8de548445a19af8c299dd51` | 3960 passed | passed | `6eec6a8f-9e7a-4f39-8dc0-5ff2e4c6cf00`; 0 open Critical/High/Medium | 42560106100; all 7 jobs passed |

Each complete suite also recorded 10 skipped, 1 deselected and 100 subtests. These are separate complete candidate runs, not a combined passing result across revisions. The R3 closure has two new Low and two carried Low findings. Na additionally has a real Fable timezone-fixture supplemental review with zero open material findings.

## Gap dispositions

| Owning task | Original gaps | Disposition | Closing published commit |
| --- | --- | --- | --- |
| R1.1 | SA1, SE1 | Implemented and accepted within observed proof limits | `78e3611ffb3fd6d8672acc2c15f54489cc258ae6` |
| R1.2 | SA2 | Implemented and accepted within observed proof limits | `78e3611ffb3fd6d8672acc2c15f54489cc258ae6` |
| R1.3 | FA1 | Implemented and accepted within observed proof limits | `78e3611ffb3fd6d8672acc2c15f54489cc258ae6` |
| R1.4 | BB1 | Implemented and accepted within observed proof limits | `78e3611ffb3fd6d8672acc2c15f54489cc258ae6` |
| R1.5 | SE2, NE2 | Implemented and accepted within observed proof limits | `78e3611ffb3fd6d8672acc2c15f54489cc258ae6` |
| R1.6 | SA3, EC1, EC2, EC3 | Implemented and accepted within observed proof limits | `78e3611ffb3fd6d8672acc2c15f54489cc258ae6` |
| R1.7 | FA2 | Implemented and accepted within observed proof limits | `78e3611ffb3fd6d8672acc2c15f54489cc258ae6` |
| R2.1 | DF1 | Implemented and accepted within observed proof limits | `ccecd32599fe63754e2b2c4de3f17fac88139b2c` |
| R2.2 | DF2 | Implemented and accepted within observed proof limits | `ccecd32599fe63754e2b2c4de3f17fac88139b2c` |
| R2.3 | DF3, BB2 deduplication | Implemented and accepted within observed proof limits | `ccecd32599fe63754e2b2c4de3f17fac88139b2c` |
| R4.1 | H1 | Implemented and accepted within observed proof limits | `82703a98b9726692ced53d761a643e7772494bde` |
| R4.2 | H2, RM2 | Implemented and accepted within observed proof limits | `82703a98b9726692ced53d761a643e7772494bde; retained-union correction ed24ec18d6b50734f378617755f60800e1d66aee` |
| R4.3 | ML3, RK3 | Implemented and accepted within observed proof limits | `82703a98b9726692ced53d761a643e7772494bde` |
| R3.1 | P1, EX1, EX2, AA3 | Implemented and accepted within observed proof limits | `c4b70a3618016fd630bee3c4ddf5b671c4d919bc` |
| R3.2 | P2 | Implemented and accepted within observed proof limits | `c4b70a3618016fd630bee3c4ddf5b671c4d919bc` |
| R3.3 | P3, P4 | Implemented and accepted within observed proof limits | `c4b70a3618016fd630bee3c4ddf5b671c4d919bc` |
| R3.4 | H3 | Implemented and accepted within observed proof limits | `c4b70a3618016fd630bee3c4ddf5b671c4d919bc` |
| R3.5 | AA1 | Implemented and accepted within observed proof limits | `c4b70a3618016fd630bee3c4ddf5b671c4d919bc` |
| R3.6 | RK5, H5 | Implemented and accepted within observed proof limits | `c4b70a3618016fd630bee3c4ddf5b671c4d919bc` |
| R3.7 | AA2 | Implemented and accepted within observed proof limits | `c4b70a3618016fd630bee3c4ddf5b671c4d919bc` |
| R5.1 | CN1, NE1 | Implemented and accepted within observed proof limits | `730bbe04ce7ba382367463dccca57bc39b7e0e92` |
| R5.2 | SE4, TR2 | Implemented and accepted within observed proof limits | `730bbe04ce7ba382367463dccca57bc39b7e0e92` |
| R5.3 | ML2, H6 | Implemented and accepted within observed proof limits | `730bbe04ce7ba382367463dccca57bc39b7e0e92` |
| R5.4 | M1, M2 | Implemented and accepted within observed proof limits | `730bbe04ce7ba382367463dccca57bc39b7e0e92` |
| R5.5 | D11 | Implemented and accepted within observed proof limits | `730bbe04ce7ba382367463dccca57bc39b7e0e92` |
| N1.1 | RM1 | Implemented and accepted within observed proof limits | `35e9ed10b0d97636d1b24819b29430c5444b291b` |
| N1.2 | TR1, RK4 | Implemented and accepted within observed proof limits | `35e9ed10b0d97636d1b24819b29430c5444b291b` |
| N1.4 | TR3, P5, EC2 prompt consumption | Implemented and accepted within observed proof limits | `35e9ed10b0d97636d1b24819b29430c5444b291b` |
| N2.2 | FA3 | Not adopted; original FA3 behavior gap remains | `35e9ed10b0d97636d1b24819b29430c5444b291b` |
| N2.3 | SE3 | Implemented and accepted within observed proof limits | `35e9ed10b0d97636d1b24819b29430c5444b291b` |
| N4.1 | BB4 | Implemented and accepted within observed proof limits | `35e9ed10b0d97636d1b24819b29430c5444b291b` |
| N4.2 | BB2 phrase wording | Implemented and accepted within observed proof limits | `35e9ed10b0d97636d1b24819b29430c5444b291b` |
| N4.3 | BB3, RK2 | Implemented and accepted within observed proof limits | `35e9ed10b0d97636d1b24819b29430c5444b291b` |
| N4.4 | CN2 | Implemented and accepted within observed proof limits | `35e9ed10b0d97636d1b24819b29430c5444b291b` |
| Nb.1 | RK1 | Kept: actual retained pair and final quoted better-reasoned Fable judgment | `856314e4b1dae655e8de548445a19af8c299dd51` |
| Nb.2 | ML1 | Not adopted; positive benefit unexercised and required better-reasoned judgment unavailable; original ML1 remains | `856314e4b1dae655e8de548445a19af8c299dd51` (disposition; not a behavior fix) |

CN3, H4 and H7 were checked as already sound; no implementation was needed. The approved plan controls FA2→R1.7 and ML1→Nb.2 where historical audit labels differ.

Amendment 1: R1 owns G2/G4/G5/G7; R3 owns G1/G3/G6/G9; Na retained G2p/G8p/G9p. The six-month default horizon is retained.

## Material corrections and actual closure

Historical builder corrections and independently verified material findings are distinguished below; disproved claims are not represented as fixes. Accepted-stage reports retain detailed regressions and Low dispositions. This table reuses preserved evidence and does not claim new tests or audits.

| Build | Correction / finding | Origin and disposition | Verified corrected source | Actual closure |
| --- | --- | --- | --- | --- |
| R5 | R5.6 source capture missed direct StockTwits/Reddit, reference-history bars and threaded optional post screen | builder-confirmed during frozen initial review; closed | `0308e892bba5f7e8d31461637f3c98eb3b23e42e` | `d017677d-9ee5-42bb-af5d-59eab4a26bd6` |
| R5 | Comparison settings omitted effort/temperature/quick-provider/token-cap differences | builder-confirmed during frozen initial review; closed | `0308e892bba5f7e8d31461637f3c98eb3b23e42e` | `d017677d-9ee5-42bb-af5d-59eab4a26bd6` |
| R5 | Background source work could leave a nominally complete baseline | builder-confirmed two-worker reproduction; closed | `0308e892bba5f7e8d31461637f3c98eb3b23e42e` | `d017677d-9ee5-42bb-af5d-59eab4a26bd6` |
| R5 | Social classification used wall clock; reference-history acquisition time incorrectly used comparison clock | builder-confirmed public-entry regressions; closed | `0308e892bba5f7e8d31461637f3c98eb3b23e42e` | `d017677d-9ee5-42bb-af5d-59eab4a26bd6` |
| R1 | G2 numeric display: nonzero subunit prices rendered zero or distinct bands had identical labels | builder-confirmed after initial freeze; closed | `87845f5a5a0ee31cd5928501ffbf13db266879b7` | `707b0bd1-3db6-4bab-b414-fd1d22148a74` |
| R1 | R1.4/G7 latest primary context selected only10-Q despite exact primary/comparison parser supporting10-K | builder-confirmed after initial freeze; closed | `87845f5a5a0ee31cd5928501ffbf13db266879b7` | `707b0bd1-3db6-4bab-b414-fd1d22148a74` |
| R2 | Stale pre-R2 wording assertions left in private replay test will fail once private inputs are available | actual initial Claude finding1; Medium confirmed; closed | `46433fad823fe882eea5a7894b3544ef65de92bd` | `6d00d60f-38e8-4c98-8fc4-32e773c2d3e2` |
| R4 | Plan acceptance checkboxes marked[x] cite test names that do not exist; no committed sanitized legacy-record fixture pinning publication hashes/kind-less load | actual initial Claude finding1; Medium partially confirmed; closed | `8ad5e1727deefa15d3f7b4c2da3e535da2ed7074` | `ad080c54-fb75-4f1e-bf1c-11d7c3c10c0b` |
| R3 | EX1 wording fix not implemented though R3.1 marked complete: current placeholders still name'evidence.json diagnostics' | actual initial Claude finding1; Medium confirmed; closed | `67865e678c9d3bda32a09939771d32e0e6d53d9e` | `79fa9f11-4c1a-4cb5-a7f4-a5e0e88987d7` |
| R3 | Closure receipt mis-binding: old e9ac805d history aliases corrected3559 receipt although old suite passed3552 | actual closure1 Claude Medium confirmed; closed | `03e5e29155ed0d3e8e8bfbb48123e9a57d1cb8ac` | `79fa9f11-4c1a-4cb5-a7f4-a5e0e88987d7` |
| R3 | Fresh/REVIEW diagnostics companion omits actual manager/market originals present in evidence raw_diagnostics | builder-confirmed runtime probe after clean static closure2; closed | `efbdd417fdd8ba177a2f80e4ab9c776f0679b27e` | `79fa9f11-4c1a-4cb5-a7f4-a5e0e88987d7` |
| R4-live-gap | Retained advisory conditions can grow without aggregate ceiling, warning or documented growth policy | actual initial Claude finding1; Medium partially confirmed; closed | `d6e8e3b69e719aa827f4204fc6c44708696df5e4` | `2615a9a9-c9df-4be4-8230-94c7cff64726` |
| Na | Observed MSFT disclosure-extraction regression: qualified OpenAI revenue claim lost after N2.2 omitted'inclusive of revenue-sharing payments' | actual interim finding1 and rubric finding1; Medium confirmed; not_adopted_original_gap_remains | `06e3171de2d083c5affd5d09f21106e30c6bf6e0` | `7617f414-e487-4fe5-8ddd-6e67f1fcf192` |
| Na | Controlled-comparison acceptance gate unmet: original candidate traces mixed_input with five misses each | actual interim finding3 and rubric finding2; Medium confirmed; closed | `3d1cc1d2f91d24bc2b0c4b7c56042760ceff1934` | `7617f414-e487-4fe5-8ddd-6e67f1fcf192` |
| Na | RM judgment explanation is HTML-escaped before HTML export and can reach editorial summary prompt | actual interim finding5; originallyLow, verified material by builder; closed | `3ebb1c7ff4f4444c3a60efad7d5c65b75217aaf2` | `7617f414-e487-4fe5-8ddd-6e67f1fcf192` |
| Na | Retained PM display entities also reach editorial summary input | builder-confirmed adjacent producer/consumer path; accepted by actual rubric closure; closed | `3ebcfa451025e880b64eca88b5262310c6536c9f` | `7617f414-e487-4fe5-8ddd-6e67f1fcf192` |
| Na | Acceptance-critical raw full test/lint logs and ledger absent from frozen packet | actual retained closure1 firstMedium; partially confirmed; closed | `dce76b2d6330d9fd63da03c82c2ea1e12f2b27c3` | `7617f414-e487-4fe5-8ddd-6e67f1fcf192` |
| Na | Independent Amendment2 acceptance and11-item retained rescore remain open | actual retained closure1 secondMedium; partially confirmed; closed | `dce76b2d6330d9fd63da03c82c2ea1e12f2b27c3` | `7617f414-e487-4fe5-8ddd-6e67f1fcf192` |
| Na | N4.3/N4.4 exact raw bodies of15matched debate and19later-role prompts missing from packet | actual retained rescore2 firstMedium; confirmed; closed | `8883bfd65faada400d4866ea7d1883c140e33451` | `7617f414-e487-4fe5-8ddd-6e67f1fcf192` |
| Na | Executed operator/controller equals supplied source and external trace bindings cannot be independently rehashed in frozen packet | actual retained rescore2 secondMedium; partially confirmed; closed | `8883bfd65faada400d4866ea7d1883c140e33451` | `7617f414-e487-4fe5-8ddd-6e67f1fcf192` |

R5 initial Medium claims about role allowlisting and automatic store isolation were disproved, not fixed. Na’s disputed-case interpretation claim was disproved against accepted safeguards; distinct evidence-completeness findings were actually closed. N2.2 was not adopted rather than repaired. Detailed stage receipts control any remaining per-finding qualification.

Nb material privacy closure: the partly confirmed future private-history push risk was closed through default denial plus verified clean public ancestry/content. Actual final Fable6eec6a8f accepted that bounded control; explicit-remote bypass remains disclosed. Required fresh checks passed before the real staging push. Current Low observations remain deferred/disclosed rather than silently erased.

## All paid analysis attempts

The analysis record reconciles 14 distinct authorized attempts and 302 wire calls: 12 analyses returned successfully and two failed. A completed historical or superseded source is not acceptance of the retained build. Failed attempts have no invented state/publication. Synthetic offline qualifications are excluded. The adjacent verification JSON retains exact source/state/receipt hashes; the full ledger stays private.

| Slot | Actual source | Publication | Disposition |
| --- | --- | --- | --- |
| phase1-DOCN | `9c252791a44d2a99c61c4224f8c9c35efc599e38` | None | Authorized failure; not acceptance |
| phase1-MSFT | `9c252791a44d2a99c61c4224f8c9c35efc599e38` | 7595b0e5-4719-406b-bfe3-965eb2e413f8 | Superseded source; not fresh baseline acceptance |
| phase1-DOCN-repeat1 | `9c252791a44d2a99c61c4224f8c9c35efc599e38` | None | Authorized failure; not acceptance |
| phase1-DOCN-repeat2 | `9c252791a44d2a99c61c4224f8c9c35efc599e38` | 20be4f7b-40a7-4541-a6dc-d564d61ca4f7 | Superseded source; not fresh baseline acceptance |
| phase1-fresh-DOCN | `ed24ec18d6b50734f378617755f60800e1d66aee` | 039e9ce6-d4a1-4f86-8723-a3531eef6cf5 | Accepted exact-source Phase1 baseline |
| phase1-fresh-MSFT | `ed24ec18d6b50734f378617755f60800e1d66aee` | 3f736b6a-2ce2-450b-8aa8-4eda0eeee459 | Accepted exact-source Phase1 baseline |
| Na-DOCN | `ab888b207d8886ee536e2fbd3ab6fb76f6f09a08` | e198b0ed-b84c-4b68-8d06-3e1e21a01ffe | Historical nonfinal candidate |
| Na-MSFT | `ab888b207d8886ee536e2fbd3ab6fb76f6f09a08` | 82e4a1df-a336-4e76-9e80-7d6cca302bdd | Historical nonfinal candidate |
| Na-retained-DOCN | `3d1cc1d2f91d24bc2b0c4b7c56042760ceff1934` | 89f493c3-6b2f-42de-a144-89c49be0d8d9 | Accepted retained Na; public35e9 equivalence recorded separately |
| Na-retained-MSFT | `3d1cc1d2f91d24bc2b0c4b7c56042760ceff1934` | 0d26a730-a63d-4e34-8a87-f4e67c4389a9 | Accepted retained Na; public35e9 equivalence recorded separately |
| Nb-DOCN | `6cd3e6c7d768cc33e913effad194bf681e5d1ef9` | 9a695a99-767b-43ff-8f93-50082f10e46e | Historical nonfinal candidate |
| Nb-MSFT | `6cd3e6c7d768cc33e913effad194bf681e5d1ef9` | 076ddf8c-417a-4348-b6a6-a3c571c2055b | Historical nonfinal candidate |
| Nb-retained-DOCN | `0addf8500f8f2d3875dcd1f2c24aa0cf5438427d` | e4cf660b-9a06-456e-adca-5bf8b90a0ede | Accepted retained Nb.1; combined-public bridge recorded separately |
| Nb-retained-MSFT | `0addf8500f8f2d3875dcd1f2c24aa0cf5438427d` | 924c8faf-c247-4a7d-8d6b-1ec99b361c2f | Accepted retained Nb.1; combined-public bridge recorded separately |

The earlier9c252791 source was equivalent to publicc4b70a36 but predates the condition-union correction. Only the fresh ed24 pair supplies the accepted corrected Phase1 baseline. OriginalNa ab888b20 comparisons are separate from the final3d1cc1d2 retained pair; candidate6cd3e6c7 is separate from final0addf850 Nb.1-only pair. All earlier charges and unknown holds remain counted.

## Observed baseline and comparison outcomes

| Source | DOCN | MSFT |
| --- | --- | --- |
| Accepted Phase 1 `ed24ec18` | Underweight; publication `039e9ce6-d4a1-4f86-8723-a3531eef6cf5` | REVIEW/insufficient; `3f736b6a-2ce2-450b-8aa8-4eda0eeee459` |
| Accepted Na private paid `3d1cc1d2`, application-equivalent to staging `35e9ed10` | Underweight/limited; `89f493c3-6b2f-42de-a144-89c49be0d8d9` | REVIEW/insufficient; `0d26a730-a63d-4e34-8a87-f4e67c4389a9` |
| Historical Nb two-change candidate `6cd3e6c7` | Underweight/limited; `9a695a99-767b-43ff-8f93-50082f10e46e` | REVIEW/insufficient; `076ddf8c-417a-4348-b6a6-a3c571c2055b` |
| Retained Nb.1-only actual `0addf850` | Underweight/limited; `e4cf660b-9a06-456e-adca-5bf8b90a0ede` | REVIEW/insufficient; `924c8faf-c247-4a7d-8d6b-1ec99b361c2f` |

Na and Nb use the same original pre-Na snapshot, ticker/date/analysis clock/models and separate disposable writes. Exact source payloads replay; novel queries return visibly typed unavailable data. Actual mixed_input labels remain. Source-envelope evidence supports the approved frozen-source interpretation; it is not independent wire telemetry or causal attribution. Current candidate calculations and model outputs were rerun, never replayed.

The historical Nb two-change candidate had DOCN3/MSFT2 typed unavailable source misses. The retained pair had DOCN2FRED and MSFTPolymarket+2FRED; all remain mixed_input. MSFT stopped at existing insufficient-evidence eligibility, so downstream risk/PM/memory judgments were not exercised. No eligible historical reflections were available at this historical cutoff: the actual lessons digest was empty. No lessons or timestamps were seeded to manufacture a comparison.

The historical two-change Nb candidate DOCN passed five actual PM numeric spot checks and three additional scenario arithmetic checks. MSFT passed five canonical numeric recomputations; these are not PM output or a cure for insufficient evidence. DOCN Base $75.61 uses borrowings_only; Na $93.73 uses finance_equipment. Different perimeters prevent a causal or like-for-like valuation comparison. Both Base cases remain disputed/excluded and unadopted. No publication adopted target or price range was invented.

The final retained DOCN source preserved 12 condition identities: four unchanged legacy objects and eight new ones (five metric, three event). Current publication, actual next-context reader and exactly-one memory link were reverified without changing immutable bytes. Several modern predicates overlap legacy conditions; this does not mean 12 distinct propositions. Legacy identities were preserved. Citation checks were 5/6 for the historical candidate, 7/10 with three visible flags for retained Nb, and 9/13 for Na. Coverage differs; mismatches remain visible, not erased. Retained-only produced no supported final shared case/target. Its five actual PM spot checks and two conditional EV/history calculations pass. MSFT’s five canonical checks pass. Its principal-inclusive cash-flow check of $17.633B is distinct from the earlier principal-exclusive $18.633B check. Both definitions have identical inputs/results across actual Na/candidate/retained states; no numeric drift is claimed.

## Historical diagnostic comparison

The preserved cfae95e9→fresh-ed24 DOCN diagnostic is uncontrolled and is not a pass/fail or causal gate: price/news/memory/context and model sampling can differ. Its original receipt SHA256 is `522f67c07ec1613fcadee9c4a43f4f1cec41f69f0dc746a62e8935679e6c4120`; the historical saved-state SHA is `d9505e263d70b0e59aba03d6f75c250c7c6d320e22070cbc5002876811e27f2b` and fresh state `6b269435d483f535fef9f2b0d5f1efc8630ef438f143ab989a7fff8e6dbf88fa`.

| Item | Observed | Inferred cause / limit |
| --- | --- | --- |
| Rating | Both Underweight. | None established; not a causal neutrality result. |
| Valuation | Neither has supported final target or adopted case. Historical Base record77.734375; fresh Base record72.932330827..., marked disputed and excluded from range; fresh scenario metadata1supported/1disputed. Conditional cases are not final targets. | The actual fresh PM accepted capital-structure objection. Differences in model assumptions, source/context and sampling are uncontrolled; no exclusive attribution. |
| First three retained conditions | Prior Revenue<348M and Gross Margin>=55.5%/<50.15% identities remain in retained collection order. Fresh PM explicitly keeps all4 prior IDs and adds7 new definitions/events. | Recorded keeps explain identity retention; this is not a separate rank of the PM preferred top three. |
| Horizon | Historical4–6months explicit text; fresh6months configured default. | Configured horizon now delivered; not proof of a recommendation effect. |
| RPO context | Historical shared brief lacks the RPO history summary; fresh contains it. | Source assembly supplies history; downstream rating impact not isolated. |

“First three” refers to the visible retained collection order, not an independently ranked PM preference. Retained Na/Nb keep the original Revenue<348M and GrossMargin>=55.5%/<50.15% identities; no ranking or automatic trading rule is invented.

## Financial evidence

After all named retained analyses, verified charges are $69.81232475 plus $76.227120 unknown holds, total $146.03944475 against the $235 whole-task analysis ceiling. Unknown holds remain counted. DOCN candidate exposure $15.64722640 was below its $30 cap; MSFT $5.414912 below its $20 cap. Retained DOCN exposure was $15.3236958 against its $30 cap; retained MSFT was $5.312436 against $20. No further named analysis slots/retries remain automatic. Account allowance is capacity, not extra spending authority. Independent audits use separate unchanged caps.

## Preserved current staging and combined-source proof

Canonical staging advanced independently from35e9 to5e1c86b64f85e078dbdeb05ac9dc966d23031333 during Nb, adding the separately accepted opt-in Ground Truth feature. The discrepancy was reported; no reset or silent rebase occurred. Native clean preparationa8156e0ac470577a52caf86bb2f150b74748916c starts from exact5e1 and copies only5Nb.1source/testblobs. The accepted new feature is preserved. BaseCI42549961745 passed all7jobs; no futureNbCI pass is inferred.

The retained private candidate passed 3,594 tests, with 10 skipped, one deselected and 100 subtests, in 83.49 seconds. The combined public candidate passed 3,960 with the same skips, deselection and subtests in 171.80 seconds. Both passed Ruff. Their agent prompt fingerprint `8df3f48e` matches; overall code, state and report bytes differ. The real offline public CLI passed 28 synthetic requests, nine risk turns, publication, memory and reports with `--no-ground-truth-audit`. Raw callback equality remains false: 22 direct message metadata UUIDs differ across eight events. The installed SDK produced byte-equal dictionaries for all 28 requests; negative controls protect content, nested tool IDs and arguments. This explicit exception supports the affected-path bridge; it is not another paid public run or wire-causality proof.

Default privatepush denial and clean public ancestry/content checks pass. All private raw prompts/ledger/history remain local; only accepted source and sanitized summaries may be published after actual closure. The first offline public fixture correctly rejected a consumed real claim before wire. Its separate hard-offline syntheticnamespace correction preserves all realclaims/globalledger and passed; no paidretry or gate removal.

The original approved Amendment 1 appendix remains verbatim, including its historical planning checkboxes. Current host-build copies and this report record disposition. All 26 named checks map to actual definitions or equivalent assertions inspected in the current source; that mapping is not a new test run.

## Actual final acceptance

Actual Fable initial8e518b38 completed79turns/$6.750577 with oneMediumprivacy/sixLow. Its original Nb.2 KEEP-with-unexercised-disclosure judgment remains preserved; strict item4 required a positive quoted better-reasoned judgment it did not supply, so Nb.2 was dropped. The named retained DOCN/MSFT pair is complete on exact0addf850. Actual final Fable rescore/material closure `6eec6a8f-9e7a-4f39-8dc0-5ff2e4c6cf00` completed normally at private frozen `badcacb9`:74turns,$4.9158405,zero Critical/High/Medium and eight verified Low findings/limits. It returned the required quoted better-reasoned KEEP for Nb.1, confirmed Nb.2 not adopted, and closed the privacy Medium. Its3893813-byte request supplied35complete sources, the full retained5-filediff and42actual prompt/output trees. Frozen manifest validation passed before advancing the docs-only record. Actual Nb audit total$11.6664175 under unchanged$50cap. No automatic failed-run retries.

Accepted implementation staging SHA is `856314e4b1dae655e8de548445a19af8c299dd51`; exact CI42560106100 completed all7jobs successfully, including Python3.11–3.14 and NewYork. All source/test/dependency/CI objects match the locally tested combineda815 source. Fresh pre-push checks excluded all10private Nb commits and22private raw/doc objects, with a strict8-path whitelist and zero known-credential hits. Raw prompts, financial ledger and private Git ancestry remain local. The final report delivery changes only documentation and preserves these receipts; exact delivery CI is separately verified.

## Limits and release boundary

Two tickers on one date and model sampling limit conclusions. Observed output differences do not establish causes. Source/cache telemetry, unavailable data, unmatched citations, unexercised positive branches and deferred Low findings remain disclosed in stage records. R2 relevance is conservative; identity batching/legacy overlap, currency-less price conditions and bounded citation/locator limits remain documented.

Production remains `9ade69bf155d1b25699d3aecfff3c1b07752aff0`. Staging is an unreleased development outcome. Production promotion, stable-app installation/replacement/launch and exact-production Machine 1 acceptance were not performed and need separate authority. No PR or worktree cleanup is authorized here.
