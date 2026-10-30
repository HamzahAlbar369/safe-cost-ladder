# Review batch 2 — gold and rule trace

> FICTIONAL insurer and synthetic tickets; dev split only (held-out is never shown). Items: the 50 from dev_review.md (selection seed `20261030:review`), batched with seed `20261030:review-batches`.

## dev-0378

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R4_NO_FAULT"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-06-22","other_party":"insured","fault_share":0,"damage_amount_sar":33900}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-06-22 vs policy end 2026-12-29 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 3 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | no | none; licence=valid, renewed=None |
| 8 | R4 | policyholder 0% at fault | **yes** | fault=0% |

Verdict: ☐ agree ☐ label error — note:

## dev-0095

**Gold:** `{"answer":60}`

Verdict: ☐ agree ☐ label error — note:

## dev-0194

**Gold:** `{"decision":"partial","payout_sar":10700,"reasons":["R4_THIRD_PARTY"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-09-12","other_party":"insured","fault_share":25,"damage_amount_sar":42800,"recovery_cases":[]}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-09-12 vs policy end 2027-03-06 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 11 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | no | none; licence=valid, renewed=None |
| 8 | R4 | policyholder 0% at fault | no | fault=25% |
| 9 | R4 | payout = damage x fault share, capped | no | 42800 x 25% = 10700; cap 10000000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0390

**Gold:** `{"policy_number":"OMI-2954271","accident_date":null,"report_number":"NJ-90829199","damage_amount_sar":15100,"fault_share":null}`

Verdict: ☐ agree ☐ label error — note:

## dev-0290

**Gold:** `{"intent":"payment_issue"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0396

**Gold:** `{"decision":"need_info","payout_sar":0,"reasons":["R7_MISSING_damage_photos"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-01-31","other_party":"insured","fault_share":50,"damage_amount_sar":39700}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-01-31 vs policy end 2026-11-09 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 14 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 39700 vs full deductible 1000 |
| 8 | R7 | all required documents present | **yes** | missing=['damage_photos'] |

Verdict: ☐ agree ☐ label error — note:

## dev-0227

**Gold:** `{"decision":"need_info","payout_sar":0,"reasons":["R7_CONFLICT"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-02-10","other_party":"insured","fault_share":50,"damage_amount_sar":10600}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-02-10 vs policy end 2026-03-24 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 11 days vs 15; justification=None |
| 7 | R7 | all required documents present | no | missing=[] |
| 8 | R7 | two stated damage amounts contradict | **yes** | 10600 vs 8300 |

Verdict: ☐ agree ☐ label error — note:

## dev-0367

**Gold:** `{"answer":3}`

Verdict: ☐ agree ☐ label error — note:

## dev-0072

**Gold:** `{"policy_number":"OMI-4972420","accident_date":"2026-02-22","report_number":"NJ-18172738","damage_amount_sar":25300,"fault_share":50}`

Verdict: ☐ agree ☐ label error — note:

## dev-0329

**Gold:** `{"decision":"partial","payout_sar":61000,"reasons":["R3_OWN_DAMAGE","R3_TOTAL_LOSS","R3_SUM_INSURED_CAP"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-02-12","other_party":"none","fault_share":null,"damage_amount_sar":62900,"sum_insured_sar":62000,"base_sar":62000,"deductible_applied_sar":1000,"total_loss":true}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-02-12 vs policy end 2026-05-27 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 6 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 62900 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | **yes** | repair 62900 vs 60% x 62000 = 37200; technical=False |
| 11 | R3 | deductible applied | **yes** | no other party: full deductible (CMIR 5.4.5, interpretation) = 1000 |
| 12 | R3 | payout = base - deductible | **yes** | 62000 - 1000 = 61000 |

Verdict: ☐ agree ☐ label error — note:
