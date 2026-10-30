# Independent Data Audit — Phase 1

**Result: 50 / 50 blind agreement with the generated gold labels. 0 label errors.**

## Why this audit exists
All 1,000 test items are synthetic, with gold labels computed by the rules engine from
`data/rules/rules.yaml`. Before any model was evaluated, we checked that those labels are correct
and that the tickets are unambiguous, using a reviewer that had never seen the generator.

## Method
| Step | Detail |
|---|---|
| Reviewer | A separate Claude Sonnet 5.5 session with **only** the rules files (`rules.yaml`, policy documents EN/AR, `SOURCES.md`) — no access to the generator, the planning, or the gold labels |
| Sample | 50 dev items drawn at random (seed recorded): 30 English, 20 Arabic |
| Coverage | All adjudication levels (L3 15, L4 4, L5 9) and all four decisions (approve 8, partial 6, deny 7, need_info 7); 14 third-party claims; 1 garage-quote-only case |
| Pass 1 — blind | Reviewer answered every item from the ticket text and rules alone, showing the rule path and arithmetic |
| Pass 2 — compare | Gold labels revealed; reviewer compared, re-did arithmetic on any disagreement, and checked that each gold trace uses only facts stated in the ticket |
| Batches | 5 × 10 items |
| Held-out | Never touched; sealed by SHA-256 before and after |

## Results
| Batch | Agreement | Label errors |
|---|---|---|
| 1 | 10 / 10 | 0 |
| 2 | 10 / 10 | 0 |
| 3 | 10 / 10 | 0 |
| 4 | 10 / 10 | 0 |
| 5 | 10 / 10 | 0 |
| **Total** | **50 / 50** | **0** |

## Text-quality findings and fixes
The gold labels were correct in every case. The reviewer flagged wording that could unfairly trip a
model or read unnaturally; each was fixed in the generator with a permanent QA scan (DECISIONS.md D1.12).

| Finding | Example items | Risk | Fix | Status |
|---|---|---|---|---|
| Numeric dates readable day-first or month-first | dev-0313 | Answer flips (on time vs late) | Unambiguous date formats only | Fixed |
| "Revised assessment" read as a replacement, not a contradiction | dev-0092 | Defensible but ambiguous label | Reworded as a second, conflicting report | Fixed |
| Hit-and-run tickets describing the other driver's behaviour | dev-0098, -0313, -0331, -0030 | Contradicts the facts | Line suppressed when the other party is unknown | Fixed |
| Event date after the ticket's submission date | dev-0127 | Impossible timeline | Date-consistency scan | Fixed |
| Arabic: English words glued to Arabic words; signer gender ≠ closing | dev-0168, -0292, -0068 | Unnatural Arabic | Spacing and gender-agreement scans | Fixed |
| Absent extract fields / vague relative dates | dev-0331, -0177, -0323 | Prompt ambiguity, not data error | Phase 2 prompt states: any absent field is null; a vague relative date means accident_date is null (SPEC §6.2) | Phase 2 (pending) |

## Limitations
- The reviewer is a Claude model, the same family as some evaluated models. Mitigations: it worked in
  an isolated context with only the rules, answered blind before seeing gold labels, and the gold
  labels themselves come from deterministic code, not from any model.
- 50 items is a sample (5% of the data); the remaining items are covered by automated QA
  (schema, gold re-derivation, duplicates, leakage, fact consistency, language scans — see `MANIFEST.json`).

Full reviewer log: `data/review/raw/checker_log.pdf`.
