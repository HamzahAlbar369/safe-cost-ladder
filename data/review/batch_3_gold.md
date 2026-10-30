# Review batch 3 — gold and rule trace

> FICTIONAL insurer and synthetic tickets; dev split only (held-out is never shown). Items: the 50 from dev_review.md (selection seed `20261030:review`), batched with seed `20261030:review-batches`.

## dev-0183

**Gold:** `{"policy_number":"OMI-8392971","accident_date":null,"report_number":"NJ-76220189","damage_amount_sar":null,"fault_share":null}`

Verdict: ☐ agree ☐ label error — note:

## dev-0306

**Gold:** `{"decision":"partial","payout_sar":20700,"reasons":["R4_THIRD_PARTY"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-02-20","other_party":"insured","fault_share":50,"damage_amount_sar":41400,"recovery_cases":[]}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-02-20 vs policy end 2026-06-03 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 13 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | no | none; licence=valid, renewed=None |
| 8 | R4 | policyholder 0% at fault | no | fault=50% |
| 9 | R4 | payout = damage x fault share, capped | no | 41400 x 50% = 20700; cap 10000000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0266

**Gold:** `{"intent":"fault_dispute"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0223

**Gold:** `{"decision":"need_info","payout_sar":0,"reasons":["R7_MISSING_damage_assessment"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-07-24","other_party":"insured","fault_share":0,"damage_amount_sar":21700}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-07-24 vs policy end 2027-05-17 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 14 days vs 15; justification=None |
| 7 | R7 | all required documents present | **yes** | missing=['damage_assessment'] |

Verdict: ☐ agree ☐ label error — note:

## dev-0135

**Gold:** `{"intent":"new_claim"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0048

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R5_OD_invalid_licence"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-08-25","other_party":"insured","fault_share":75,"damage_amount_sar":22500}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-08-25 vs policy end 2027-06-08 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | **yes** | status=none, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |

Verdict: ☐ agree ☐ label error — note:

## dev-0326

**Gold:** `{"decision":"approve","payout_sar":22250,"reasons":["R3_OWN_DAMAGE","SUBROGATION"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-04-25","other_party":"insured","fault_share":25,"damage_amount_sar":22500,"sum_insured_sar":94000,"base_sar":22500,"deductible_applied_sar":250,"total_loss":false}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-04-25 vs policy end 2026-05-18 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=domestic_worker |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 14 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 22500 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | no | repair 22500 vs 60% x 94000 = 56400; technical=False |
| 11 | R3 | deductible applied | **yes** | 1000 x 25% (CMIR 5.4.3/5.4.4) = 250 |
| 12 | R3 | payout = base - deductible | **yes** | 22500 - 250 = 22250 |

Verdict: ☐ agree ☐ label error — note:

## dev-0078

**Gold:** `{"answer":1000}`

Verdict: ☐ agree ☐ label error — note:

## dev-0270

**Gold:** `{"decision":"partial","payout_sar":84000,"reasons":["R3_OWN_DAMAGE","R3_TOTAL_LOSS","R3_SUM_INSURED_CAP","SUBROGATION"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-07-17","other_party":"insured","fault_share":0,"damage_amount_sar":98900,"sum_insured_sar":84000,"base_sar":84000,"deductible_applied_sar":0,"total_loss":true}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-07-17 vs policy end 2026-08-22 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 10 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 98900 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | **yes** | repair 98900 vs 60% x 84000 = 50400; technical=False |
| 11 | R3 | deductible applied | no | 1000 x 0% (CMIR 5.4.3/5.4.4) = 0 |
| 12 | R3 | payout = base - deductible | **yes** | 84000 - 0 = 84000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0282

**Gold:** `{"decision":"partial","payout_sar":18450,"reasons":["R4_THIRD_PARTY","RECOVERY_RIGHT"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-03-01","other_party":"insured","fault_share":75,"damage_amount_sar":24600,"recovery_cases":["invalid_licence"]}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-03-01 vs policy end 2026-06-24 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 11 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | **yes** | ['invalid_licence']; licence=expired, renewed=2026-04-25 |
| 8 | R4 | policyholder 0% at fault | no | fault=75% |
| 9 | R4 | payout = damage x fault share, capped | no | 24600 x 75% = 18450; cap 10000000 |

Verdict: ☐ agree ☐ label error — note:
