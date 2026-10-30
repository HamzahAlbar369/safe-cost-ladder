# Review batch 2 — gold and rule trace

> FICTIONAL insurer and synthetic tickets; dev split only (held-out is never shown). Items: the 50 from dev_review.md (selection seed `20261030:review`), batched with seed `20261030:review-batches`.

## dev-0249

**Gold:** `{"decision":"need_info","payout_sar":0,"reasons":["R7_MISSING_damage_assessment"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-06-18","other_party":"insured","fault_share":50,"damage_amount_sar":600}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-06-18 vs policy end 2026-09-15 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 9 days vs 15; justification=None |
| 7 | R7 | all required documents present | **yes** | missing=['damage_assessment'] |

Verdict: ☐ agree ☐ label error — note:

## dev-0250

**Gold:** `{"answer":15}`

Verdict: ☐ agree ☐ label error — note:

## dev-0099

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R3_BELOW_DEDUCTIBLE"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-03-14","other_party":"insured","fault_share":25,"damage_amount_sar":600}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-03-14 vs policy end 2026-06-07 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | no | 8 days vs 15; justification=None |
| 7 | R3 | CMIR 7.3 loss at or below the full deductible | **yes** | repair 600 vs full deductible 1000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0167

**Gold:** `{"intent":"document_submission"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0246

**Gold:** `{"intent":"coverage_question"}`

Verdict: ☐ agree ☐ label error — note:

## dev-0080

**Gold:** `{"decision":"partial","payout_sar":13525,"reasons":["R4_THIRD_PARTY"],"inputs":{"claim_type":"third_party_claim","cover":"TPL","accident_date":"2026-04-16","other_party":"insured","fault_share":25,"damage_amount_sar":54100,"recovery_cases":[]}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-04-16 vs policy end 2026-09-20 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 15 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | no |  |
| 7 | R5 | UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7)) | no | none; licence=valid, renewed=None |
| 8 | R4 | policyholder 0% at fault | no | fault=25% |
| 9 | R4 | payout = damage x fault share, capped | no | 54100 x 25% = 13525; cap 10000000 |

Verdict: ☐ agree ☐ label error — note:

## dev-0188

**Gold:** `{"decision":"deny","payout_sar":0,"reasons":["R6_LATE_REPORT"],"inputs":{"claim_type":"own_damage","cover":"COMP","accident_date":"2026-01-06","other_party":"insured","fault_share":100,"damage_amount_sar":25900}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-01-06 vs policy end 2026-10-04 |
| 3 | R5 | CMIR 7.2 licence valid (50 business-day grace for expired only) | no | status=valid, renewed=None |
| 4 | R5 | CMIR 7.4 driver authorised (CMIR 1.8) | no | driver=insured |
| 5 | R5 | CMIR 7.16 violation proven to cause the accident | no | violations=[], caused=False |
| 6 | R6 | reported late without an accepted reason | **yes** | 38 days vs 15; justification=None |

Verdict: ☐ agree ☐ label error — note:

## dev-0010

**Gold:** `{"answer":5}`

Verdict: ☐ agree ☐ label error — note:

## dev-0358

**Gold:** `{"policy_number":"OMI-0897271","accident_date":"2026-08-11","report_number":null,"damage_amount_sar":44600,"fault_share":100}`

Verdict: ☐ agree ☐ label error — note:

## dev-0013

**Gold:** `{"decision":"need_info","payout_sar":0,"reasons":["R7_CONFLICT"],"inputs":{"claim_type":"third_party_claim","cover":"COMP","accident_date":"2026-01-15","other_party":"insured","fault_share":75,"damage_amount_sar":59000}}`

| # | Rule | Check | Fired | Detail |
|---|---|---|---|---|
| 1 | R0 | peril in scope (collision) | no | peril=collision |
| 2 | R1 | accident after policy end date | no | accident 2026-01-15 vs policy end 2026-06-29 |
| 3 | R5 | third-party exclusion (UP Art. 6) | no | none |
| 4 | R6 | reported late without an accepted reason | no | 9 days vs 15; justification=None |
| 5 | R7 | all required documents present | no | missing=[] |
| 6 | R7 | two stated damage amounts contradict | **yes** | 59000 vs 57700 |

Verdict: ☐ agree ☐ label error — note:
