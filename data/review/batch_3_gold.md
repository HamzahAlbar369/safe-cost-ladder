# Review batch 3 — gold and rule trace

> FICTIONAL insurer and synthetic tickets; dev split only (held-out is never shown). Items: the 50 from dev_review.md (selection seed `20261030:review`), batched with seed `20261030:review-batches`.

## dev-0230

**Gold:** `{"intent":"policy_change"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0346

**Gold:** `{"decision":"partial","payout_sar":7450,"reasons":["R4_THIRD_PARTY"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-04-11","other_party":"insured","fault_share":50,"damage_amount_sar":14900,"recovery_cases":[]}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-04-11 vs policy end 2026-12-17 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 2 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | no | none; licence=valid, renewed=None |
| 8 | R4 | policyholder 0% at fault | no | fault=50% |
| 9 | R4 | payout = damage x fault share, capped | no | 14900 x 50% = 7450; cap 10000000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0335

**Gold:** `{"policy_number":null,"accident_date":"2026-04-16","report_number":"NJ-59785095","damage_amount_sar":27900,"fault_share":null}`

Verdict: ☐ agree ☐ label error — note:

## dev-0330

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R1_TPL_NO_OWN_DAMAGE"],"inputs":{"claim_type":"own_damage","cover":"TPL","accident_date":"2026-02-18","other_party":"insured","fault_share":100,"damage_amount_sar":9800}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-02-18 vs policy end 2026-09-13 |
| 3 | R1 | own damage under TPL | **yes** |  |

Verdict: ☐ agree ☐ label error — note:

## dev-0071

**Gold:** `{"policy_number":"OMI-6212581","accident_date":null,"report_number":"TP-59359108","damage_amount_sar":41600,"fault_share":0}`

Verdict: ☐ agree ☐ label error — note:

## dev-0273

**Gold:** `{"decision":"partial","payout_sar":7450,"reasons":["R4_THIRD_PARTY"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-04-11","other_party":"insured","fault_share":50,"damage_amount_sar":14900,"recovery_cases":[]}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-04-11 vs policy end 2026-12-17 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 2 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | no | none; licence=valid, renewed=None |
| 8 | R4 | policyholder 0% at fault | no | fault=50% |
| 9 | R4 | payout = damage x fault share, capped | no | 14900 x 50% = 7450; cap 10000000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0224

**Gold:** `{"decision":"approve","payout_sar":45300,"reasons":["R4_THIRD_PARTY"],"inputs":{"claim_type":"third_party_claim","cover":"TPL","accident_date":"2026-03-09","other_party":"insured","fault_share":100,"damage_amount_sar":45300,"recovery_cases":[]}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-03-09 vs policy end 2026-09-26 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 4 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | no | none; licence=valid, renewed=None |
| 8 | R4 | policyholder 0% at fault | no | fault=100% |
| 9 | R4 | payout = damage x fault share, capped | no | 45300 x 100% = 45300; cap 10000000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0033

**Gold:** `{"answer":"no"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0296

**Gold:** `{"decision":"approve","payout_sar":23000,"reasons":["R3_OWN_DAMAGE"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-09-14","other_party":"insured","fault_share":100,"damage_amount_sar":24000,"sum_insured_sar":138000,"base_sar":24000,"deductible_applied_sar":1000,"total_loss":false}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-09-14 vs policy end 2026-12-22 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=['wrong_direction'], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 1 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 24000 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | no | repair 24000 vs 60% x 138000 = 82800; technical=False |
| 11 | R3 | deductible applied | **yes** | 1000 x 100% (CMIR 5.4.3/5.4.4) = 1000 |
| 12 | R3 | payout = base - deductible | **yes** | 24000 - 1000 = 23000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0324

**Gold:** `{"decision":"approve","payout_sar":27500,"reasons":["R4_THIRD_PARTY"],"inputs":{"claim_type":"third_party_claim","cover":"TPL","accident_date":"2026-05-04","other_party":"insured","fault_share":100,"damage_amount_sar":27500,"recovery_cases":[]}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-05-04 vs policy end 2027-01-16 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 2 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | no | none; licence=valid, renewed=None |
| 8 | R4 | policyholder 0% at fault | no | fault=100% |
| 9 | R4 | payout = damage x fault share, capped | no | 27500 x 100% = 27500; cap 10000000 |

Verdict: ☐ agree ☐ label error — note:
