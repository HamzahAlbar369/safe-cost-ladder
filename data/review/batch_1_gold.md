# Review batch 1 — gold and rule trace

> FICTIONAL insurer and synthetic tickets; dev split only (held-out is never shown). Items: the 50 from dev_review.md (selection seed `20261030:review`), batched with seed `20261030:review-batches`.

## dev-0060

**Gold:** `{"intent":"complaint"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0337

**Gold:** `{"decision":"approve","payout_sar":4350,"reasons":["R3_OWN_DAMAGE","SUBROGATION"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-09-09","other_party":"insured","fault_share":25,"damage_amount_sar":4600,"sum_insured_sar":72000,"base_sar":4600,"deductible_applied_sar":250,"total_loss":false}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-09-09 vs policy end 2027-05-07 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=['racing_or_drifting'], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 7 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 4600 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | no | repair 4600 vs 60% x 72000 = 43200; technical=False |
| 11 | R3 | deductible applied | **yes** | 1000 x 25% (CMIR 5.4.3/5.4.4) = 250 |
| 12 | R3 | payout = base - deductible | **yes** | 4600 - 250 = 4350 |

Verdict: ☐ agree ☐ label error — note:

## dev-0304

**Gold:** `{"answer":"yes"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0264

**Gold:** `{"policy_number":"OMI-9049579","accident_date":null,"report_number":"NJ-32775235","damage_amount_sar":25400,"fault_share":null}`

Verdict: ☐ agree ☐ label error — note:

## dev-0215

**Gold:** `{"policy_number":"OMI-5577683","accident_date":"2026-04-27","report_number":"NJ-13456987","damage_amount_sar":11000,"fault_share":100}`

Verdict: ☐ agree ☐ label error — note:

## dev-0133

**Gold:** `{"decision":"approve","payout_sar":41500,"reasons":["R3_OWN_DAMAGE","SUBROGATION"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-08-10","other_party":"insured","fault_share":0,"damage_amount_sar":41500,"sum_insured_sar":157000,"base_sar":41500,"deductible_applied_sar":0,"total_loss":false}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-08-10 vs policy end 2027-01-19 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 3 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 41500 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | no | repair 41500 vs 60% x 157000 = 94200; technical=False |
| 11 | R3 | deductible applied | no | 1000 x 0% (CMIR 5.4.3/5.4.4) = 0 |
| 12 | R3 | payout = base - deductible | **yes** | 41500 - 0 = 41500 |

Verdict: ☐ agree ☐ label error — note:

## dev-0287

**Gold:** `{"answer":"no"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0391

**Gold:** `{"decision":"need_info","payout_sar":0,"reasons":["R7_MISSING_licence_copy"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-07-30","other_party":"insured","fault_share":25,"damage_amount_sar":39700}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-07-30 vs policy end 2027-05-21 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 6 days vs 15; justification=None |
| 5 | R7 | all required documents present | **yes** | missing=['licence_copy'] |

Verdict: ☐ agree ☐ label error — note:

## dev-0050

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R6_LATE_REPORT"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-09-28","other_party":"insured","fault_share":100,"damage_amount_sar":11000}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-09-28 vs policy end 2027-05-12 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | **yes** | 29 days vs 15; justification=None |

Verdict: ☐ agree ☐ label error — note:

## dev-0231

**Gold:** `{"decision":"approve","payout_sar":27350,"reasons":["R3_OWN_DAMAGE","SUBROGATION"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-03-04","other_party":"insured","fault_share":25,"damage_amount_sar":27600,"sum_insured_sar":91000,"base_sar":27600,"deductible_applied_sar":250,"total_loss":false}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-03-04 vs policy end 2026-05-28 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 0 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 27600 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | no | repair 27600 vs 60% x 91000 = 54600; technical=False |
| 11 | R3 | deductible applied | **yes** | 1000 x 25% (CMIR 5.4.3/5.4.4) = 250 |
| 12 | R3 | payout = base - deductible | **yes** | 27600 - 250 = 27350 |

Verdict: ☐ agree ☐ label error — note:
