# Decision log

Format: date · decision · evidence · run id. Newest phase at the bottom. Numbers here are copied from the
named run file, never typed from memory.

## Phase 0 — Recon & smoke (2026-10-30)

### D0.1 · Prices re-verified on the official Anthropic page: no differences from SPEC §2.2
- **Decision:** `config/models.yaml` uses the SPEC §2.2 prices unchanged; `verified_on: 2026-10-30`,
  `source: https://platform.claude.com/docs/en/about-claude/pricing`.
- **Evidence:** official table rows for Claude Haiku 5.5 (≤100K-token prompts), Sonnet 5.5 and Opus 5.5 match all
  15 values (input, output, 5m cache write, cache read). Footnote 2 confirms cache reads at 0.05× base for
  Sonnet 5.5 and Opus 5.5. Haiku 5.5 prompts over 100,000 tokens use a higher tier ($0.50 / $2.50); the client
  refuses requests estimated above it. Unit test `tests/test_cost.py::test_prices_match_spec_2_2`.
- **Run id:** n/a (documentation check).

### D0.2 · Jev: Decisions API, `typesafe/jev-1.14`, schema confirmed from the official OpenAPI spec
- **Decision:** Jev is called with plain HTTP at `POST https://openrouter.ai/api/alpha/decisions`
  (request `{model, state, questions}`; question types `noul`, `choice`, `score`; answers carry probabilities and
  a confidence). Pinned model `typesafe/jev-1.14` (the current release; SPEC named Jev without a version).
- **Evidence:** OpenRouter OpenAPI spec for `createApiAlphaDecisions`
  (https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request.md) and the Jev hub
  (https://openrouter.ai/docs/guides/community/jev.md). Pricing: input tokens only, output free; $0.042/MTok
  reproduces the documented example exactly (476 tokens → $0.000019992). `usage.cost` is the cost of record.
- **Risk:** the endpoint is under `/api/alpha/` and may change or be withdrawn. **Mitigation:** model version pinned
  (`jev-1.14`, not `jev-latest`); every Jev call is recorded to `cassettes/openrouter/`, so all Jev results replay
  without the endpoint; Jev is one router variant among three and the local router does not depend on it.
- **Run id:** n/a (documentation check); live confirmation in D0.6.

### D0.3 · Cassette key extended with thinking mode and repeat index (approved by Hamzah)
- **Decision:** key = sha256 of (model, effort, sha256(system), user, max_tokens, schema, thinking, repeat).
  SPEC §6.5 updated.
- **Why:** check 6 sends the same prompt with and without `thinking: adaptive`, and check 4 sends identical
  requests twice on purpose; without these fields the cassettes would collide. Storing only the system prompt's
  hash keeps cassettes small; `engine check` re-derives every key from the stored request.
- **Evidence:** `tests/test_replay.py::test_hash_covers_every_output_relevant_field`.

### D0.4 · Server-side refusal fallbacks deliberately disabled
- **Decision:** requests do not set `fallbacks`. A refusal is recorded as a failed call (`stop_reason: refusal`).
- **Why:** a fallback silently serves a different model, which would corrupt per-config cost/accuracy.

### D0.5 · gitleaks gap found and closed
- **Decision:** `.gitleaks.toml` extends the default rules with explicit Anthropic and OpenRouter key rules;
  `engine check` runs a canary (freshly generated fake keys must both be detected), a full-history scan, and the
  staged-files pre-commit hook.
- **Evidence:** the pinned gitleaks v8.21.2 default ruleset did not flag a well-formed fake `sk-ant-api03-…` key
  (it did flag a fake GitHub token). With the custom config both fake keys are detected.

### D0.6 · Smoke results (SPEC §2.3 checks 1–7)
- **Run id:** `smoke-20261030T130454Z` · git `9c507f0` (`-dirty` = the uncommitted SPEC §6.5 text edit only;
  no code changed) · files `runs/smoke.json`, `runs/smoke-20261030T130454Z/{calls,jev}.jsonl`.
  Spend: Anthropic $0.161098, OpenRouter $0.00020261 (approved caps $4.00 / $0.01).
  Replay reproduces the run exactly with no key (`engine check`, replay integrity).
- **Model IDs:** `client.models.list()` returned all three IDs (none missing); each reports max output 128,000
  and effort low/medium/high supported.
- **Check 1 (parseable JSON):** 7/9 configs 5/5. `sonnet-medium` and `sonnet-high` each failed 1/5, both on
  `probe-4-adjudicate`: with `thinking` omitted the model wrote 0 thinking tokens and reasoned in the visible
  text, before or around the JSON. No truncations, refusals or API errors in any call.
- **Check 2 (effort effect):** effort raises output tokens and latency on every model (high/low mean output:
  Haiku 1.40×, Sonnet 1.70×, Opus 1.65×; latency 1.16×, 1.17×, 1.27×). The probe items are short, so absolute
  numbers are small; Phase 2 re-measures on real items.
- **Check 3 (tokens/latency):** see the per-config table in `runs/smoke.json` → `3_tokens_latency_per_config`.
  Max output tokens seen in any smoke call: 652 (`haiku-high`, adjudicate); max thinking tokens: 459 (same call).
- **Check 4 (minimum cacheable prefix):** identical on all three models: a 499-token prompt did not cache, a
  1,098-token prompt did. The full static prefix (2,725 cached tokens) caches on every model. Consistent with the
  documented 512-token minimum for Sonnet/Opus 5.5; for Haiku 5.5 we only know the minimum is between 500 and 1,098.
- **Check 5 (effort vs cache):** changing effort does NOT invalidate the cached system prefix on any model: the first
  `medium` and `high` calls each read 2,725 cached tokens written by `low`. **Decision:** one prefix cache per model
  (not per model × effort); SPEC §6.2's per-(model, effort) assumption is retired, and warm-up needs one request
  per model.
- **Check 6 (thinking vs effort):** effort applies without explicitly enabling thinking on all three models.
  With `thinking` omitted, Haiku 5.5 and Opus 5.5 still thought on some calls; Sonnet 5.5 produced 0 thinking
  tokens on all four of its thinking-omitted check-6 calls (in the matrix, `sonnet-high` thought on some items), and the explicit `thinking: {type: "adaptive"}` request for sonnet-high
  adjudicate thought (217 tokens) and parsed, where the omitted request did not.
- **Check 7 (Jev):** reachable; 10/10 calls OK; served `typesafe/jev-1.14-20261014`. Latency: first call 42,801 ms
  (cold start), then p50 313 ms (n=10 incl. first: mean 4,565, p95 42,801). Arabic: 5/5 Arabic calls OK;
  `complexity` agreed EN vs AR on 3/5 parallel pairs; largest noul probability gap 0.40; `complexity` confidences
  ranged 0.22–0.94, with 5 of 10 below 0.5. Mean input 482 tokens; total $0.00020261.
- **Tokenizer note:** prompt token counts were identical across the three models on these prefixes (499 / 1,098 /
  2,772). The CLAUDE.md rule against cross-model token comparison stays; costs are always computed per model.

### D0.7 · Recommendations from the smoke run (need Hamzah's OK before Phase 2 prompts freeze)
1. **Keep all 9 configs.** The two check-1 failures came from the request setup (thinking omitted), not the model;
   check 6 shows the fix working on the same item. Do not drop `sonnet-medium`/`sonnet-high`.
2. **Send `thinking: {type: "adaptive"}` explicitly on every task call**, so all three models behave the same way.
3. **Consider structured outputs (`output_config.format` with a JSON schema)** for the four task outputs, so a
   parse failure cannot come from prose around the JSON. This changes the request shape, so it must be decided
   before the dev matrix is recorded.
4. **Per-task `max_tokens`:** smoke outputs were short (max 652 incl. thinking). Phase 1/2 will set caps from
   dev-item measurements with headroom; until then keep generous caps (truncation = failure).
5. **Jev:** warm it with one call before timing anything (the 42.8 s cold start would otherwise dominate p95);
   Arabic agreement (3/5) is a risk flag for the Jev router on Arabic tickets.

### D0.8 · D0.7 approved by Hamzah (2026-10-30)
- **Keep all 9 configs.**
- **`thinking: {type: "adaptive"}` is sent explicitly on every task call.**
- **Structured outputs (`output_config.format`) on all task calls.** Not yet verified on these models.
  **Phase 2 entry check:** before the dev matrix is recorded, a small paid probe (estimate shown first) must confirm
  that all three models accept `output_config.format` together with `output_config.effort` and adaptive thinking,
  and return schema-valid JSON for all four task schemas.
- **Jev is warmed with one untimed call before any latency measurement.**

### D0.9 · Low effort is the cheapest config per model once caching is removed (Hamzah's hypothesis: confirmed)
- **Evidence:** run `smoke-20261030T130454Z`, `uv run engine smoke --summary`, column `nocache_usd` (every prompt
  token at the base input rate, SPEC §7.5). Low effort has the lowest no-cache cost on all three models. Medium /
  high cost more than low by: Haiku +3.1% / +9.6%, Sonnet +8.0% / +8.7%, Opus +6.8% / +8.7%.
- **Why the actual-cost column said otherwise:** `low` ran first on each model and paid the one cache write for the
  shared prefix (D0.6 check 5); `medium` and `high` then read that cache, so their actual cost looked lower.
- **Caveat:** 5 short probe items per config; the gaps are small. Phase 2 re-measures on the dev matrix.

### D0.10 · Paid commands refuse a dirty working tree (except `engine smoke`)
- **Decision:** `LLMClient` and `JevClient` check `git status --porcelain` (tracked changes and untracked,
  non-ignored files) before their first live call and raise `DirtyTree` if anything is uncommitted. Only `engine
  smoke` opts out (`allow_dirty=True`). Replay mode never checks. Enforced in the clients, not per command, so a new
  paid command cannot forget it.
- **Why:** every paid run's git SHA must identify the exact code and prompts (the smoke run was recorded as
  `9c507f0-dirty`).
