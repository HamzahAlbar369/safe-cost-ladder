# Build Specification — Challenge 2: Deliver AI with Less Compute

Version 1.0 · 30 Oct 2026 · Owner: Hamzah · Status: locked unless noted "PROPOSED" or "OPEN".
`CLAUDE.md` holds the hard rules; this file holds the detail. Section numbers are referenced from code
comments and commit messages.

---

## §1 Goal and judging alignment

Build an efficiency layer that answers each request with the cheapest (model, effort) configuration that
meets that task's accuracy floor and latency budget, and prove it on held-out data.

| Judging criterion | What demonstrates it |
|---|---|
| Task Performance | Sealed held-out split; CPST, accuracy and p95 vs five baselines |
| Robustness & Adaptation | Shifted split (unseen templates, dialect, noise); policy-change scenario (rules v2); scenario switcher (floors, prices, outages) |
| Evaluation & Iteration | Pre-registered floors and keep/drop rule; ablation table with bootstrap CIs; replay-integrity check; commit history |
| Technical Judgment & Creativity | Tier 0; effort ladder; router head-to-head incl. an external decision model; oracle gap; break-even map; negative results |
| Engineering Quality | One-command run; record/replay with no API key; typed contracts; tests; pinned deps |
| Communication | Generated HTML report; deck mapped to these six criteria; 3–4 min video |

---

## §2 Models, effort, prices

### §2.1 Configurations
9 configs: `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5` × effort `low|medium|high`
(`output_config.effort`; omitting it equals `high`). `max` and `xhigh` are excluded (not cross-model).
Config id format: `haiku-low`, `sonnet-medium`, `opus-high`, …

### §2.2 Prices (config/models.yaml) — verified_on 2026-10-30 from consistent third-party pricing pages;
re-verify on the official Anthropic pricing page in Phase 0 and update `verified_on`/`source`.

| Model | Input $/MTok | Output $/MTok | Cache write 5m | Cache read | Notes |
|---|---|---|---|---|---|
| claude-haiku-5-5 | 0.10 | 0.50 | 0.125 | 0.01 | Prompts ≤100K tokens. >100K: 0.50 / 2.50 (never exceed) |
| claude-sonnet-5-5 | 2.00 | 10.00 | 2.50 | 0.10 | cache read 0.05× |
| claude-opus-5-5 | 4.00 | 20.00 | 5.00 | 0.20 | cache read 0.05× |

Thinking tokens bill as output. Batch (50% off) is out of scope unless added as a stretch item.
Jev (OpenRouter): $0.042/MTok input, output not billed (published rate; verify).

### §2.3 Phase 0 smoke checks (`engine smoke`) — record results in `runs/smoke.json` and DECISIONS.md
1. Each of the 9 configs accepts the request and returns parseable JSON for 5 fixed items (incl. 2 Arabic).
2. Effort changes output tokens and latency measurably (report mean output tokens per config).
3. Real input/output/thinking tokens and latency per config (feeds the cost estimator).
4. Minimum cacheable prefix per model (try the full static prefix; confirm `cache_read_input_tokens > 0` on repeat).
5. Whether changing effort on the same model invalidates the cache (Claude Code docs list effort changes as
   cache-invalidating; assume per-(model, effort) caches until proven otherwise).
6. Whether thinking must be explicitly enabled (`thinking: {type: "adaptive"}`) for effort to apply on each model.
7. Jev: endpoint reachable through OpenRouter, request schema confirmed from current docs, latency from
   Saudi Arabia (10 calls), Arabic handling (5 Arabic tickets).
Any config that fails 1 is dropped and logged; the design tolerates 6–9 configs.

---

## §3 Workload: fictional motor-insurance claims desk

Insurer: **"Oasis Motor Insurance (fictional demo insurer)"**. Policy document rendered from `rules.yaml`.

### §3.1 Task types and outputs (all outputs are strict JSON; parse failure = failed task)
| Task | Input | Output JSON | Grader | Cost of wrong answer (config) |
|---|---|---|---|---|
| `faq` | Customer question about the policy | `{"answer": <canonical value>}` (number, yes/no, or enum) | exact match after normalisation | low ($0.50) |
| `intent` | Free-text ticket | `{"intent": <label>}` | exact label | low ($0.50) |
| `extract` | Free-text claim message | `{"policy_number","accident_date","report_number","damage_amount_sar","fault_share"}` (null if absent) | all fields exact after normalisation; field-level accuracy also reported | medium ($5) |
| `adjudicate` | Claim narrative | `{"decision": approve|partial|deny|need_info, "payout_sar": int, "reasons": [rule_ids], "inputs": {...}}` | decision exact AND payout within ±1 SAR | high ($50) |

Decision definitions (also in `rules.yaml` → `decisions`; D1.8): **approve** = payable, reduced only by the
deductible (if any); **partial** = payable but reduced by the fault share or a cap (sum insured or the third-party
cap); **deny** = payout 0 (out of scope, policy not in force, exclusion, no own-damage cover, late report, 0% fault,
or loss at or below the deductible, CMIR 7.3); **need_info** = payout 0 because a required document is missing or
two stated values contradict each other. Every claim has a `claim_type`: `own_damage` (R3/R8, CMIR) or
`third_party_claim` (R4/R5, UP). `reasons` is reported but not graded. FAQ answers are a number, `yes`/`no`, an
enum value, or `out_of_scope` for non-insurance questions (D1.3).

Intent labels (9; D1.5): `new_claim, claim_status, coverage_question, document_submission, complaint,
policy_change, payment_issue, fault_dispute, other`. Overlap definitions live in `rules.yaml` → `intents`:
`new_claim` = no claim exists yet; `document_submission` = a claim exists and a document is being sent;
`payment_issue` = the claim payout only (IBAN, delay, wrong amount); premium and renewal → `policy_change`;
`fault_dispute` = objection to the fault share in the accident report; out-of-scope perils (injury/death, theft,
fire, flood) and non-insurance messages → `other`.

Normalisation: Arabic-Indic digits → ASCII; strip thousands separators; dates → ISO; case/whitespace fold.

### §3.2 Difficulty levels (global, used for stratification)
| Level | Content | Share |
|---|---|---|
| L1 | FAQ, single fact lookup | 25% |
| L2 | Intent classification and field extraction | 30% |
| L3 | Adjudication, one rule applies | 20% |
| L4 | Adjudication, 2–3 interacting rules + distractor details | 15% |
| L5 | Adjudication with missing or contradictory info → correct answer `need_info` (or a specific deny) | 10% |

Task mix follows from levels (≈25% faq, 30% intent+extract split evenly, 45% adjudicate).
The skew toward easy traffic is deliberate and declared: it mirrors real support queues.

---

## §4 Data generation (`engine gen`)

### §4.1 Rules file — single source of truth (`data/rules/rules.yaml`)
Fictional insurer; rules follow SAMA-issued instruments administered by the Insurance Authority: the Unified
Compulsory Motor Insurance Policy (UP), the Comprehensive Motor Insurance Rules (CMIR) and the Claims' Settlement
Instructions (CSI). Every rule, parameter and item carries a `source:` (D1.8); the generated table is
`data/rules/SOURCES.md`. Values shown are v1.
- R0 Desk scope (insurer-specific): injury/death, theft, fire, flood → intent `other` (no R0 adjudication items).
- R1 Cover: `TPL` (liability to third parties) and `COMP` (own vehicle + third parties). Own damage under TPL →
  deny (UP 6.1). Accident after the policy end date → deny.
- R2 Fault share ∈ {0, 25, 50, 75, 100} % from the Najm or traffic-police report.
- R3 Own damage (COMP, CMIR 5.3/5.4): base = sum insured on technical total loss or repair > ETL% (60) × sum
  insured, else min(repair, sum insured). Deductible applied = fixed deductible (SAR 1,000) × fault %; 0 if not
  liable or hit-and-run; full if no other party; also on total loss. Payout = base − deductible applied. Repair
  estimate ≤ full fixed deductible → deny (7.3).
- R4 Third-party claim (UP): payout = damage × fault share, cap SAR 10,000,000; 0% fault → deny.
- R5 Exclusions: third-party claim → deny for UP Art. 6 cases (fled scene, DUI, drifting/racing, deliberate,
  misrepresentation); paid + `RECOVERY_RIGHT` for UP Art. 5 cases (invalid licence with 50-day grace, wrong
  direction, red light, use outside purpose). Own damage → deny for CMIR Art. 7 (all listed; sampler generates 7.2
  licence with 50-business-day grace, 7.3, 7.4 unauthorised driver, 7.16 violation proven to have caused the accident).
- R6 Reporting window (insurer-specific): > 15 days → deny unless an accepted justification is stated.
- R7 Required documents (CSI): accident report, registration, licence copy, damage photos, damage assessment;
  missing or contradictory → `need_info`.
- R8 Other party ∈ {insured, uninsured, unknown, none}: COMP + unknown → no deductible, no subrogation; TPL +
  unknown/uninsured → deny own damage. Report from Najm or the traffic police.
- Precedence (first match decides) is listed in the YAML and SOURCES.md.
- FAQ-only facts (`faq_only`): licence grace 50 days (TPL) vs 50 business days (COMP), no deductible when not
  liable, no deduction for prior use, towing SAR 500 / 1,000, settlement < SAR 2,000 in 5 working days else 15 days,
  missing-documents notice 3 working days, total-loss report 7 working days, replacement car = optional add-on,
  claim statuses, options when the other party is 100% at fault.
`render_policy.py` turns rules.yaml into the policy document (EN + AR); `rules_engine.py` computes gold labels
from the same file. `rules_v2.yaml` changes only insurer-specific values (fixed deductible, ETL %, reporting window; D1.8).

### §4.2 Pipeline
1. **Sample** case facts per level with a seeded RNG (seed recorded in MANIFEST).
2. **Compute gold** with `rules_engine.py`.
3. **Realise text** from template families (≥6 families per task per language for dev/held-out; the shifted
   split uses held-back families only; D1.2).
4. **Variation layer** (deterministic, seeded): typos, filler, sentence reordering, Arabic/English code-switching.
   Never edits a gold-relevant value. **Fact-preservation check**: every value in `meta.facts` must still appear
   (after normalisation) or the item is regenerated. No LLM paraphrase; Phase 1 makes no paid calls (D1.2).
   (A non-Anthropic rewrite of the shifted split is deferred; §13, D1.6.)
5. **QA** (§4.4), then write splits + `MANIFEST.json` (counts, composition, sha256 per file, seed, generator git SHA).

### §4.3 Split composition
| Split | n | Arabic | Notes |
|---|---|---|---|
| dev | 400 | ~30% (mostly MSA, light Saudi dialect) | tuning, floors, router training (cross-validated) |
| heldout | 400 | ~30% (same mix as dev) | sealed; run once at `freeze-*` tag |
| shifted | 200 | ~30%, dialect-leaning | held-back template families only, longer, noisier, code-switching; 40 items use rules_v2; ~20 adversarial items |

Sizes per D1.1. ~20% of dev items are EN/AR parallel pairs (same facts, both languages) for the language
cost/accuracy comparison. Stratify every split by task × level × language (±3 percentage points of target).

Adversarial / out-of-scope items (shifted only, ~20; D1.3), correct behaviour defined in `rules.yaml` →
`adversarial`: prompt injection asking for approval (gold = the rules applied to the facts, injection ignored);
non-insurance questions (`faq` → `out_of_scope`, `intent` → `other`); garbled or near-empty messages
(`intent` → `other`, `adjudicate` → `need_info`); very long rambling tickets (normal gold). Tagged
`meta.scenario = adversarial` so they are reported separately as well as in the shifted totals.

### §4.4 QA thresholds (all must pass; failures block Phase 1)
| Check | Threshold |
|---|---|
| Schema validity | 100% |
| Decision-label distribution per split in MANIFEST (D1.8) | any label < 10% of adjudication items is flagged |
| Exact duplicates across splits | 0 |
| Near-duplicates across splits (char 5-gram Jaccard ≥ 0.8) | 0 |
| Composition vs §4.3 | within ±3 pts |
| Fact preservation after the variation layer (every `meta.facts` value present after normalisation) | 100% |
| Template leak: label predictable from `template_family` id alone | ≤ majority-class rate + 5 pts |
| Rules-engine unit tests | ≥1 test per rule + interaction tests; 100% pass |
| Manual review (Hamzah): 30 EN + 20 AR dev items | 0 label errors (any error → fix generator, regenerate) |
| Solvability (Phase 2): every `opus-high` failure on dev inspected | generator-bug rate after fixes < 2% |

---

## §5 Data contracts (`src/engine/contracts.py`, pydantic v2)

- **Ticket**: `id, split, task_type, level, language (en|ar), dialect (msa|saudi|mixed), template_family,
  rules_version, parallel_pair_id?, text, gold (task-typed), meta{rule_ids, distractors, scenario
  (normal|adversarial|policy_change), facts (gold-relevant surface values, for the fact-preservation check),
  case (the sampled facts gold was computed from, incl. `claim_type`), trace (rule-by-rule engine trace)}`.
- **ModelCall** (one per API call): `call_id, ticket_id, run_id, config_id, model, effort, role
  (answer|verify|router), request_hash, input_tokens, cache_creation_tokens, cache_read_tokens, output_tokens,
  latency_ms, cost_usd, cost_usd_nocache, stop_reason, parsed_ok, error?, replayed (bool), ts`.
- **TaskResult**: `ticket_id, policy_id, path [config_ids in order], final_output, correct, latency_ms_total,
  cost_usd_total, success (correct AND within budget), verifier_verdicts, router{name, choice, confidence}`.
- **PolicySpec**: `policy_id, tier0 (bool), router (none|local|jev), threshold, ladder [config_ids],
  verify_level_by_task, cache (bool)`.
- **RunManifest**: `run_id, git_sha, config_hash, split, policies, created_at, spend_usd`.
All JSONL; one record per line; never mutate a committed run file (write a new run).

---

## §6 System architecture

### §6.1 Request flow
1. **Tier 0 (no model)**: language detection; deterministic regex extraction when unambiguous (e.g. exactly one
   policy-number pattern); FAQ lookup when the question exactly matches a canonical FAQ key; reject empty or
   duplicate tickets. Steps aside on any ambiguity.
2. **Router** (variant per policy): predicts the cheapest sufficient rung and a confidence. Confident → start at that
   rung. Unsure (below threshold) → start the cascade at the bottom rung.
3. **Ladder**: the Pareto-efficient subset of the 9 configs for that task, ordered by cost (dominated configs removed
   in Phase 2). Escalation moves one rung up.
4. **Verifier** (risk-tiered, §6.3). Pass → answer. Fail → escalate; top rung failure → return best answer flagged
   for human review (counts as a failure in metrics).
5. **Controller** reads `config/policy.yaml` (floors, budgets, cost-of-error, retry budget) and chooses ladder,
   threshold and verify depth per task.
6. **Trace log** records every call (ModelCall) and result (TaskResult).

### §6.2 Prompt and cache layout
- `system` = one static block: role + all four task instructions + full policy document (identical across tasks so
  every task shares one cached prefix per config). Marked with `cache_control` (5-minute TTL).
- `user` = task type + ticket text only. Nothing dynamic (ids, timestamps) in the static block.
- Output caps: strict JSON schema in the prompt and a per-task `max_tokens` (set from Phase 0 measurements with
  headroom for thinking; truncation = failure, logged).
- Caches are per model: §2.3 check 5 (run `smoke-20261030T130454Z`, DECISIONS D0.6) showed an effort change does not
  invalidate the cached system prefix. Warm up one request per model before parallel runs.

### §6.3 Verification
| Level | Check | Applies to |
|---|---|---|
| V0 | JSON parses, schema valid, enum labels valid | all |
| V1 | Grounding: extracted literals (policy no., report no., dates, amounts) appear in the ticket text | extract, adjudicate |
| V2 | Consistency: payout recomputed from the model's own stated `inputs` with the published formula; decision consistent with stated reasons | adjudicate |
| V3 | Second opinion: one rung higher must agree, only when expected loss (p_error × cost_of_error) exceeds the check's cost | adjudicate (high payout) |
Verifier false-accept rate (wrong answer passing all checks) is measured per task on dev.

### §6.4 Routers
- **Local**: TF-IDF char 2–5-grams over ticket text + features (length, language, count of digits/amounts/dates,
  Tier-0 intent hint). Target: cheapest correct Pareto rung within budget (multi-class). Logistic regression,
  5-fold cross-validated on dev (out-of-fold predictions only for evaluation). Confidence = max class probability.
- **Jev (zero-shot)**: typed questions over the ticket (e.g. complexity choice, needs-calculation boolean,
  missing-information boolean); answers map to a rung via a fixed mapping declared in DECISIONS.md BEFORE running.
  Probabilities used as confidence. All calls recorded/replayed like LLM calls. Ticket text only (no policy doc).
- **Cascade-only**: no router; always start at the bottom rung.
Thresholds for both routers tuned on dev out-of-fold data only.

### §6.5 Record/replay
Every API call goes through `llm/client.py`. Key = sha256 of (model, effort, system, user, max_tokens, schema,
thinking mode, repeat index); `thinking` = omitted|adaptive, `repeat` = 0 except for deliberate identical repeats
(cache probes). The system prompt enters the key and the cassette as its sha256 (approved 2026-10-30, DECISIONS.md).
Jev calls use their own key: sha256 of (model, state, questions, repeat).
Paid (live/auto) calls refuse to run on a dirty working tree so every run's git SHA is clean; only `engine smoke`
is exempt (DECISIONS D0.10).
Modes: `live` (call + record), `replay` (cassette only; miss = error), `auto` (replay if present). Recorded latency
is stored and reused in replay; replayed results are labelled `replayed=true` and reports say "simulated".

### §6.6 PROPOSED (needs Hamzah's OK): extract-then-compute variant
For `adjudicate`, a cheap model extracts structured facts and the deterministic rules engine computes decision
and payout (LLMs don't do the arithmetic). Evaluated as one more policy; likely large savings at high accuracy and
a strong "simpler alternative" result. Gold labels remain independent (engine applied to TRUE facts; the variant
applies it to EXTRACTED facts).

---

## §7 Evaluation protocol

### §7.1 Success
A task is a success iff the grader marks it correct AND total latency ≤ that task's budget.
**CPST** = Σ cost_usd over every call (answer, verify, router, retries, failures) ÷ number of successes.

### §7.2 Floors and budgets (`engine floors`, frozen and committed as tag `floors-v1` before Phase 3)
- Accuracy floor per task = accuracy of the most accurate single config on dev for that task − tolerance
  (adjudicate 1 pt; extract, intent, faq 2 pts).
- Latency budget per task = p95 latency of that same most-accurate config on dev ("never slower than always-premium"),
  rounded up to 0.5 s.
- Fallback if per-task floors prove unworkable: one global floor = most accurate config overall − 2 pts (log in DECISIONS.md).

### §7.3 Policies compared
Baselines: B1 always-best (most accurate config) · B2 always-cheapest (`haiku-low`) · B3 static rules by task type ·
B4 cheapest single config meeting every floor · B5 naive cascade (`haiku-low` → most accurate config on V0 failure).
Ours: O1 Tier 0 + ladder cascade + risk-tiered verification + caching · O2 = O1 + local router · O3 = O1 + Jev router ·
(O4 extract-then-compute, if approved).

### §7.4 Counterfactual replay
Record all 9 configs on every dev and shifted ticket once (`engine matrix`). Any policy is then evaluated by lookup:
follow its decision path through recorded answers, verdicts, costs and latencies (sequential latencies summed,
router latency added). Zero extra API cost. The same recordings give the oracle, router training labels and the
scenario switcher.

### §7.5 Reporting rules
- Labels (D1.4), used verbatim everywhere: **"Cost without caching (headline)"** = all prompt tokens at the base
  input rate (`cost_usd_nocache`): conservative and order-independent. **"Cost with caching (actual)"** = what was
  billed (`cost_usd`).
- Beside them, if shown: modelled steady-state cache cost (static prefix at cache-read price, writes amortised per
  5-min window at a stated traffic rate) — labelled "modelled".
- Every metric reported per task, per language, and overall, with 95% paired bootstrap CIs (2,000 resamples, fixed seed).
- **Oracle**: per ticket, cheapest correct config within budget. Gap captured = (CPST_B1 − CPST_policy) / (CPST_B1 − CPST_oracle).
- **Break-even map**: per task, each rung's pass rate vs its break-even threshold (cost_rung + cost_verify) / cost_next_rung.
- Ablations: each layer of O1 toggled off one at a time.
- Simulated vs live: the final policy's live held-out run is compared with its simulated result; the gap is reported.

### §7.6 Held-out protocol
Held-out is evaluated exactly once, by `engine final`, at a clean commit tagged `freeze-*`: it records the 9-config
matrix on held-out (for baselines/oracle via replay) and runs the chosen final policy live. Results are committed in a
new run; no further changes to prompts, ladder, thresholds or code paths affecting outputs.

### §7.7 Pre-registered keep/drop rule for routers (do not edit after Phase 2)
A router is kept iff, on BOTH dev (out-of-fold) and shifted:
(a) CPST improves ≥ 5% vs O1 with the 95% CI excluding 0, OR p95 latency improves ≥ 20% with the CI excluding 0; AND
(b) no per-task accuracy floor is breached.
If both routers qualify, keep the one with lower CPST. Otherwise report the result as a negative finding.
Also report: misroute rates in both directions and a collapse check (share of tickets sent above the oracle rung).

---

## §8 Robustness
- **Shifted split** (§4.3): headline metrics re-reported; floor breaches explained or fixed without touching held-out.
- **Policy-change scenario**: 40 shifted items generated under `rules_v2.yaml`; the system is pointed at the v2 policy
  document via config only (no code change). Success = floors still met.
- **Scenario switcher** (`engine scenario`, replay-based, instant): accuracy floors ±, latency budgets ±, price
  multipliers per model, model outage (remove configs), router on/off. At least 3 scenarios in the report.
- Failure behaviour: API errors retried at most once per call (retry budget in policy.yaml), then escalate; all retries billed.

---

## §9 Handoff
- README: problem, approach, headline results (generated block), one-command quickstart (`uv sync && uv run engine demo --replay`),
  how to run live with your own key, repo map, limitations, fiction disclaimer, licence.
- `reports/report.html` committed; `cassettes/` and `runs/` committed so a fresh clone reproduces all numbers with no key.
- Repo hygiene: `.gitignore` contains `.env`, `CLAUDE.local.md`, `.claude/settings.local.json`, caches, venvs.
  `CLAUDE.md`, `docs/`, `.claude/settings.json` (if any) are committed. gitleaks clean before going public.

---

## §10 Phases and exit gates (times are Fri 30 → Sat 31 Oct, Asia/Riyadh)

| Phase | Window | Exit gate (all must hold) |
|---|---|---|
| 0 Recon & smoke | 13:15–14:00 | Repo + `.gitignore` + `.env.example` + pre-commit/gitleaks committed · prices re-verified · `engine smoke` results logged (§2.3 items 1–7) · Jev reachable + Arabic result logged · mentor slot booked |
| 1 Data | 14:00–17:30 | rules.yaml reviewed by Hamzah · rules-engine tests pass · all §4.4 checks pass · MANIFEST committed · held-out sealed (hash recorded) |
| 2 Harness, matrix, floors | 17:30–20:00 | 9-config dev matrix recorded, 0 unrecorded calls · replay reproduces live metrics exactly · solvability check done · baselines table generated · floors/budgets frozen (tag `floors-v1`) · oracle gap computed · router go/no-go logged · spend logged |
| 3 Layers & router | 20:30–00:30 | Ablation row with CI for every layer; layers without gain removed or justified · verifier false-accept rate per task · router keep/drop decided by §7.7 · chosen policy meets all floors on dev |
| 4 Robustness & freeze | 00:30–01:15 | Shifted + policy-change results generated · ≥3 scenarios run · prompts frozen · tag `freeze-v1` |
| 5 Held-out & handoff | 01:15–03:00 | `engine final` run once · simulated-vs-live gap reported · report regenerated · fresh-clone test passes with no key · README complete · gitleaks clean |
| 6 Submission | Sat | Deck maps to six criteria and every number is cross-checked against the report · video 3–4 min, public link checked logged-out · repo public · project page complete |

Hard freeze 03:00 whatever the state; anything unfinished is cut per the cut order and documented as next steps.

---

## §11 Quality charter (applies to every phase and every artifact)

Each item is a checkable standard. "Blocker" items stop a gate; "Target" items are expected but may be waived with a
logged reason in DECISIONS.md.

### §11.1 Evidence and correctness — Blocker
- Every number in README, report, deck and video traces to a run id + git SHA + config hash.
- No claim without a comparison: every improvement is stated against a named baseline with a CI.
- Simulated results are labelled "simulated"; modelled cache costs labelled "modelled".
- Negative results (e.g. a router that lost) are reported, not hidden.

### §11.2 Data — Blocker
- All §4.4 thresholds pass. Gold labels come only from the rules engine. Held-out is never inspected or tuned on.
- Fiction disclaimer present on the policy document and in the README.

### §11.3 Code — Blocker (first three), Target (rest)
- pydantic contracts at every boundary; no untyped dicts crossing modules.
- `engine check` green: ruff, pytest, replay integrity, gitleaks.
- Unit tests for: rules engine (every rule + interactions), graders (incl. Arabic digit normalisation), cost
  accounting (hand-computed fixtures), replay determinism, budget guard.
- Target: functions small and named for what they do; no notebook-only logic; seeds fixed and recorded; no dead code.

### §11.4 Evaluation — Blocker
- Floors, budgets and the router keep/drop rule are committed before the results they judge.
- Dev/held-out separation enforced in code (`engine final` tag check), not by discipline alone.
- Paired bootstrap CIs on every comparison; per-task and per-language breakdowns.

### §11.5 Cost and security — Blocker
- Budget guard on every paid command; ledger matches the Anthropic console within 5%.
- No secret ever committed (pre-commit gitleaks + final scan). If one leaks: revoke the key immediately.

### §11.6 Reproducibility and handoff — Blocker
- Fresh clone → `uv sync && uv run engine demo --replay` reproduces the report's numbers exactly, with no API key.
- Dependencies pinned (uv.lock). Python version stated.

### §11.7 Communication — Target
- Every chart: title, axis units, data source (run id) in caption.
- Deck: one section per judging criterion; one claim per slide, backed by a report figure.
- Video: challenge → approach → live/replay demo → results → next steps, 3–4 minutes.
- Plain language first, technical term second.

### §11.8 Review ritual (end of every phase)
1. Run `engine check`. 2. Walk the phase's gate row in §10 and tick each item with evidence (file/run id).
3. Log decisions and any waived Target items in DECISIONS.md. 4. Commit. 5. Post a 3-line status to Hamzah:
done / evidence / next.

---

## §12 Risk register
| Risk | Impact | Mitigation |
|---|---|---|
| Time overrun (≈2 h behind plan already) | Incomplete handoff | Gates + cut order + 03:00 hard freeze |
| Rules-engine or generator bugs | Wrong gold labels | Unit tests, solvability check, manual review |
| Template artifacts make tasks too easy | Inflated results | Multiple families, leak check, shifted split with unseen families |
| Effort unsupported on a model | Fewer configs | §2.3 smoke test; design tolerates 6–9 configs |
| Thinking tokens blow the budget | Overspend | Phase 0 measurements, per-run estimate, $5 ask threshold, prepaid cap |
| Jev access/latency from KSA | Router variant lost | Local router still competes; report the access result |
| Cache behaviour differs from assumptions | Wrong cost model | Headline uses no-cache cost; cache reported as modelled |
| Small-sample noise | False wins | Bootstrap CIs, pre-registered thresholds |
| Grader edge cases (Arabic numerals, dates) | Mis-scored items | Normalisation tests incl. Arabic fixtures |
| Secret leak in public repo | Key abuse | gitleaks pre-commit + final scan; revoke on leak |
| Judges can't run it | Lost Engineering points | Replay mode, fresh-clone test |

---

## §13 Cut order and open items
Cut order under time pressure: router experiment → scenario switcher → audit sampling → bring-your-own-tasks.
Never cut: held-out protocol, replay, report, secret hygiene.

OPEN: product name · approval of §6.6 extract-then-compute · Jev access confirmation (Phase 0) ·
Hamzah's review of rules.yaml wording and intent labels.

DEFERRED (Phase 3, if time allows; D1.6): AI rewrite of the shifted split only, by a non-Anthropic model via
OpenRouter, with a fact-preservation check that rejects any rewrite changing a gold-relevant value (`meta.facts`).
Gold labels are computed from case facts, so a rewrite never changes them.
