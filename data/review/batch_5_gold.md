# Review batch 5 — gold and rule trace

> FICTIONAL insurer and synthetic tickets; dev split only (held-out is never shown). Items: the 50 from dev_review.md (selection seed `20261030:review`), batched with seed `20261030:review-batches`.

## dev-0382

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R6_LATE_REPORT"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-03-03","other_party":"insured","fault_share":50,"damage_amount_sar":21700}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-03-03 vs policy end 2026-11-23 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | **yes** | 20 days vs 15; justification=None |

Verdict: ☐ agree ☐ label error — note:

## dev-0268

**Gold:** `{"decision":"need_info","payout_sar":0,"reasons":["R7_MISSING_damage_assessment"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-01-27","other_party":"insured","fault_share":100,"damage_amount_sar":21500}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-01-27 vs policy end 2026-09-11 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 5 days vs 15; justification=None |
| 5 | R7 | all required documents present | **yes** | missing=['damage_assessment'] |

Verdict: ☐ agree ☐ label error — note:

## dev-0349

**Gold:** `{"decision":"approve","payout_sar":24600,"reasons":["R4_THIRD_PARTY"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-02-22","other_party":"insured","fault_share":100,"damage_amount_sar":24600,"recovery_cases":[]}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-02-22 vs policy end 2026-03-19 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 3 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | no | none; licence=valid, renewed=None |
| 8 | R4 | policyholder 0% at fault | no | fault=100% |
| 9 | R4 | payout = damage x fault share, capped | no | 24600 x 100% = 24600; cap 10000000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0350

**Gold:** `{"decision":"approve","payout_sar":22550,"reasons":["R3_OWN_DAMAGE","SUBROGATION"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-03-29","other_party":"insured","fault_share":75,"damage_amount_sar":23300,"sum_insured_sar":57000,"base_sar":23300,"deductible_applied_sar":750,"total_loss":false}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-03-29 vs policy end 2026-07-24 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 1 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 23300 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | no | repair 23300 vs 60% x 57000 = 34200; technical=False |
| 11 | R3 | deductible applied | **yes** | 1000 x 75% (CMIR 5.4.3/5.4.4) = 750 |
| 12 | R3 | payout = base - deductible | **yes** | 23300 - 750 = 22550 |

Verdict: ☐ agree ☐ label error — note:

## dev-0120

**Gold:** `{"decision":"approve","payout_sar":15450,"reasons":["R3_OWN_DAMAGE","SUBROGATION"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-05-22","other_party":"insured","fault_share":75,"damage_amount_sar":16200,"sum_insured_sar":153000,"base_sar":16200,"deductible_applied_sar":750,"total_loss":false}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-05-22 vs policy end 2027-03-10 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 3 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 16200 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | no | repair 16200 vs 60% x 153000 = 91800; technical=False |
| 11 | R3 | deductible applied | **yes** | 1000 x 75% (CMIR 5.4.3/5.4.4) = 750 |
| 12 | R3 | payout = base - deductible | **yes** | 16200 - 750 = 15450 |

Verdict: ☐ agree ☐ label error — note:

## dev-0058

**Gold:** `{"intent":"policy_change"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0321

**Gold:** `{"answer":"no"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0326

**Gold:** `{"decision":"need_info","payout_sar":0,"reasons":["R7_CONFLICT"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-04-30","other_party":"insured","fault_share":100,"damage_amount_sar":32700}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-04-30 vs policy end 2026-09-02 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 13 days vs 15; justification=None |
| 7 | R7 | all required documents present | no | missing=[] |
| 8 | R7 | two stated damage amounts contradict | **yes** | 32700 vs 29500 |

Verdict: ☐ agree ☐ label error — note:

## dev-0359

**Gold:** `{"answer":7}`

Verdict: ☐ agree ☐ label error — note:

## dev-0239

**Gold:** `{"policy_number":"OMI-3591827","accident_date":null,"report_number":"NJ-54399104","damage_amount_sar":null,"fault_share":null}`

Verdict: ☐ agree ☐ label error — note:
