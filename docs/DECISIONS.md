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
