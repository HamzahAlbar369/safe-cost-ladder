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
