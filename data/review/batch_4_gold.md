# Review batch 4 — gold and rule trace

> FICTIONAL insurer and synthetic tickets; dev split only (held-out is never shown). Items: the 50 from dev_review.md (selection seed `20261030:review`), batched with seed `20261030:review-batches`.

## dev-0294

**Gold:** `{"policy_number":"OMI-2984873","accident_date":null,"report_number":"TP-48281443","damage_amount_sar":null,"fault_share":null}`

Verdict: ☐ agree ☐ label error — note:

## dev-0154

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R5_TP_fled_scene"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-08-09","other_party":"insured","fault_share":25,"damage_amount_sar":15100}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-08-09 vs policy end 2026-12-09 |
| 3 | R5 | third-party exclusion (UP Art. 6) | **yes** | fled_scene |

Verdict: ☐ agree ☐ label error — note:

## dev-0226

**Gold:** `{"answer":5}`

Verdict: ☐ agree ☐ label error — note:

## dev-0140

**Gold:** `{"decision":"partial","payout_sar":53000,"reasons":["R3_OWN_DAMAGE","R3_TOTAL_LOSS","R3_SUM_INSURED_CAP"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-01-10","other_party":"none","fault_share":null,"damage_amount_sar":56900,"sum_insured_sar":54000,"base_sar":54000,"deductible_applied_sar":1000,"total_loss":true}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-01-10 vs policy end 2026-08-30 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 0 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | no | repair 56900 vs full deductible 1000 |
| 8 | R7 | all required documents present | no | missing=[] |
| 9 | R7 | two stated damage amounts contradict | no |  |
| 10 | R3 | total loss (technical, or repair > ETL% x sum insured) | **yes** | repair 56900 vs 60% x 54000 = 32400; technical=False |
| 11 | R3 | deductible applied | **yes** | no other party: full deductible (CMIR 5.4.5, interpretation) = 1000 |
| 12 | R3 | payout = base - deductible | **yes** | 54000 - 1000 = 53000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0238

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R5_OD_invalid_licence"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-07-19","other_party":"insured","fault_share":0,"damage_amount_sar":14700}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-07-19 vs policy end 2027-03-15 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | **yes** | status=none, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |

Verdict: ☐ agree ☐ label error — note:

## dev-0196

**Gold:** `{"decision":"need_info","payout_sar":0,"reasons":["R7_MISSING_accident_report","R7_MISSING_registration"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-04-28","other_party":"insured","fault_share":75,"damage_amount_sar":2200}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-04-28 vs policy end 2026-12-02 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 12 days vs 15; justification=None |
| 5 | R7 | all required documents present | **yes** | missing=['accident_report', 'registration'] |

Verdict: ☐ agree ☐ label error — note:

## dev-0347

**Gold:** `{"intent":"fault_dispute"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0149

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R1_TPL_NO_OWN_DAMAGE"],"inputs":{"claim_type":"own_damage","cover":"TPL","accident_date":"2026-05-06","other_party":"insured","fault_share":50,"damage_amount_sar":15500}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-05-06 vs policy end 2026-11-04 |
| 3 | R1 | own damage under TPL | **yes** |  |

Verdict: ☐ agree ☐ label error — note:

## dev-0010

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R3_BELOW_DEDUCTIBLE"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-02-03","other_party":"insured","fault_share":75,"damage_amount_sar":900}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-02-03 vs policy end 2026-10-23 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 8 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | **yes** | repair 900 vs full deductible 1000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0265

**Gold:** `{"intent":"claim_status"}`

Verdict: ☐ agree ☐ label error — note:
