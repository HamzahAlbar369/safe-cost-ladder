# Review batch 3 — gold and rule trace

> FICTIONAL insurer and synthetic tickets; dev split only (held-out is never shown). Items: the 50 from dev_review.md (selection seed `20261030:review`), batched with seed `20261030:review-batches`.

## dev-0121

**Gold:** `{"intent":"policy_change"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0313

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

## dev-0227

**Gold:** `{"policy_number":"OMI-4568354","accident_date":"2026-09-28","report_number":"NJ-52455198","damage_amount_sar":null,"fault_share":null}`

Verdict: ☐ agree ☐ label error — note:

## dev-0217

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R5_OD_invalid_licence"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-03-20","other_party":"insured","fault_share":25,"damage_amount_sar":18500}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-03-20 vs policy end 2026-08-20 |
| 3 | R5 | CMIR 7.2 licence valid (expired only: renewed on or before the business-day-50 date) | **yes** | status=wrong_class, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |

Verdict: ☐ agree ☐ label error — note:

## dev-0040

**Gold:** `{"intent":"document_submission"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0361

**Gold:** `{"decision":"need_info","payout_sar":0,"reasons":["R7_MISSING_licence_copy"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-08-19","other_party":"insured","fault_share":25,"damage_amount_sar":3600}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-08-19 vs policy end 2027-02-04 |
| 3 | R5 | CMIR 7.2 licence valid (expired only: renewed on or before the business-day-50 date) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 8 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 3600 vs full deductible 1000 |
| 8 | R7 | all required documents present | **yes** | missing=['licence_copy'] |

Verdict: ☐ agree ☐ label error — note:

## dev-0100

**Gold:** `{"decision":"partial","payout_sar":2700,"reasons":["R4_THIRD_PARTY"],"inputs":{"claim_type":"third_party_claim","cover":"TPL","accident_date":"2026-06-29","other_party":"insured","fault_share":75,"damage_amount_sar":3600,"recovery_cases":[]}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-06-29 vs policy end 2026-12-12 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 11 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | no | none; licence=valid, renewed=None |
| 8 | R4 | policyholder 0% at fault | no | fault=75% |
| 9 | R4 | payout = damage x fault share, capped | no | 3600 x 75% = 2700; cap 10000000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0324

**Gold:** `{"answer":10000000}`

Verdict: ☐ agree ☐ label error — note:

## dev-0190

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R3_BELOW_DEDUCTIBLE"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-03-22","other_party":"insured","fault_share":25,"damage_amount_sar":400}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-03-22 vs policy end 2026-07-22 |
| 3 | R5 | CMIR 7.2 licence valid (expired only: renewed on or before the business-day-50 date) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 7 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | **yes** | repair 400 vs full deductible 1000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0399

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R4_NO_FAULT"],"inputs":{"claim_type":"third_party_claim","cover":"TPL","accident_date":"2026-04-21","other_party":"insured","fault_share":0,"damage_amount_sar":7800}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-04-21 vs policy end 2026-12-05 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 2 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | no | none; licence=valid, renewed=None |
| 8 | R4 | policyholder 0% at fault | **yes** | fault=0% |

Verdict: ☐ agree ☐ label error — note:
