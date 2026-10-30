# Review batch 4 — gold and rule trace

> FICTIONAL insurer and synthetic tickets; dev split only (held-out is never shown). Items: the 50 from dev_review.md (selection seed `20261030:review`), batched with seed `20261030:review-batches`.

## dev-0062

**Gold:** `{"policy_number":"OMI-1388857","accident_date":"2026-01-26","report_number":null,"damage_amount_sar":28800,"fault_share":null}`

Verdict: ☐ agree ☐ label error — note:

## dev-0131

**Gold:** `{"decision":"approve","payout_sar":14800,"reasons":["R3_OWN_DAMAGE","SUBROGATION"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-09-19","other_party":"insured","fault_share":50,"damage_amount_sar":15300,"sum_insured_sar":170000,"base_sar":15300,"deductible_applied_sar":500,"total_loss":false}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-09-19 vs policy end 2027-04-14 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=expired, renewed=2026-11-05 |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 0 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 15300 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | no | repair 15300 vs 60% x 170000 = 102000; technical=False |
| 11 | R3 | deductible applied | **yes** | 1000 x 50% (CMIR 5.4.3/5.4.4) = 500 |
| 12 | R3 | payout = base - deductible | **yes** | 15300 - 500 = 14800 |

Verdict: ☐ agree ☐ label error — note:

## dev-0387

**Gold:** `{"answer":60}`

Verdict: ☐ agree ☐ label error — note:

## dev-0089

**Gold:** `{"decision":"need_info","payout_sar":0,"reasons":["R7_CONFLICT"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-05-19","other_party":"insured","fault_share":50,"damage_amount_sar":2500}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-05-19 vs policy end 2026-08-20 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 2 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | **yes** | 2500 vs 5700 |

Verdict: ☐ agree ☐ label error — note:

## dev-0204

**Gold:** `{"decision":"partial","payout_sar":4275,"reasons":["R4_THIRD_PARTY"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-08-07","other_party":"insured","fault_share":25,"damage_amount_sar":17100,"recovery_cases":[]}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-08-07 vs policy end 2026-10-31 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 5 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | no | none; licence=valid, renewed=None |
| 8 | R4 | policyholder 0% at fault | no | fault=25% |
| 9 | R4 | payout = damage x fault share, capped | no | 17100 x 25% = 4275; cap 10000000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0032

**Gold:** `{"decision":"need_info","payout_sar":0,"reasons":["R7_CONFLICT"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-04-07","other_party":"insured","fault_share":25,"damage_amount_sar":48800}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-04-07 vs policy end 2026-10-29 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 12 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | **yes** | 48800 vs 45400 |

Verdict: ☐ agree ☐ label error — note:

## dev-0164

**Gold:** `{"policy_number":"OMI-3900659","accident_date":"2026-02-13","report_number":"NJ-72859890","damage_amount_sar":null,"fault_share":0}`

Verdict: ☐ agree ☐ label error — note:

## dev-0103

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R3_BELOW_DEDUCTIBLE"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-07-29","other_party":"insured","fault_share":0,"damage_amount_sar":900}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-07-29 vs policy end 2027-01-25 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 6 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | **yes** | repair 900 vs full deductible 1000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0342

**Gold:** `{"decision":"approve","payout_sar":10800,"reasons":["R4_THIRD_PARTY"],"inputs":{"claim_type":"third_party_claim","cover":"TPL","accident_date":"2026-09-13","other_party":"insured","fault_share":100,"damage_amount_sar":10800,"recovery_cases":[]}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-09-13 vs policy end 2026-11-05 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 5 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | no | none; licence=valid, renewed=None |
| 8 | R4 | policyholder 0% at fault | no | fault=100% |
| 9 | R4 | payout = damage x fault share, capped | no | 10800 x 100% = 10800; cap 10000000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0222

**Gold:** `{"intent":"other"}`

Verdict: ☐ agree ☐ label error — note:
