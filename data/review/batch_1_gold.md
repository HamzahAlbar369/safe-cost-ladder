# Review batch 1 — gold and rule trace

> FICTIONAL insurer and synthetic tickets; dev split only (held-out is never shown). Items: the 50 from dev_review.md (selection seed `20261030:review`), batched with seed `20261030:review-batches`.

## dev-0370

**Gold:** `{"intent":"coverage_question"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0161

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R1_TPL_NO_OWN_DAMAGE"],"inputs":{"claim_type":"own_damage","cover":"TPL","accident_date":"2026-09-18","other_party":"insured","fault_share":75,"damage_amount_sar":19500}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-09-18 vs policy end 2027-02-24 |
| 3 | R1 | own damage under TPL | **yes** |  |

Verdict: ☐ agree ☐ label error — note:

## dev-0241

**Gold:** `{"answer":5}`

Verdict: ☐ agree ☐ label error — note:

## dev-0290

**Gold:** `{"policy_number":"OMI-8534970","accident_date":"2026-08-05","report_number":"NJ-51216883","damage_amount_sar":10800,"fault_share":null}`

Verdict: ☐ agree ☐ label error — note:

## dev-0379

**Gold:** `{"intent":"complaint"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0098

**Gold:** `{"decision":"approve","payout_sar":17600,"reasons":["R3_OWN_DAMAGE","R8_UNKNOWN_PARTY"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-07-28","other_party":"unknown","fault_share":null,"damage_amount_sar":17600,"sum_insured_sar":190000,"base_sar":17600,"deductible_applied_sar":0,"total_loss":false}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-07-28 vs policy end 2027-02-10 |
| 3 | R5 | CMIR 7.2 licence valid (expired only: renewed on or before the business-day-50 date) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 6 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 17600 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | no | repair 17600 vs 60% x 190000 = 114000; technical=False |
| 11 | R3 | deductible applied | no | hit-and-run: no deductible (CMIR 5.4.4) = 0 |
| 12 | R3 | payout = base - deductible | **yes** | 17600 - 0 = 17600 |

Verdict: ☐ agree ☐ label error — note:

## dev-0345

**Gold:** `{"answer":"no"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0074

**Gold:** `{"decision":"partial","payout_sar":14100,"reasons":["R4_THIRD_PARTY"],"inputs":{"claim_type":"third_party_claim","cover":"TPL","accident_date":"2026-01-24","other_party":"insured","fault_share":50,"damage_amount_sar":28200,"recovery_cases":[]}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-01-24 vs policy end 2026-02-14 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 4 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | no | none; licence=valid, renewed=None |
| 8 | R4 | policyholder 0% at fault | no | fault=50% |
| 9 | R4 | payout = damage x fault share, capped | no | 28200 x 50% = 14100; cap 10000000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0106

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R4_NO_FAULT"],"inputs":{"claim_type":"third_party_claim","cover":"TPL","accident_date":"2026-03-04","other_party":"insured","fault_share":0,"damage_amount_sar":58600}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-03-04 vs policy end 2026-12-07 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 7 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | no | none; licence=valid, renewed=None |
| 8 | R4 | policyholder 0% at fault | **yes** | fault=0% |

Verdict: ☐ agree ☐ label error — note:

## dev-0033

**Gold:** `{"decision":"need_info","payout_sar":0,"reasons":["R7_MISSING_damage_assessment"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-08-10","other_party":"insured","fault_share":25,"damage_amount_sar":29900}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-08-10 vs policy end 2026-12-17 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 5 days vs 15; justification=None |
| 5 | R7 | all required documents present | **yes** | missing=['damage_assessment'] |

Verdict: ☐ agree ☐ label error — note:
