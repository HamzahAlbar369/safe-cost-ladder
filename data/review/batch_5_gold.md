# Review batch 5 — gold and rule trace

> FICTIONAL insurer and synthetic tickets; dev split only (held-out is never shown). Items: the 50 from dev_review.md (selection seed `20261030:review`), batched with seed `20261030:review-batches`.

## dev-0354

**Gold:** `{"decision":"approve","payout_sar":2050,"reasons":["R3_OWN_DAMAGE","SUBROGATION"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-09-01","other_party":"insured","fault_share":75,"damage_amount_sar":2800,"sum_insured_sar":87000,"base_sar":2800,"deductible_applied_sar":750,"total_loss":false}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-09-01 vs policy end 2026-10-03 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=['wrong_direction'], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 5 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 2800 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | no | repair 2800 vs 60% x 87000 = 52200; technical=False |
| 11 | R3 | deductible applied | **yes** | 1000 x 75% (CMIR 5.4.3/5.4.4) = 750 |
| 12 | R3 | payout = base - deductible | **yes** | 2800 - 750 = 2050 |

Verdict: ☐ agree ☐ label error — note:

## dev-0275

**Gold:** `{"decision":"approve","payout_sar":29800,"reasons":["R3_OWN_DAMAGE","SUBROGATION"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-08-16","other_party":"insured","fault_share":0,"damage_amount_sar":29800,"sum_insured_sar":58000,"base_sar":29800,"deductible_applied_sar":0,"total_loss":false}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-08-16 vs policy end 2026-11-02 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 4 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 29800 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | no | repair 29800 vs 60% x 58000 = 34800; technical=False |
| 11 | R3 | deductible applied | no | 1000 x 0% (CMIR 5.4.3/5.4.4) = 0 |
| 12 | R3 | payout = base - deductible | **yes** | 29800 - 0 = 29800 |

Verdict: ☐ agree ☐ label error — note:

## dev-0318

**Gold:** `{"decision":"need_info","payout_sar":0,"reasons":["R7_CONFLICT"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-05-11","other_party":"insured","fault_share":75,"damage_amount_sar":7300}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-05-11 vs policy end 2026-09-07 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 14 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | **yes** | 7300 vs 3800 |

Verdict: ☐ agree ☐ label error — note:

## dev-0274

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R5_OD_invalid_licence"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-04-30","other_party":"insured","fault_share":100,"damage_amount_sar":34900}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-04-30 vs policy end 2026-08-30 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | **yes** | status=expired, renewed=2026-07-15 |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |

Verdict: ☐ agree ☐ label error — note:

## dev-0331

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R6_LATE_REPORT"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-09-01","other_party":"insured","fault_share":25,"damage_amount_sar":57700}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-09-01 vs policy end 2027-06-08 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | **yes** | 18 days vs 15; justification=None |

Verdict: ☐ agree ☐ label error — note:

## dev-0139

**Gold:** `{"policy_number":"OMI-5148967","accident_date":"2026-03-27","report_number":"NJ-34875061","damage_amount_sar":null,"fault_share":null}`

Verdict: ☐ agree ☐ label error — note:

## dev-0295

**Gold:** `{"answer":250}`

Verdict: ☐ agree ☐ label error — note:

## dev-0309

**Gold:** `{"decision":"partial","payout_sar":57250,"reasons":["R3_OWN_DAMAGE","R3_TOTAL_LOSS","R3_SUM_INSURED_CAP","SUBROGATION"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-03-25","other_party":"insured","fault_share":75,"damage_amount_sar":67800,"sum_insured_sar":58000,"base_sar":58000,"deductible_applied_sar":750,"total_loss":true}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-03-25 vs policy end 2026-11-18 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 15 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 67800 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | **yes** | repair 67800 vs 60% x 58000 = 34800; technical=False |
| 11 | R3 | deductible applied | **yes** | 1000 x 75% (CMIR 5.4.3/5.4.4) = 750 |
| 12 | R3 | payout = base - deductible | **yes** | 58000 - 750 = 57250 |

Verdict: ☐ agree ☐ label error — note:

## dev-0353

**Gold:** `{"answer":2000}`

Verdict: ☐ agree ☐ label error — note:

## dev-0296

**Gold:** `{"intent":"document_submission"}`

Verdict: ☐ agree ☐ label error — note:
