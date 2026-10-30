# Review batch 2 — gold and rule trace

> FICTIONAL insurer and synthetic tickets; dev split only (held-out is never shown). Items: the 50 from dev_review.md (selection seed `20261030:review`), batched with seed `20261030:review-batches`.

## dev-0050

**Gold:** `{"decision":"partial","payout_sar":7225,"reasons":["R4_THIRD_PARTY"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-08-20","other_party":"insured","fault_share":25,"damage_amount_sar":28900,"recovery_cases":[]}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-08-20 vs policy end 2026-11-07 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 3 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | no | none; licence=valid, renewed=None |
| 8 | R4 | policyholder 0% at fault | no | fault=25% |
| 9 | R4 | payout = damage x fault share, capped | no | 28900 x 25% = 7225; cap 10000000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0271

**Gold:** `{"answer":60}`

Verdict: ☐ agree ☐ label error — note:

## dev-0087

**Gold:** `{"decision":"approve","payout_sar":40750,"reasons":["R3_OWN_DAMAGE"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-09-16","other_party":"uninsured","fault_share":25,"damage_amount_sar":41000,"sum_insured_sar":176000,"base_sar":41000,"deductible_applied_sar":250,"total_loss":false}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-09-16 vs policy end 2027-05-25 |
| 3 | R5 | CMIR 7.2 licence valid (expired only: renewed on or before the business-day-50 date) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 0 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 41000 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | no | repair 41000 vs 60% x 176000 = 105600; technical=False |
| 11 | R3 | deductible applied | **yes** | 1000 x 25% (CMIR 5.4.3/5.4.4) = 250 |
| 12 | R3 | payout = base - deductible | **yes** | 41000 - 250 = 40750 |

Verdict: ☐ agree ☐ label error — note:

## dev-0164

**Gold:** `{"intent":"other"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0331

**Gold:** `{"policy_number":null,"accident_date":null,"report_number":"TP-06552573","damage_amount_sar":30100,"fault_share":null}`

Verdict: ☐ agree ☐ label error — note:

## dev-0355

**Gold:** `{"decision":"need_info","payout_sar":0,"reasons":["R7_MISSING_registration"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-03-10","other_party":"insured","fault_share":100,"damage_amount_sar":39700}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-03-10 vs policy end 2026-12-23 |
| 3 | R5 | CMIR 7.2 licence valid (expired only: renewed on or before the business-day-50 date) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 11 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 39700 vs full deductible 1000 |
| 8 | R7 | all required documents present | **yes** | missing=['registration'] |

Verdict: ☐ agree ☐ label error — note:

## dev-0127

**Gold:** `{"decision":"partial","payout_sar":28125,"reasons":["R4_THIRD_PARTY","RECOVERY_RIGHT"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-02-06","other_party":"insured","fault_share":75,"damage_amount_sar":37500,"recovery_cases":["invalid_licence"]}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-02-06 vs policy end 2026-10-17 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 13 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | **yes** | ['invalid_licence']; licence=expired, renewed=2026-04-03 |
| 8 | R4 | policyholder 0% at fault | no | fault=75% |
| 9 | R4 | payout = damage x fault share, capped | no | 37500 x 75% = 28125; cap 10000000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0010

**Gold:** `{"answer":7}`

Verdict: ☐ agree ☐ label error — note:

## dev-0177

**Gold:** `{"policy_number":"OMI-8596031","accident_date":null,"report_number":"NJ-91103513","damage_amount_sar":18600,"fault_share":null}`

Verdict: ☐ agree ☐ label error — note:

## dev-0254

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R6_LATE_REPORT"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-01-09","other_party":"insured","fault_share":0,"damage_amount_sar":11600}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-01-09 vs policy end 2026-09-24 |
| 3 | R5 | CMIR 7.2 licence valid (expired only: renewed on or before the business-day-50 date) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | **yes** | 26 days vs 15; justification=None |

Verdict: ☐ agree ☐ label error — note:
