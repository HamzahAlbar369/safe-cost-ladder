# CLAUDE.md — HUMAIN × Misk Hackathon · Challenge 2: Deliver AI with Less Compute

Working title: TBD (naming parked). Python package: `engine`.
Deadline: **Sat 31 Oct 2026, 20:00 Asia/Riyadh**. Hard technical freeze: **Sat 03:00**.
Owner: Hamzah (solo). Planning lives in a claude.ai chat Project; **this repo is the source of truth for the build.**

Read before starting any phase: the matching section of `docs/SPEC.md`.
Human-readable overview: `docs/ARCHITECTURE.pdf`. Decision log: `docs/DECISIONS.md`.

## What we are building
A domain-agnostic **efficiency layer**: for every request it picks the cheapest
(model, effort) configuration that still meets that task's accuracy floor and latency
budget, and it proves the savings on held-out data.

- Showcase workload: a **fictional** Saudi motor-insurance claims desk (bilingual EN/AR).
- Headline metric — **CPST, cost per successful task** = all USD spent (every call, retry,
  verification, router call, failed attempt) ÷ tasks that are correct AND within the task's
  latency budget.
- Thesis (verified Oct-2026 pricing): Haiku : Sonnet : Opus ≈ 1 : 20 : 40. A wasted Haiku
  attempt costs ~2% of a Sonnet call, so the savings live in picking the right rung among the
  expensive configs (especially **effort level**) and skipping waits. With caching, Sonnet/Opus
  input is nearly free (cache reads 0.05×), so output + thinking tokens dominate the bill.

## Locked decisions (ask Hamzah before changing any)
1. Task models: Anthropic only. 9 configs = {`claude-haiku-5-5`, `claude-sonnet-5-5`,
   `claude-opus-5-5`} × effort {low, medium, high} via `output_config.effort`. No `max`/`xhigh`.
2. Decision-model router, head-to-head: (a) local classifier (TF-IDF char n-grams + simple
   features → logistic regression), (b) TypeSafe **Jev** via OpenRouter, (c) cascade-only.
   Winner decided by the pre-registered keep/drop rule (SPEC §7.7).
3. Router sits **in front of** the cascade; low confidence → normal cascade.
4. Data: 100% synthetic, generated from `data/rules/rules.yaml` — the single source of truth
   for BOTH the policy document the models read AND the gold labels.
5. Splits: dev 240 / held-out 240 (sealed) / shifted 120. ~30% Arabic in every split
   (MSA + Saudi dialect; shifted leans dialectal), stratified by task × difficulty; some EN/AR
   parallel pairs.
6. **Per-task** accuracy floors (fallback: one global floor), derived from dev baselines and
   committed BEFORE any optimisation.
7. Budgets: Anthropic **$100** total (prepaid credit = hard cap); OpenRouter/Jev **$5**.
8. Evaluation by counterfactual replay over a recorded 9-config matrix; final policy confirmed
   by one live run on held-out.
9. Deliverables: public GitHub repo, PDF deck, 3–4 min demo video.

## Hard rules
- **Secrets**: keys only from env (`ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`) loaded from `.env`
  (gitignored). Never print, log, echo, or commit them. Never display `.env` contents.
- **Held-out**: never load `data/generated/heldout.jsonl` except via `engine final`, which refuses
  to run unless HEAD is a clean commit tagged `freeze-*`. Automated QA may scan it for
  duplicates/schema; no human or LLM reads its items and nothing is tuned against it.
- **Money**: every paid command prints a cost estimate first and aborts if it would exceed the
  remaining budget (ledger: `runs/spend.jsonl`). Ask Hamzah before any single run > $5.
- **Numbers**: never hand-type a metric into README, report, docs or slides. Every figure comes
  from a generated report tied to a run id + git SHA + config hash.
- **Prompts** freeze once the dev matrix is recorded; any prompt change means re-recording the
  affected cassettes (`engine check` fails on replay misses).
- **Prices** live only in `config/models.yaml` with `verified_on` and `source`. Cost is computed
  in USD from each model's own reported usage. Never compare token counts across models
  (Haiku 5.5 uses a different tokenizer).
- **Fiction**: the insurer and its rules are fictional. Label them so in data, docs and UI. Never
  present them as real Najm / SAMA / insurer rules.
- Ask before: changing a locked decision, adding a heavy dependency, deleting data or runs,
  force-pushing, or spending outside the ledger.

## Stack
Python 3.11+, uv · `anthropic` SDK · `httpx` (OpenRouter/Jev) · pydantic v2 for every data
contract · PyYAML · scikit-learn · numpy/pandas · jinja2 + plotly (static HTML report) · typer
(CLI) · pytest · ruff · pre-commit with gitleaks.

## Repo layout
```
CLAUDE.md  README.md  LICENSE  pyproject.toml  uv.lock  .env.example  .gitignore
config/            models.yaml (ids, prices, efforts) · policy.yaml (floors, budgets, cost-of-error)
data/rules/        rules.yaml (+ rules_v2.yaml for the policy-change scenario)
data/generated/    dev.jsonl · heldout.jsonl · shifted.jsonl · MANIFEST.json (sha256 + counts)
src/engine/
  contracts.py     pydantic models (SPEC §5)
  llm/             client.py (record/replay, cost, budget guard, caching layout) · jev.py
  datagen/         rules_engine.py · sampler.py · templates/ · paraphrase.py · qa.py · render_policy.py
  tasks/           prompts.py · graders.py
  tier0/  verify/  router/ (local.py, jev_router.py)  policy/ (ladder.py, cascade.py, controller.py)
  eval/            matrix.py · replay.py · metrics.py · bootstrap.py · oracle.py · scenarios.py
  report/          build.py · templates/
  cli.py
cassettes/         recorded API responses keyed by request hash (committed)
runs/              trace logs (JSONL) + spend.jsonl (committed)
reports/           report.html + figures (committed)
docs/              SPEC.md · ARCHITECTURE.pdf · DECISIONS.md
tests/
```

## Commands
```
uv sync
uv run engine smoke                 # Phase 0: 9 configs × 5 items; effort, tokens, latency, cache
uv run engine gen                   # generate + QA all splits, write MANIFEST.json
uv run engine matrix --split dev    # record 9-config matrix (paid; estimates first)
uv run engine floors                # derive + freeze per-task floors and latency budgets
uv run engine evaluate --split dev  # replay all policies → metrics with CIs
uv run engine router                # local vs Jev vs cascade head-to-head on recorded data
uv run engine scenario --price opus=2x --outage haiku   # instant what-if via replay
uv run engine final                 # held-out run (freeze-* tag only)
uv run engine report                # build reports/report.html from runs
uv run engine demo --replay         # judge-facing demo, no API key needed
uv run engine check                 # ruff + pytest + replay integrity + gitleaks (before EVERY commit)
```

## Phases (gates in SPEC §10 — a phase is done only when its gate passes,
## `engine check` is green, and the work is committed)
0 Recon & smoke · 1 Data · 2 Harness, matrix, floors · 3 Layers & router ·
4 Robustness & freeze · 5 Held-out & handoff · 6 Submission (deck, video, page — Saturday)

## Definition of done for any change
- Typed at boundaries (pydantic), unit-tested, ruff-clean, `engine check` green.
- SPEC updated if behaviour or a contract changed; decision logged in `docs/DECISIONS.md`
  (date · decision · evidence · run id).
- Committed as `phase<N>: <what> (<evidence or run id>)`. Commit often: history is evidence.

## Quality bar (full charter: SPEC §11)
Evidence over claims · reproducible from a fresh clone with no API key · no unexplained number ·
simplest thing that passes the gate · negative results reported honestly.

## Working style
- Before coding a phase: restate the plan in ≤10 bullets and list files to touch, then build.
- Small verifiable steps; run the relevant tests after each.
- If the spec is ambiguous or a gate cannot pass, stop and ask — never guess, mock, or fake data.
- Time pressure → follow the cut order: router experiment → scenario switcher → audit sampling →
  bring-your-own-tasks. Never cut: held-out protocol, replay, report, secret hygiene.
- Human sign-off required (stop and wait for Hamzah's explicit OK) before: starting each phase's
  build, every paid run, tagging floors-v1, tagging freeze-*, running engine final, and marking
  any phase done. At each gate, list the human checks for that phase from SPEC §11.9.
