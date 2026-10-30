# Review batch 4 — gold and rule trace

> FICTIONAL insurer and synthetic tickets; dev split only (held-out is never shown). Items: the 50 from dev_review.md (selection seed `20261030:review`), batched with seed `20261030:review-batches`.

## dev-0202

**Gold:** `{"intent":"claim_status"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0263

**Gold:** `{"decision":"approve","payout_sar":40050,"reasons":["R3_OWN_DAMAGE","SUBROGATION"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-08-11","other_party":"insured","fault_share":25,"damage_amount_sar":40300,"sum_insured_sar":103000,"base_sar":40300,"deductible_applied_sar":250,"total_loss":false}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-08-11 vs policy end 2027-01-26 |
| 3 | R5 | CMIR 7.2 licence valid (expired only: renewed on or before the business-day-50 date) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 1 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 40300 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | no | repair 40300 vs 60% x 103000 = 61800; technical=False |
| 11 | R3 | deductible applied | **yes** | 1000 x 25% (CMIR 5.4.3/5.4.4) = 250 |
| 12 | R3 | payout = base - deductible | **yes** | 40300 - 250 = 40050 |

Verdict: ☐ agree ☐ label error — note:

## dev-0256

**Gold:** `{"answer":"no"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0077

**Gold:** `{"decision":"need_info","payout_sar":0,"reasons":["R7_CONFLICT"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-03-02","other_party":"insured","fault_share":50,"damage_amount_sar":57100}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-03-02 vs policy end 2026-09-01 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 6 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | **yes** | 57100 vs 60900 |

Verdict: ☐ agree ☐ label error — note:

## dev-0195

**Gold:** `{"decision":"approve","payout_sar":49100,"reasons":["R4_THIRD_PARTY"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-01-11","other_party":"insured","fault_share":100,"damage_amount_sar":49100,"recovery_cases":[]}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-01-11 vs policy end 2026-04-07 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 4 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | no | none; licence=valid, renewed=None |
| 8 | R4 | policyholder 0% at fault | no | fault=100% |
| 9 | R4 | payout = damage x fault share, capped | no | 49100 x 100% = 49100; cap 10000000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0030

**Gold:** `{"decision":"approve","payout_sar":42200,"reasons":["R3_OWN_DAMAGE","R8_UNKNOWN_PARTY"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-02-02","other_party":"unknown","fault_share":null,"damage_amount_sar":42200,"sum_insured_sar":131000,"base_sar":42200,"deductible_applied_sar":0,"total_loss":false}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-02-02 vs policy end 2026-03-12 |
| 3 | R5 | CMIR 7.2 licence valid (expired only: renewed on or before the business-day-50 date) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 6 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 42200 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | no | repair 42200 vs 60% x 131000 = 78600; technical=False |
| 11 | R3 | deductible applied | no | hit-and-run: no deductible (CMIR 5.4.4) = 0 |
| 12 | R3 | payout = base - deductible | **yes** | 42200 - 0 = 42200 |

Verdict: ☐ agree ☐ label error — note:

## dev-0323

**Gold:** `{"policy_number":null,"accident_date":null,"report_number":"NJ-50281869","damage_amount_sar":27500,"fault_share":50}`

Verdict: ☐ agree ☐ label error — note:

## dev-0120

**Gold:** `{"decision":"approve","payout_sar":20700,"reasons":["R4_THIRD_PARTY"],"inputs":{"claim_type":"third_party_claim","cover":"TPL","accident_date":"2026-03-01","other_party":"insured","fault_share":100,"damage_amount_sar":20700,"recovery_cases":[]}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-03-01 vs policy end 2026-11-17 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 6 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | no | none; licence=valid, renewed=None |
| 8 | R4 | policyholder 0% at fault | no | fault=100% |
| 9 | R4 | payout = damage x fault share, capped | no | 20700 x 100% = 20700; cap 10000000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0292

**Gold:** `{"decision":"approve","payout_sar":23700,"reasons":["R3_OWN_DAMAGE","R6_JUSTIFIED"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-03-18","other_party":"insured","fault_share":100,"damage_amount_sar":24700,"sum_insured_sar":61000,"base_sar":24700,"deductible_applied_sar":1000,"total_loss":false}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-03-18 vs policy end 2026-05-03 |
| 3 | R5 | CMIR 7.2 licence valid (expired only: renewed on or before the business-day-50 date) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 39 days vs 15; justification=travel_outside_kingdom |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 24700 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | no | repair 24700 vs 60% x 61000 = 36600; technical=False |
| 11 | R3 | deductible applied | **yes** | 1000 x 100% (CMIR 5.4.3/5.4.4) = 1000 |
| 12 | R3 | payout = base - deductible | **yes** | 24700 - 1000 = 23700 |

Verdict: ☐ agree ☐ label error — note:

## dev-0103

**Gold:** `{"policy_number":"OMI-1341071","accident_date":null,"report_number":null,"damage_amount_sar":null,"fault_share":25}`

Verdict: ☐ agree ☐ label error — note:
