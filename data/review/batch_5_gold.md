# Review batch 5 — gold and rule trace

> FICTIONAL insurer and synthetic tickets; dev split only (held-out is never shown). Items: the 50 from dev_review.md (selection seed `20261030:review`), batched with seed `20261030:review-batches`.

## dev-0168

**Gold:** `{"decision":"partial","payout_sar":28250,"reasons":["R3_OWN_DAMAGE","R3_TOTAL_LOSS","R3_SUM_INSURED_CAP","SUBROGATION"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-06-01","other_party":"insured","fault_share":75,"damage_amount_sar":31700,"sum_insured_sar":29000,"base_sar":29000,"deductible_applied_sar":750,"total_loss":true}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-06-01 vs policy end 2027-03-01 |
| 3 | R5 | CMIR 7.2 licence valid (expired only: renewed on or before the business-day-50 date) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 15 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 31700 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | **yes** | repair 31700 vs 60% x 29000 = 17400; technical=False |
| 11 | R3 | deductible applied | **yes** | 1000 x 75% (CMIR 5.4.3/5.4.4) = 750 |
| 12 | R3 | payout = base - deductible | **yes** | 29000 - 750 = 28250 |

Verdict: ☐ agree ☐ label error — note:

## dev-0068

**Gold:** `{"decision":"need_info","payout_sar":0,"reasons":["R7_MISSING_damage_assessment"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-04-24","other_party":"insured","fault_share":100,"damage_amount_sar":12700}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-04-24 vs policy end 2026-10-13 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 7 days vs 15; justification=None |
| 5 | R7 | all required documents present | **yes** | missing=['damage_assessment'] |

Verdict: ☐ agree ☐ label error — note:

## dev-0019

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R6_LATE_REPORT"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-05-12","other_party":"insured","fault_share":25,"damage_amount_sar":52800}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-05-12 vs policy end 2026-11-28 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | **yes** | 45 days vs 15; justification=None |

Verdict: ☐ agree ☐ label error — note:

## dev-0243

**Gold:** `{"decision":"partial","payout_sar":17500,"reasons":["R4_THIRD_PARTY"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-03-07","other_party":"insured","fault_share":50,"damage_amount_sar":35000,"recovery_cases":[]}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-03-07 vs policy end 2026-12-26 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 0 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | no | none; licence=valid, renewed=None |
| 8 | R4 | policyholder 0% at fault | no | fault=50% |
| 9 | R4 | payout = damage x fault share, capped | no | 35000 x 50% = 17500; cap 10000000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0092

**Gold:** `{"decision":"need_info","payout_sar":0,"reasons":["R7_CONFLICT"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-08-26","other_party":"insured","fault_share":100,"damage_amount_sar":44500}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-08-26 vs policy end 2027-03-18 |
| 3 | R5 | CMIR 7.2 licence valid (expired only: renewed on or before the business-day-50 date) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 7 days vs 15; justification=None |
| 7 | R7 | all required documents present | no | missing=[] |
| 8 | R7 | two stated damage amounts contradict | **yes** | 44500 vs 43500 |

Verdict: ☐ agree ☐ label error — note:

## dev-0229

**Gold:** `{"policy_number":"OMI-2557732","accident_date":"2026-07-29","report_number":"TP-70476788","damage_amount_sar":18000,"fault_share":null}`

Verdict: ☐ agree ☐ label error — note:

## dev-0093

**Gold:** `{"answer":1000}`

Verdict: ☐ agree ☐ label error — note:

## dev-0262

**Gold:** `{"decision":"need_info","payout_sar":0,"reasons":["R7_MISSING_registration"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-07-10","other_party":"insured","fault_share":50,"damage_amount_sar":54800}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-07-10 vs policy end 2026-10-23 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 3 days vs 15; justification=None |
| 5 | R7 | all required documents present | **yes** | missing=['registration'] |

Verdict: ☐ agree ☐ label error — note:

## dev-0082

**Gold:** `{"answer":1000}`

Verdict: ☐ agree ☐ label error — note:

## dev-0265

**Gold:** `{"intent":"complaint"}`

Verdict: ☐ agree ☐ label error — note:
