# Solvability check (Phase 2 gate) — dev matrix `matrix-dev-full-1`

Every failure of `opus-high` (the strongest config by design) is categorised as **generator bug**, **ambiguous** or
**genuinely hard**. Evidence for each id (ticket text, gold, rule trace, the model's full output, verifier verdicts) is
in `reports/phase2/failures_opus-high.json`; the same files exist for `opus-medium` and `opus-low`. Counts below are
read from `reports/phase2/cells_report.txt` and `reports/phase2/failures_*.json` (run id, git SHA and config hash are in
their headers). Categories are a human judgement made by reading those records.

## `opus-high` failures

| Ticket | Task / level | Category | Why |
|---|---|---|---|
| dev-0378 | adjudicate L4 (EN, `od_driver_unauthorised`) | **ambiguous — generator defect** | The agent summary says "caller Faisal" and the customer text says "The car was being driven by Faisal from work". Gold is *deny* (R5, driver not authorised); the model read Faisal as the policyholder driving and approved. Cause: `people()` in `datagen/templates/render.py` draws `name_i` (caller) and `other_i` (second person) independently from the same 20 names, so they coincide with probability 1/20 whenever a second named person appears. The rules and gold are right; the text is genuinely ambiguous. 8 of 9 configs got it wrong (only `opus-medium` right). |

`opus-high` has exactly one failure on 180 adjudicate tickets (0.994). No generator bug in the *rules or gold*; one
text-level defect in name sampling.

## Other opus misses (for context)

| Ticket | Config | Category | Why |
|---|---|---|---|
| dev-0378 | opus-low | ambiguous (same ticket as above) | — |
| dev-0084 | opus-medium | genuinely hard | L5 `excluded_and_missing`: the claim has both an unlicensed driver (CMIR 7.2 exclusion → deny) and no damage assessment (→ need_info). Policy section 12 puts exclusions before required documents, so *deny* is right; the model answered need_info. 5 of 9 configs missed it. Gold agrees with the policy text. |

## Wider pattern (all 9 configs)

- 23 of 400 dev tickets are wrong in at least one config; 3 in three or more (dev-0378, dev-0084, dev-0214).
  dev-0214 is the Arabic twin of dev-0084 (`excluded_and_missing`: exclusion beats missing document): genuinely hard.
- 34 of the wrong cells are adjudicate (L4 over-sum-insured, L5 exclusion-vs-missing-document, a violation that did not
  cause the accident); the rest are 5 intent (`policy_change` borderline wording), 1 faq, 1 extract.
- Reliability events that are not accuracy errors (all counted as failures per SPEC §3.1): three Sonnet runs hit
  `max_tokens` after about 6,000 thinking tokens on ordinary L3/L4 tickets (dev-0167, dev-0243 on `sonnet-medium`;
  dev-0400 on `sonnet-low`; every other config solved all three), and one `sonnet-high` call returned
  `stop_reason: refusal` on a benign Arabic third-party claim (dev-0067). Server-side fallbacks are deliberately off
  (D0.4), so these are recorded as failed answers.

## Decision needed (Hamzah)

The name collision affects roughly 1 in 20 tickets that name a second person, in every split including the sealed
held-out. Options: **(A)** leave the frozen data and document it as a known limitation (one dev ticket changed an
`opus-high` outcome; floors already include it); **(B)** make `other_i != name_i`, regenerate (gold unchanged; only
colliding texts change, dev ids stable by D1.11), re-seal held-out with a new hash, and re-record the changed dev
cells. Recommendation: **A** — the change is small relative to the time left, held-out was never inspected, and the
effect (about 1 ticket in 400 for the strongest config) is inside the tolerance already built into the floors.