- **Evidence:** `tests/test_runinfo.py` (refusal before any API call or ledger entry; smoke opt-out; replay unaffected;
  Jev too).

### Phase 0 closed (2026-10-30, Hamzah's sign-off)
Gate (SPEC §10): repo + `.gitignore` + `.env.example` + pre-commit/gitleaks committed · prices re-verified (D0.1) ·
smoke checks 1–7 logged (D0.6) · Jev reachable + Arabic result logged (D0.6) · mentor slot: Hamzah.

## Phase 1 — Data (2026-10-30)

Decisions D1.1–D1.6 were made by Hamzah at the start of Phase 1, informed by a review of the SAMA Unified
Compulsory Motor Insurance Policy (https://rulebook.sama.gov.sa/en/node/7886) and commercial Najm/claims guides.
The insurer and every rule stay fictional and are worded by us; nothing is presented as a real Najm, SAMA or
insurer rule.

### D1.1 · Splits are 400 / 400 / 200 (was 240 / 240 / 120)
- **Decision:** dev 400 · held-out 400 (sealed) · shifted 200. ~30% Arabic in every split, stratified by
  task × level × language. Updates locked decision 5 (CLAUDE.md) and SPEC §4.3.
- **Why:** tighter bootstrap CIs on per-task and per-language comparisons.
- **Consequence:** the Phase 2 dev + shifted matrix is 600 tickets × 9 configs (was 360 × 9), about 1.67× the
  calls; `engine final` records 400 × 9. `engine matrix` prints its estimate before any spend, and any run over $5
  needs Hamzah's OK (CLAUDE.md).

### D1.2 · Templates only, no LLM paraphrase; Phase 1 makes no paid calls
- **Decision:** text comes only from template families plus a deterministic variation layer. At least 6
  families per task per language are used by dev/held-out; further families are held back for the shifted
  split only. The variation layer (seeded) adds typos, filler, sentence reordering and Arabic/English
  code-switching, and never edits a gold-relevant value. SPEC §4.2 step 4 (paraphrase with `haiku-low`) is removed.
- **Why:** no generator/answerer model overlap, no Phase 1 spend, fully reproducible text.
- **Check kept:** the §4.4 fact-preservation check (100%) now runs on the variation layer's output.

### D1.3 · Shifted split adds ~20 adversarial / out-of-scope items
- **Decision:** prompt injection asking for approval, non-insurance questions, garbled or near-empty
  messages, very long rambling tickets. The correct behaviour for each kind is defined in `rules.yaml`
  (`adversarial:` section), and gold comes from the rules engine like every other item.

### D1.4 · Cost labels everywhere
- **Decision:** every report, CLI table, chart and slide uses exactly two labels:
  **"Cost with caching (actual)"** (`cost_usd`, what was billed) and **"Cost without caching (headline)"**
  (`cost_usd_nocache`, all prompt tokens at the base input rate; SPEC §7.5). Field names in data files stay as they are.

### D1.5 · Rules realism changes (structure informed by the SAMA unified policy; wording our own)
- **R3** own damage: deductible = max(SAR 1,000, 5% of damage); own-damage cap = the vehicle's market value;
  repair cost above market value = total loss.
- **R4** third-party payout proportional to fault, with a lower fictional TPL cap so the cap triggers.
- **R5** rework. Third-party claims with a violation (unlicensed driver, expired licence not renewed within 50 days
  of the accident, wrong direction, red light, use outside the schedule) → pay per R4 plus a `recovery_right`
  reason code. Outright denials (any claim type): intoxication, fled the scene, drifting/racing, fraud.
  Own-damage claims: deny for unlicensed driver and commercial use (a fictional policy choice). Policy expired on
  the accident date → deny.
- **R8 (new)** unknown or uninsured other party: COMP pays own damage less the deductible; TPL denies. The report
  may come from Najm or the traffic police.
- **R6** reporting window 15 days. **R7** unchanged.
- Explicit decision definitions: approve = full payout; partial = reduced by fault, cap or deductible;
  deny = payout 0. Every claim carries `claim_type` (`own_damage` | `third_party`).
- FAQ-only parameters: replacement-car days, towing, the 3 / 5 / 15 working-day timelines, the 24-hour Najm report.
- Declared out of scope in the policy: injury/death, theft, fire, flood (intent `other`).
- Intent labels: 9 (adds `fault_dispute`), with overlap definitions: `payment_issue` = claim payout only;
  premium/renewal → `policy_change`; `new_claim` = no claim exists yet; `document_submission` = a claim exists.
- Every threshold is a YAML parameter. SPEC §3.1, §4.1, §4.3 updated.

### D1.6 · DEFERRED to Phase 3 (if time allows): AI rewrite of the shifted split
- **Decision:** a rewrite pass over the shifted split only, using a non-Anthropic model via OpenRouter (so Claude
  never rewrites the tests Claude then answers), with a fact-preservation check that rejects any rewrite that
  changes a gold-relevant value. Listed in SPEC §13 open items.
- **Design hook built now:** every ticket stores its gold-relevant surface values (`meta.facts`), and gold is
  computed from sampled case facts, never from text, so a later rewrite can be checked and bolted on without
  changing any gold label.

### D1.7 · Stage A interpretation choices (PENDING Hamzah's wording review)
Choices made while writing `data/rules/rules.yaml` where D1.5 left a detail open. Each is a YAML value or a
precedence step, so changing one is a one-line edit plus `engine policy`.
1. **Own damage can never be `approve`.** The deductible is always ≥ SAR 1,000, so an own-damage payout is always
   below the claimed damage → `partial` (or `deny` at/below the deductible). `approve` happens only on third-party
   claims at 100% fault under the cap. Alternative: waive the deductible when the other party is identified,
   insured and 100% at fault (adds an approve path and one more interaction).
2. **Deny beats need_info.** Precedence: R0 → R5 expiry → R5 absolute → R8/R1 cover → R5 own-damage → R6 → R7 →
   payout. A claim that is excluded AND missing a document is `deny`.
3. **Licence grace period** reads as: an expired licence counts as valid if renewed within 50 days *after* the
   accident (`licence_renewal_grace_days`).
4. **R8** treats "identified but uninsured" the same as "unknown". Under TPL the reason code is `R8_no_own_cover`
   (checked before R1); under COMP it adds `R8_unknown_party` to the R3 payout.
5. **Boundaries are inclusive:** a report on day 15 is on time; a policy is valid through its end date.
6. **Out-of-scope perils (R0) in an adjudication ticket → `deny`**, payout 0 (intent tickets about them → `other`).
7. **Fictional values:** TPL cap SAR 50,000; replacement car 10 days (COMP only); towing SAR 500; fault objection
   5 days (from a soft source, so labelled fictional like everything else). v2: deductible floor 1,500, window 10
   days, TPL cap 35,000.
8. **Fictional ID formats:** policy `OMI-<7 digits>`, report `NJ-<8 digits>` (Najm) / `TP-<8 digits>` (police).
9. `rules_v2.yaml` is an override file (base + 3 changed values) so v1/v2 cannot drift; a test asserts that only
   those three values differ.

### D1.8 · Stage A approved with grounding changes (Hamzah, 2026-10-30) — supersedes D1.5/D1.7 where they differ
- **Sources (verified by Hamzah 2026-10-30):** Unified Compulsory Motor Insurance Policy (UP, in force 2023-04-01);
  Comprehensive Motor Insurance Rules (CMIR, SAMA Decision 3/S/445, 21/04/1445H); Instructions for Motor Insurance
  Claims' Settlement (CSI, SAMA circular, 14 May 2023). Regulator wording: "SAMA-issued, administered by the
  Insurance Authority". The insurer stays fictional.
- **Every rule, parameter, enumeration item and document clause carries `source:`** in one of these forms:
  `<instrument> Art. N` · `interpretation of <instrument> Art. N` · `<instrument> (article TBC)` ·
  `insurer-specific (illustrative)` · `reported, unverified`. The loader rejects any other form. The rule → source
  table is generated from the YAML: `data/rules/SOURCES.md` (`engine policy`).
- **Third party (UP):** Art. 6 exclusions → deny (fled scene, DUI, drifting/racing, deliberate, misrepresentation).
  Art. 5 recovery cases → paid + `RECOVERY_RIGHT`. Own vehicle under TPL → deny (Art. 6.1). Cap SAR 10,000,000.
  Licence grace 50 calendar days. Payout = damage × fault share (tagged as interpretation).
- **Own damage (CMIR), replaces draft R3:**
  - Base = sum insured on a technical total loss or when repair > ETL% × sum insured; otherwise min(repair, sum insured).
  - No deduction for prior use (5.3.4).
  - Deductible applied = fixed deductible × fault % (5.4.3); 0 if not liable (5.4.4); full if there is no other
    party (5.4.5). The fixed deductible is set per policy (5.4.7) and also applies to a total loss (interpretation of 5.4.2).
  - Deny if the repair estimate ≤ the full fixed deductible (7.3, literal reading).
  - The "doubles at fault ≥ 75%" rule is removed.
  - All CMIR Art. 7 exclusions are listed; the sampler generates only 7.2, 7.3, 7.4 and 7.16 (`generated: true`).
- **R8:** other party ∈ {insured, unknown, uninsured, none}. COMP + unknown → deductible 0, no subrogation.
  TPL + unknown/uninsured → deny own damage. The report may come from Najm or the traffic police (tagged
  "reported, unverified").
- **R7 documents (CSI):** accident report, registration, licence copy, damage photos, damage assessment report;
  any missing → need_info. **R6:** 15 days, insurer-specific, with the justification clause.
- **Decisions (supersede D1.7 #1; own damage can now be `approve`):** approve = payable, reduced only by the
  deductible; partial = reduced by fault share or a cap; deny = payout 0; need_info. `claim_type` ∈
  {`own_damage`, `third_party_claim`}.
- **FAQ gold** follows Hamzah's list (`faq_only`). Dropped: the 5-day fault-objection draft, the 24-hour Najm report,
  the old 3/5/15 timelines and replacement-car days. A replacement car is now an optional add-on, not part of the
  base policy.
- **rules_v2** changes only insurer-specific values: fixed deductible 1,000 → 1,500, ETL 60% → 50%, window 15 → 10
  days. A test asserts that every changed value is tagged insurer-specific.
- **MANIFEST** will report the decision-label distribution per split and flag any label under 10% of adjudication items.
- **Source verification (Hamzah, 2026-10-30, against the primary texts: the IA PDF and the SAMA rulebook):**
  - UP: insurer pays third parties = Art. 3 (proportional-to-fault stays "interpretation of UP Art. 3"); TPL cap =
    Art. 4 + Appendix A, per event; recovery cases = Art. 5; exclusions = Art. 6 (own vehicle 6.1); third parties
    not denied for violations, subject to Art. 6, recovery kept = Art. 9(7).
  - CMIR: 1.8 verified (Driver includes relatives and domestic or sponsored workers); 7.2 confirmed (grace only
    for an expired licence renewed within 50 business days; wrong class or forfeited → no grace); 5.4.5 confirmed
    as "may" (kept as an interpretation). Towing = "CMIR Policy Schedule, per-claim coverage limit (insurer may
    agree higher)".
  - CSI is cited as a whole: "SAMA Instructions for Motor Insurance Claims' Settlement, circular 14 May 2023"
    (no article numbers). Claims below SAR 2,000 → 5 working days; others → 15 calendar days.
  - Our own fetcher could not load the primary texts (IA PDF 404, UP page showed only the blank schedule); a CMIR
    machine summary at rulebook.sama.gov.sa/en/entiresection/8038 agreed with the above.
  - Still open: COMP cover type "CMIR (article TBC)"; fault-share steps and report sources "reported, unverified".
- **Rule order change (Hamzah):** CMIR 7.3 (repair estimate ≤ full deductible → deny) is evaluated before R7 when
  the damage assessment is present and unambiguous, so deny beats need_info (D1.7 #2). If the assessment itself is
  missing → need_info.
- **R0 note:** a real comprehensive policy usually covers theft and fire. Here R0 is an insurer-specific desk scope
  (collision only). The sampler will use R0 for intent tickets (`other`) and will not generate R0 adjudication
  denials, so the data never claims that a comprehensive policy denies theft.

### D1.9 · Template-leak check measured within each split (measurement fix, not a threshold change)
- **Decision:** the SPEC §4.4 leak check (label predictable from `template_family` ≤ majority-class rate + 5 pts)
  is computed by leave-one-out *within each split* and pooled over splits. Threshold unchanged.
- **Why:** the first version pooled all splits. Held-back families appear only in the shifted split, and the shifted
  split legitimately carries rules-v2 FAQ answers (1,500 / 375 / 50 / 10) that occur nowhere else, so the family
  "predicted" those answers through the split, not through the template (FAQ gap 5.2 pts). Within a split, families
  are drawn independently of the label, which is what the check is meant to test.
- **Evidence:** within-split gaps on the generated data: adjudicate −0.7, intent −7.3, FAQ +1.6 pts (MANIFEST
  `qa.template_leak`). Unit test `tests/test_datagen.py::test_qa_template_leak_flags_a_family_that_predicts_the_label`
  shows the check still catches a family that predicts the label.

### D1.10 · Spec gaps from the independent checker, fixed before Hamzah's review (2026-10-30)
- **Policy documents cite every rule inline.** Each clause renders its `source:` in brackets (EN verbatim; AR with
  translated instrument names), plus a legend at the top, so the "articles cited" disclaimer is literally true.
  Test: `test_every_clause_carries_its_inline_citation` (43 of 43 clauses per document).
- **7.3 text aligned with rules.yaml:** the deny applies when the damage assessment is present and not contradicted;
  contradictory assessment values → need_info (R7 contradiction). The precedence row and section 12 say the same.
- **Explicit labels** (rules.yaml `decisions` + policy section 1), and the engine checked against each:
  deductible scaled by fault only → approve; repair above the sum insured (cap binds) → partial; ETL / technical
  total loss paying the sum insured (repair not above it) → approve; third-party claim at fault < 100% → partial.
  Test: `test_d110_explicit_labels`.
- **Licence grace:** the accident day is day 0; a renewal on or before day 50 (calendar, TPL) or business day 50
  (COMP) is within grace. Business days follow the Saudi week: Sunday–Thursday working, Friday–Saturday weekend;
  public holidays ignored (stated in the policy). **Engine check:** it already read Sunday–Thursday from
  `rules.yaml` (no Mon–Fri default existed). New tests cover both conventions, including a case where they give
  different labels (`test_engine_uses_the_saudi_week_from_rules_yaml_not_mon_fri`).
- **Boundaries stated in the policy:** ETL = repair strictly above ETL% × sum insured (exactly equal is not a total
  loss); day 0 = accident day, reported on day 15 = on time, day 16 = late; repair ≤ full deductible → deny
  (equal counts). Test: `test_policy_states_the_boundaries_explicitly`.
- **Templates:**
  - (a) Every damage amount is attributed to the assessment report, or explicitly to a garage/workshop quote. A
    garage quote is not an assessment. New L5 design `garage_quote_only` → need_info (R7 missing assessment), and
    every design that drops the assessment now states a garage quote (`damage_source` on `Case`). "Contradiction"
    now means two assessment reports disagree, not garage quote vs assessment. Form labels say "assessed".
  - (b) Every licence-grace FAQ names its cover type (TPL / third-party / ضد الغير; comprehensive / الشامل). It
    already did; now enforced by `test_every_licence_grace_faq_names_the_cover_type`.
  - (c) No ticket has the customer saying they will claim from the other party's insurer: none did; now enforced
    by a QA scan of every ticket in every split (`structure.tickets_claiming_from_other_insurer` = 0) and a
    template test.
- **Required documents are "for the vehicle being claimed for"** (policy section 11, EN + AR).
- **Found while re-checking, also fixed:**
  - The typo layer could alter a month name in a long-form date (e.g. "Febraury"), breaking normalisation.
    Generation had silently retried those items; month names are now protected.
  - Arabic code-switching replaced substrings inside words ("بالوثيقة" → mangled, "تقريرا" → "reportا"). It now
    swaps whole words only, and typos skip mixed-script tokens. A new QA scan (`structure.tickets_with_mangled_tokens`)
    must be 0.
  - The new garage-quote design pushed partial labels to the 10% floor (shifted 10.0%), so the weights of the two
    partial-producing designs were raised (`tp_partial_fault` 3.0 → 3.5, `od_over_sum_insured` 1.5 → 1.8). This
    balances labels only; no model results exist yet.
- **Gold labels changed:** re-adjudicating every committed case (dev 180, held-out 180, shifted 90 adjudication
  items) with the updated engine changed **0** labels: the fixes were rule text, ticket wording and new designs,
  not engine logic. Wording defects in the previous data: 19 tickets stated an amount without an assessment report
  (dev 6, held-out 7, shifted 6), and up to 24 conflict tickets could read as garage quote vs assessment (upper
  bound). All splits were regenerated, so every item is a new draw from the same seed (held-out re-sealed with a
  new hash; it had never been used for evaluation).
- **QA re-run:** all §4.4 checks (schema, gold re-derived from rules, exact and near-duplicates, composition, fact
  preservation, template leak, structure incl. the two new scans, decision-label distribution) plus
  `engine check` (ruff, pytest, replay integrity, gitleaks). Review file and the 5 blind/gold batches re-exported
  from the new dev split.

### D1.11 · Final checker findings: wording and QA (2026-10-30)
- **Policy §11 per claim type:** own damage = the policyholder's vehicle registration, damage assessment and photos,
  the licence copy of the driver at the time, and the accident report. Third party = the claimant's vehicle
  registration and damage assessment, the at-fault driver's licence copy, the accident report, and photos of the
  claimant's vehicle damage. Templates follow it: third-party tickets name the claimant's documents and the at-fault
  driver's licence (`DOC_TP` in both phrase banks). The five required-document keys and the engine are unchanged.
- **Permanent QA check `fact_consistency`** (all splits): no ticket states two different fault shares or two policy
  numbers. On claim tickets, every SAR amount and every date in the text must be one of the case's own values (a
  second amount is allowed only in the assessment-contradiction case), and adjudication tickets must state the
  accident date. The licence-expiry date shown in tickets moved onto `Case.licence_expiry_date` (informational; the
  engine ignores it) so it can be checked. Result: 1000/1000 consistent. On the previously committed data, the scan
  flagged 23 tickets, all of them expired-licence cases whose expiry date was not stored on the case. None was a
  real conflict.
- **COMP licence grace = a calendar-date deadline:** count 50 business days (Saudi week) from the accident (day 0)
  to get the deadline date; a renewal on any calendar date on or before it, weekend days included, is within grace,
  and a later one is not. Engine: `business_day_deadline`. The old rule counted business days up to the renewal date,
  which wrongly accepted a Friday or Saturday renewal right after business day 50.
  Tests: `test_d111_comp_grace_is_a_calendar_date_deadline`, and the Saudi-vs-Mon–Fri test rewritten around a
  Friday accident (deadline Thursday vs Friday).
- **Arabic:** "50 يومًا تقويميًا" (new `ar_calday` counted noun); Arabic comma ، between cited articles.
- **No "(article TBC)":** the COMP cover-type source is now "CMIR, SAMA Decision 3/S/445"; the TBC form is no longer
  accepted by the loader. Disclaimer: "sources cited for each clause" (EN and AR).
- **Permanent QA check `policy_documents_no_placeholders`:** 0 unresolved `{…}` in policy v1/v2 EN/AR and SOURCES.md.
- **Generator RNG made local (found while answering "which review items changed"):** one RNG stream used to drive
  every item in sequence, so a single changed duplicate-check outcome re-drew every later item and re-shuffled all
  ids (the third-party wording change alone altered 200 of 400 dev texts). Each slot now has its own seeded stream
  (`{seed}:{split}:slot{i}`), and ids come from a separate seeded shuffle (`{seed}:{split}:order`).
  Test `test_wording_change_stays_local_to_the_items_that_use_it`: swapping the third-party document wording now
  changes only third-party claim texts (dev 77, held-out 72, shifted 35), with every gold label and id unchanged.
- **Gold labels changed:** re-adjudicating every previously committed case (450 adjudication items) with the
  updated engine (deadline rule included) changed **0** labels. Switching to per-slot RNG streams redrew all
  splits once (held-out re-sealed with a new hash; never used for evaluation). As a result, all 50 review items
  were replaced by new draws (none of the previous 50 texts remains in dev), and the review file and 5 batches were
  re-exported. The new review set covers L3/L4/L5 and all four decisions, including 14 third-party claims and 1
  garage-quote-only item.

### Phase 1 gate walk (2026-10-30) — sign-off recorded below (Phase 1 closed)
SPEC §10 row "1 Data", item by item:
- **rules.yaml reviewed by Hamzah:** Stage A approved with grounding changes (D1.8) and source corrections (D1.8
  update). Evidence: `data/rules/rules.yaml`, generated `data/rules/SOURCES.md`.
- **Rules-engine tests pass:** `tests/test_rules_engine.py` (74 tests: every rule R0–R8, the UP/CMIR licence grace
  contrast, 7.3-before-R7, deny-beats-need_info, cap, total loss, fault-scaled deductible, v2 values). Full suite
  191 passed; `engine check` green.
- **All §4.4 checks pass:** `data/generated/MANIFEST.json` → `qa` (schema 1000/1000; gold re-derived from rules,
  0 mismatches; 0 exact and 0 near-duplicates across splits; composition max deviation 0.0 pts; fact preservation
  100%; template leak within budget, D1.9; structure: 40 dev EN/AR pairs, 20 adversarial, 40 rules_v2 items,
  held-back families only in shifted). Decision-label distribution: no label under 10% in any split
  (`decision_distribution`). Generator self-check: every sampler design's expected decision equals the engine's
  (`tests/test_datagen.py`).
- **MANIFEST committed:** `data/generated/MANIFEST.json`, generator git SHA recorded from a clean tree, seed
  20261030, sha256 per file. A fresh clone reproduces every file hash (`.gitattributes` pins bytes);
  `tests/test_data_integrity.py` regenerates all splits and checks byte-for-byte equality.
- **Held-out sealed (hash recorded):** `MANIFEST.json` → `heldout_sealed.sha256`. Held-out was written by
  `engine gen` and only hashed or scanned by automated QA; no item was printed or reviewed.
- **Still open (human):** the §4.4 manual review of `data/review/dev_review.md` (30 EN + 20 AR dev items; any label
  error → fix the generator and regenerate). Solvability (opus-high failures) is a Phase 2 item.
- **No paid calls in Phase 1** (D1.2); ledger unchanged.
- **Waived Target items:** none. Note: CLAUDE.md refers to SPEC §11.9 for human checks, but SPEC has no §11.9;
  the human checks used here are the §10 gate row and the §4.4 manual-review row.

### D1.12 · Checker text defects fixed, each with a permanent QA scan (2026-10-30)
Checker result before these fixes: 50/50 blind agreement with gold, 0 label errors. The QA check
`text_defects` holds one counter per item; on the previous data it found every class, so the scans are live
(dev / held-out / shifted):
- **Ambiguous numeric dates** (day and month both ≤ 12): 94 / 112 / 61 tickets. Numeric formats are now used only
  when the day is above 12; otherwise the month is a word ("5 Mar 2026", "5 مارس 2026").
- **"Revised" assessment wording**: 4 / 2 / 0. Now "another assessment report gives a different figure"
  (EN; MSA "تقرير تقييم آخر يعطي رقمًا مختلفًا").
- **Other-driver lines on hit-and-run or single-vehicle tickets** (other party unknown/none): 9 / 1 / 0. Suppressed.
- **Dates after the ticket's own date**: 10 / 9 / 4 (licence renewed after the claim was reported). Such tickets
  are now a later update with an explicit date (`Case.submitted_on`, text only, on or after the renewal), and no
  date other than the policy end may be later than it.
- **Arabic/English without a space**: 6 / 2 / 7. Code-switching now inserts whole English words ("claim", not
  "الclaim"); the scan flags any Arabic letter touching a Latin letter.
- **Signer gender**: 14 / 4 / 0 female signers under "شاكرًا لكم". The closing now follows the name (شاكرًا /
  شاكرةً), and first-person Arabic phrases that were masculine-only were made gender-neutral (e.g. "بسبب تنويمي",
  "سافرت", "وثيقتي لديكم رقمها", "مكالمة من {name}").
- **EN/AR parallel pairs spanning splits**: 0 before and after (pairs exist only in dev by construction); now
  scanned permanently.
- **Optional polish done**: "wallah", "yalla" and "you know" removed from English prose (21 / 18 / 54 tickets
  previously); "inshallah" and "ya akhi" remain as English code-switching.
- **Labels:** 0 gold labels changed, and no task type changed, in any split (compared by id, which per-slot RNG now
  keeps stable). Texts changed: dev 186/400, held-out 185/400, shifted 123/200 (mostly date formats). The 50
  review items are the same ids in the same order; 29 changed text only (dev-0345, dev-0241, dev-0290, dev-0019,
  dev-0355, dev-0127, dev-0098, dev-0262, dev-0100, dev-0263, dev-0092, dev-0050, dev-0087, dev-0399, dev-0361,
  dev-0313, dev-0379, dev-0177, dev-0331, dev-0227, dev-0292, dev-0077, dev-0168, dev-0120, dev-0068, dev-0243,
  dev-0030, dev-0106, dev-0033), 0 changed label. Review file and batches re-exported. Held-out re-sealed (new hash;
  never used for evaluation).
- **Recorded for Phase 2 (SPEC §6.2):** the extract prompt must state that any absent field is null, and that a vague
  relative date ("a few days ago", "قبل أيام") means `accident_date` is null.

### Phase 1 closed (2026-10-30, Hamzah's sign-off)
- **Human review passed:** independent blind review of the 50 dev items (5 batches): 50/50 agreement with gold,
  0 label errors. The checker log is expected under `data/review/` (to be added by Hamzah; not generated here).
- **Gate (SPEC §10 row 1):** rules.yaml reviewed and sourced (D1.5, D1.8, D1.10, D1.11); rules-engine tests pass; all
  §4.4 checks pass plus the D1.10–D1.12 scans (MANIFEST `qa`); MANIFEST committed with a clean generator SHA;
  held-out sealed with its hash recorded. No paid calls in Phase 1.

## Phase 2 — Harness, matrix, floors (2026-10-30)

### D2.1 · Task prompts, output schemas and graders (Hamzah approved the prompts with one change)
- **Prompts** (`src/engine/tasks/prompts.py`): one static system block for all tasks (role + reading rules + faq /
  intent / extract / adjudicate instructions + the full English v1 policy document), the same bytes for every
  model and effort. User turn = `Task: <task>` + ticket text only. Arabic tickets are answered against the English
  policy. Extract: absent field = null; a vague relative date means `accident_date` null (D1.12). Intent: the nine
  rules.yaml definitions, overlaps included. Adjudicate lists the reason codes from rules.yaml.
- **Schemas** (`tasks/schemas.py`) for `output_config.format`, adaptive thinking sent explicitly (D0.8). Adjudicate
  emits `inputs` and `reasons` before `decision` and `payout_sar` (facts first). **FAQ change (Hamzah):** `answer`
  is an integer or an enum of the canonical strings; the enum is derived from the generator's FAQ answers plus
  `out_of_scope`, giving `no`, `out_of_scope`, `yes`, and the faq instructions list them. No list-type FAQ gold value
  exists in any split, so none is in the enum.
- **`max_tokens`:** faq 2048, intent 2048, extract 3072, adjudicate 6144 (largest smoke output incl. thinking was 652).
- **Graders** (`tasks/graders.py`, SPEC §3.1): Arabic-Indic digits, thousands separators, dates to ISO, case fold;
  payout within ±1 SAR; a malformed output is wrong, never an exception.
- **Test:** every gold output in dev / held-out / shifted validates against its task schema and grades 100% against
  itself (adjudicate `inputs`, which is not graded, is projected to the schema's keys first). Counts only are ever
  asserted or printed, never ids or values (held-out stays unseen). Result: dev 400/400, held-out 400/400,
  shifted 200/200 on both checks.
- **Latency measurement (Hamzah):** `latency_ms` = request sent to response received; queue/pacer wait is recorded
  separately as `queue_wait_ms` and excluded from p95 and the latency budgets (to be added with the matrix runner).

### D2.2 · Client: structured outputs in the cassette key, queue wait, rate-limit headers; entry probe built
- `LLMRequest.output_schema` is sent as `output_config.format` and enters the cassette key only when present, so
  every pre-existing cassette key is unchanged (`engine check` replay integrity re-derives them).
- `ModelCall.queue_wait_ms` (default 0) is recorded apart from `latency_ms`; latency starts at the moment of sending
  (after the budget guard and any pacer wait), so p95 and the latency budgets exclude our own queueing (Hamzah).
- Live calls return the parsed `anthropic-ratelimit-*` / `retry-after` headers (`CallResult.rate_limit`) for the
  matrix pacer; replay returns none.
- Held-out cannot be loaded through `eval.data.load_split` (raises `SealedSplit`); only `engine final` will read it.
- `engine probe` (24 calls: 4 dev items x 3 models x efforts low/high) is built; its requests are ordinary matrix
  requests, so their cassettes will be reused. Not yet run: awaiting Hamzah's sign-off on the estimate.

### D2.3 · Entry probe result: structured outputs + effort + adaptive thinking work on all 9 configs (Phase 2 entry check passed)
- **Run:** `probe-20261030T185356Z` (`runs/probe-20261030T185356Z/{calls.jsonl,summary.json}`), approved cap $1.50,
  spend **$0.294078** (Cost with caching (actual)); Cost without caching (headline) $0.422902; estimate was
  $0.126 (worst case $1.41). The estimator was recalibrated from this run (now $0.312 for the same 24 calls).
  The summary's `git_sha` was hand-corrected from `...-dirty` to the clean HEAD: the tree was clean at launch and
  was dirtied only by the run's own output files; the code now reads the SHA before the run writes anything.
- **Result:** 24/24 calls accepted with `output_config.format` + `output_config.effort` + `thinking: adaptive`
  (3 models x efforts low/high x 4 task schemas), all `end_turn`, all JSON schema-valid, no truncations, no
  errors; all 24 also graded correct (informational: n is too small to compare configs).
- **Max output seen (thinking included):** 1,727 tokens (`haiku-high`, adjudicate; 1,599 of them thinking), against
  the 6,144 cap. Opus and Sonnet often wrote 0 thinking tokens on faq / intent / extract; Haiku thought on most.
- **Finding 1, caches are per (model, task schema), superseding D0.6 check 5's "one cache per model":** the
  structured-output schema is part of the cached prefix, so each task has its own prefix (cached tokens: faq 7,219,
  intent 7,236, extract 7,450, adjudicate 8,300). On every model the four low-effort calls each wrote a cache and
  all four high-effort calls read one. Effort still does not invalidate the cache. Warm-up is therefore one request
  per (model, task), 12 in total.
- **Finding 2, the first call on a schema is slow:** 6.8-8.7 s for the first faq / intent / extract call per
  model against 1.3-2.0 s for the same tasks later (schema compilation plus cache write). Unhandled, this would
  inflate the p95 latency that becomes the latency budget. The matrix warms each (model, task) with a separate
  request (`repeat=1`, key distinct from every matrix request) whose result is not part of the data.
- **Finding 3, prefix size:** about 7.2K tokens (not the ~4.7K assumed), so the headline cost without caching is
  dominated by input: e.g. opus-high faq $0.0296 without caching vs $0.0021 with caching.

### D2.4 · Matrix runner, pacer and pilot subset built (no paid calls yet)
- `engine matrix --split dev --subset pilot|all`: paid runs need `--yes --cap-anthropic`; the estimate (Cost with
  caching (actual), Cost without caching (headline), worst case, wall clock) is printed first. Resumable by
  `--run-id`: finished cells are skipped, and in `auto` mode any request that has a cassette is replayed.
- Parallelism: one `Pacer` per model (limits are per model), max `--concurrency` calls in flight (default 6). It
  pauses on low `anthropic-ratelimit-*` headroom, halves its allowance on a 429 and honours `retry-after`. Time
  spent waiting is stored as `queue_wait_ms` and is never part of `latency_ms` (Hamzah).
- Warm-up: one tiny real request (`max_tokens` 64, fresh `repeat`) per (model, task) with live work pending, stored
  with role `probe`, excluded from every metric (D2.3 findings 1-2).
- A cell that returns no response is re-sent up to 3 times (data collection only; policies keep their own retry
  budget); any cell still without a response makes the command exit non-zero and is retried by resuming.
- Pilot: 40 dev tickets stratified by task x level (about 30% Arabic per stratum), fixed seed 20261030.
- `shifted` is refused until Phase 4; `heldout` cannot be loaded at all.

### D2.5 · Correction: commit cc9dcab was labelled "engine check green" but its replay-integrity step had crashed
- `engine check` raised `KeyError: 'request_hash'` on the probe run's log (rows wrapped as `{"call": ...}`); my
  command piped the output through `tail`, which hid the non-zero exit. The check now reads both row shapes
  (`src/engine/check.py`). Re-run with the real exit code: all four steps PASS (109 cassettes, 109 recorded calls
  referenced; smoke replay exact). From now on the exit code is read directly, not through a pipe.

### D2.6 · The clean-tree rule ignores the harness's own output paths (`runs/`, `cassettes/`)
- **Found:** the first pilot launch was refused, with no spend, because the matrix runner creates
  `runs/<run_id>/calls.jsonl` before its first paid call and a resumed run's earlier output is uncommitted; both
  made the tree "dirty" (D0.10).
- **Decision:** `runinfo.code_changes()` filters out `runs/` and `cassettes/`; `require_clean_tree()` and
  `git_sha()` use it. Anything else (code, prompts, config, data, docs) still blocks a paid run and marks the SHA
  `-dirty`. Run outputs cannot change which code or prompts a run used, which is what the rule protects.
- **Evidence:** `tests/test_runinfo.py::test_harness_outputs_do_not_make_the_tree_dirty`.

### D2.7 · Pilot result (run `matrix-dev-pilot-1`, 40 stratified dev tickets x 9 configs = 360 cells); connection cold start found
- **Run:** approved cap $5.00; spend **$1.279278** = $1.0398 for the 360 cells (Cost with caching (actual); Cost
  without caching (headline) $6.4194) + $0.2395 for 12 cache warm-up calls (excluded from every metric). Estimate
  was $2.03 (with caching) / $6.82 (without). 0 errors, 0 rate-limit (429) hits, 0 truncations, parse rate 100%,
  wall clock 98 s at 6 in flight per model. All 360 calls read the cache; max output seen 2,707 tokens (cap 6,144).
- **Accuracy:** 358/360 correct. The only two misses are the same ticket (dev-0168, an L4 over-sum-insured own-damage
  case with subrogation): `sonnet-low` got the decision wrong, `haiku-medium` the payout wrong. Both accuracy and the
  verifiers are far from discriminating at n = 40; the full 400 is needed. The V0-V2 verifiers agreed with the grader
  on 358/360 cells: 1 wrong answer passed all checks (the payout error), 1 right answer was rejected.
- **Effort effect on output tokens (mean, adjudicate):** Haiku 862 / 1,001 / 1,316 (low / medium / high), Sonnet
  223 / 330 / 454, Opus 205 / 345 / 372; Opus and Sonnet wrote almost no thinking on faq / intent / extract.
- **Finding (latency artifact):** the ~21 earliest-completed pilot calls took 6-7 s even for faq / extract (median 1.4-1.6 s),
  which inflates p95. Cause, measured with free `GET /v1/models` calls (18 parallel): the first request on each new
  connection takes 5.8-7.4 s from Saudi Arabia (TCP/TLS setup), later requests 0.27-0.40 s. The runner now
  opens its connection pool with free calls before any recorded call (`LLMClient.warm_connections`), so recorded
  latency excludes connection setup. Pilot latencies are therefore NOT usable for budgets; the dev matrix is
  recorded afresh (`--repeat 1` gives every request a new cassette key; the pilot stays on disk as evidence).
- **Estimator recalibrated** from the measured output means per model / task / effort (`eval/estimate.py`); the
  full dev matrix now estimates $10.76 with caching / $61.46 without.

### D2.8 · Full dev matrix recorded (run `matrix-dev-full-1`, epoch `--repeat 1`): 400 tickets x 9 configs = 3,600 cells
- **Run:** approved cap $20.00; spend **$10.525825** (estimate $10.76); 3,600/3,600 cells, 0 errors, 0 rate-limit hits,
  wall clock 712.7 s at 6 in flight per model, connections pre-warmed (setup median 6.65 s, excluded from latency).
  Ledger after the run is in `runs/spend.jsonl`. Provenance of every figure: `reports/phase2/*` headers (run, git
  SHA, config hash).
- **Replay gate:** `engine replay-check` and `tests/test_committed_matrix.py` replay all 3,600 recorded calls through the
  record/replay client with no key: per-call cost, latency, tokens, parse flag and every metric cell are identical
  (`reports/phase2/replay_check.txt`).
- **Findings:** accuracy is close to ceiling (every config at or above 0.97 overall; faq/intent/extract are 1.000 for
  most configs), so savings come from model choice (Haiku for faq / intent / extract) rather than from effort among
  expensive rungs; adjudicate is where only Opus meets the floor. B5 (naive cascade) is identical to B2 because
  `haiku-low` never fails V0 (parse rate 1.000). B4 equals B1 (`opus-low`): no cheaper single config meets every floor.
  CPST alone can reward failing hard tickets, so `engine evaluate` flags each policy "meets every floor" and the router
  headroom uses only policies that do (`reports/phase2/evaluate_*.txt`).
- **Budget rule (decision needed):** ties at top accuracy resolve to Haiku configs (approved tie-break), which sets
  tight budgets from Haiku's p95 and makes B1 fail latency on many tickets. `engine floors --budget-rule premium` sets
  the budget from the most expensive tied config instead ("never slower than always-premium"). Both are in
  `reports/phase2/floors_*.txt` and `evaluate_*.txt`. Proposal in `config/policy.yaml` is marked `proposed`.
- **Solvability:** `docs/SOLVABILITY.md` (one `opus-high` failure, ambiguous because of a caller / second-person name
  collision in the generator).

### D2.9 · Phase 2 sign-off (Hamzah): premium budget rule, floors frozen, no data change
- **Budget rule = PREMIUM.** Among configs tied for the best dev accuracy, the latency budget is the p95 of the most
  expensive tied config, rounded up to 0.5 s (SPEC §7.2 reworded). Both rules were computed before any optimisation
  (`reports/phase2/floors_{cheapest,premium}.txt`, `evaluate_{cheapest,premium}.txt`). Under the cheapest-tie rule the
  always-best baseline B1 failed its own intent latency budget (B1 intent success 0.517), which would have inflated
  every saving; premium is the fair, conservative choice. Effect on the B3 saving vs B1 (Cost without caching
  (headline) CPST): 52.9% under cheapest-tie, 49.5% under premium. The accuracy floors are identical under both.
- **Tolerances unchanged:** adjudicate 1 pt; extract, intent, faq 2 pts.
- **Name clash: no data change** (documented in `docs/SOLVABILITY.md` and the README limitations). The audit
  (`engine audit-names`, `reports/phase2/name_collisions.txt`) shows two mechanisms; the first draft of the solvability
  note described only the independent claimant draw and was corrected to include the structural driver-name reuse.
- **V2 unchanged, prompts stay frozen, false rejects documented as a known cost**
  (`reports/phase2/verifiers.txt`): V2 rejects 19 correct adjudicate answers (13 from a wrongly stated
  `other_party`, 6 missing reason codes).
- **Spend approved:** $12.26 (ledger `runs/spend.jsonl`).
- **Frozen:** `config/policy.yaml` (`status: frozen`, derived from `matrix-dev-full-1`) committed and tagged
  `floors-v1` before Phase 3. Changing floors, budgets or the keep/drop rule afterwards needs a new decision entry.
