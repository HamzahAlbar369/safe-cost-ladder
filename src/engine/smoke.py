"""`engine smoke`: Phase 0 checks 1–7 (SPEC §2.3). Results go to runs/smoke.json; calls to runs/<run_id>/.

Call plan, per model and in this order (order matters for the cache checks):
  cache_size  3 prefix sizes x 2 identical calls (write, then read)            -> check 4
  matrix      3 efforts x 5 probe items, full static prefix, thinking omitted -> checks 1, 2, 3, 4 (full), 5
  thinking    2 items x {low, high} with thinking={"type": "adaptive"}       -> check 6
Models run in parallel threads (sequential within a model). Jev runs last, sequentially -> check 7.
"""

from __future__ import annotations

import json
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from engine import runinfo
from engine.contracts import JevRequest, JevResponse, LLMRequest, ModelCall, SmokeReport
from engine.llm import jev
from engine.llm.client import (
    BudgetExceeded,
    CassetteStore,
    Ledger,
    LLMClient,
    Mode,
    RunBudget,
    estimate_tokens,
    load_key,
    request_hash,
    worst_case_cost,
)
from engine.llm.pricing import ROOT, PriceBook, pricebook
from engine.smoke_fixtures import (
    EXPECTED_KEYS,
    FICTION_LABEL,
    JEV_QUESTIONS_SPEC,
    PROBE_ITEMS,
    STATIC_PREFIX,
    ProbeItem,
    user_message,
)

MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5")
EFFORTS = ("low", "medium", "high")
SMOKE_MAX_TOKENS = 32000  # generous on purpose: high-effort thinking must not be truncated
PROBE_MAX_TOKENS = 4000
CACHE_PROBE_CHARS = (1000, 2400, 4800)  # ~250 / ~600 / ~1200 tokens of English text
THINKING_ITEMS = ("probe-1-faq", "probe-4-adjudicate")
THINKING_EFFORTS = ("low", "high")
EXPECTED_OUTPUT_TOKENS = {"low": 400, "medium": 1200, "high": 3000}  # estimate assumption only
SMOKE_JSON = ROOT / "runs" / "smoke.json"
ITEMS = {i.id: i for i in PROBE_ITEMS}


# --------------------------------------------------------------------------- plan


@dataclass(frozen=True)
class Planned:
    check: str  # cache_size | matrix | thinking
    tag: str
    item: ProbeItem
    req: LLMRequest


@dataclass(frozen=True)
class PlannedJev:
    item_id: str
    language: str
    req: JevRequest


def plan_anthropic() -> dict[str, list[Planned]]:
    plan: dict[str, list[Planned]] = {}
    faq = ITEMS["probe-1-faq"]
    for model in MODELS:
        steps: list[Planned] = []
        for chars in CACHE_PROBE_CHARS:
            system = f"CACHE-SIZE PROBE ({chars} chars). {FICTION_LABEL}\n{STATIC_PREFIX[:chars]}"
            for repeat in (0, 1):
                req = LLMRequest(
                    model=model,
                    effort="low",
                    system=system,
                    user=user_message(faq),
                    max_tokens=PROBE_MAX_TOKENS,
                    schema_name=faq.task,
                    repeat=repeat,
                )
                steps.append(Planned("cache_size", str(chars), faq, req))
        for effort in EFFORTS:
            for item in PROBE_ITEMS:
                req = LLMRequest(
                    model=model,
                    effort=effort,
                    system=STATIC_PREFIX,
                    user=user_message(item),
                    max_tokens=SMOKE_MAX_TOKENS,
                    schema_name=item.task,
                )
                steps.append(Planned("matrix", item.id, item, req))
        for item_id in THINKING_ITEMS:
            for effort in THINKING_EFFORTS:
                item = ITEMS[item_id]
                req = LLMRequest(
                    model=model,
                    effort=effort,
                    system=STATIC_PREFIX,
                    user=user_message(item),
                    max_tokens=SMOKE_MAX_TOKENS,
                    schema_name=item.task,
                    thinking="adaptive",
                )
                steps.append(Planned("thinking", item_id, item, req))
        plan[model] = steps
    return plan


def jev_questions() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name, spec in JEV_QUESTIONS_SPEC.items():
        if spec["kind"] == "choice":
            out[name] = jev.choice(spec["instructions"], spec["criteria"])
        else:
            out[name] = jev.noul(spec["instructions"])
    return out


def plan_jev() -> list[PlannedJev]:
    qs = jev_questions()
    return [
        PlannedJev(item.id, lang, JevRequest(model=jev.JEV_MODEL, state=getattr(item, lang), questions=qs))
        for lang in ("en", "ar")
        for item in PROBE_ITEMS
    ]


# --------------------------------------------------------------------------- estimate


def estimate(prices: PriceBook | None = None) -> dict[str, Any]:
    """Expected and worst-case USD per check. Input tokens use the conservative bytes/2 estimate."""
    prices = prices or pricebook()
    rows: dict[str, dict[str, float]] = {}
    for model, steps in plan_anthropic().items():
        p = prices.price(model)
        seen_prefix: set[tuple[str, str, str]] = set()
        for s in steps:
            key = (s.req.system, s.req.effort, s.req.thinking)
            prompt = estimate_tokens(s.req.system)
            user = estimate_tokens(s.req.user)
            if key in seen_prefix:
                in_cost = prompt * p.cache_read + user * p.input
            else:
                in_cost = prompt * p.cache_write_5m + user * p.input
                seen_prefix.add(key)
            out_cost = EXPECTED_OUTPUT_TOKENS[s.req.effort] * p.output
            row = rows.setdefault(f"{s.check}:{p.short}", {"calls": 0, "expected": 0.0, "worst": 0.0})
            row["calls"] += 1
            row["expected"] += (in_cost + out_cost) / 1e6
            row["worst"] += worst_case_cost(p, s.req)
    jc = jev.JevClient("replay", "estimate", prices=prices)
    jev_rows = [jc.estimate(j.req) for j in plan_jev()]
    rows["jev:jev"] = {"calls": len(jev_rows), "expected": sum(jev_rows), "worst": sum(jev_rows)}
    anth = [r for k, r in rows.items() if not k.startswith("jev")]
    return {
        "rows": rows,
        "anthropic_expected": sum(r["expected"] for r in anth),
        "anthropic_worst": sum(r["worst"] for r in anth),
        "openrouter_expected": rows["jev:jev"]["expected"],
        "assumptions": {
            "input_tokens": "UTF-8 bytes / 2 (over-counts English ~2x)",
            "expected_output_tokens_incl_thinking": EXPECTED_OUTPUT_TOKENS,
            "cache": "first call per (model, effort, prefix, thinking) writes; later calls read",
            "worst": "no cache reads, every call hits max_tokens",
        },
    }


# --------------------------------------------------------------------------- run


@dataclass
class SmokeCall:
    check: str
    tag: str
    task: str
    call: ModelCall
    strict_json: bool = False
    fenced_json: bool = False
    keys_ok: bool = False


@dataclass
class JevCall:
    request_hash: str
    item_id: str
    language: str
    response: JevResponse | None
    replayed: bool
    error: str | None = None


@dataclass
class RunState:
    calls: list[SmokeCall] = field(default_factory=list)
    aborted: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


def parse_json(text: str) -> tuple[Any, bool, bool]:
    """(obj, strict_ok, fenced_ok). Strict = the whole text is one JSON value (SPEC §3.1)."""
    try:
        return json.loads(text.strip()), True, True
    except ValueError:
        pass
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
        try:
            return json.loads(t), False, True
        except ValueError:
            pass
    return None, False, False


def keys_ok(task: str, obj: Any) -> bool:
    return isinstance(obj, dict) and EXPECTED_KEYS[task] <= set(obj)


def _validator(task: str):
    def validate(text: str) -> bool:
        obj, strict, _ = parse_json(text)
        return strict and keys_ok(task, obj)

    return validate


def _run_model(client: LLMClient, steps: list[Planned], state: RunState) -> None:
    for s in steps:
        try:
            res = client.call(s.req, ticket_id=s.item.id, role="probe", validate=_validator(s.item.task))
        except BudgetExceeded as e:
            with state.lock:
                state.aborted.append(f"{s.req.model}: {e}")
            return
        obj, strict, fenced = parse_json(res.response.text) if res.response else (None, False, False)
        rec = SmokeCall(s.check, s.tag, s.item.task, res.call, strict, fenced, keys_ok(s.item.task, obj))
        with state.lock:
            state.calls.append(rec)


def list_models(mode: Mode, sdk: Any = None, smoke_json: Path = SMOKE_JSON) -> dict[str, Any]:
    """Verify model IDs with the Models API (free). Replay reuses the recorded result."""
    if mode == "replay":
        if smoke_json.exists():
            return json.loads(smoke_json.read_text(encoding="utf-8"))["models_api"]
        return {"skipped": "replay mode and no runs/smoke.json"}
    if sdk is None:
        import anthropic

        sdk = anthropic.Anthropic(api_key=load_key("ANTHROPIC_API_KEY"), max_retries=1)
    listed = {m.id: m for m in sdk.models.list()}
    found: dict[str, Any] = {}
    for mid in MODELS:
        m = listed.get(mid)
        if m is None:
            continue
        caps = getattr(m, "capabilities", None)
        found[mid] = {
            "display_name": getattr(m, "display_name", None),
            "max_input_tokens": getattr(m, "max_input_tokens", None),
            "max_tokens": getattr(m, "max_tokens", None),
            "capabilities": caps.to_dict() if hasattr(caps, "to_dict") else caps,
        }
    return {
        "listed": found,
        "missing": [m for m in MODELS if m not in found],
        "total_models_listed": len(listed),
    }


def run(
    mode: Mode,
    caps: dict[str, float] | None = None,
    *,
    ledger: Ledger | None = None,
    store: CassetteStore | None = None,
    sdk: Any = None,
    http: httpx.Client | None = None,
    smoke_json: Path = SMOKE_JSON,
) -> tuple[SmokeReport, list[SmokeCall], list[JevCall]]:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"smoke-{ts}" if mode != "replay" else f"smoke-replay-{ts}"
    ledger = ledger or Ledger()
    store = store or CassetteStore()
    budget = RunBudget(caps) if caps is not None else None
    if mode != "replay" and budget is None:
        raise ValueError("a live smoke run needs an approved run cap")
    client = LLMClient(
        mode, run_id, ledger=ledger, store=store, run_budget=budget, sdk_client=sdk, allow_dirty=True
    )
    models_api = list_models(mode, sdk, smoke_json)

    state = RunState()
    plan = plan_anthropic()
    with ThreadPoolExecutor(max_workers=len(plan)) as pool:
        for f in [pool.submit(_run_model, client, steps, state) for steps in plan.values()]:
            f.result()

    jc = jev.JevClient(
        mode, run_id, ledger=ledger, store=store, run_budget=budget, http=http, allow_dirty=True
    )
    jev_calls: list[JevCall] = []
    for pj in plan_jev():
        h = jev.jev_request_hash(pj.req)
        try:
            resp, replayed = jc.ask(pj.req)
            jev_calls.append(JevCall(h, pj.item_id, pj.language, resp, replayed))
        except (jev.JevError, BudgetExceeded) as e:
            jev_calls.append(JevCall(h, pj.item_id, pj.language, None, False, str(e)))

    position = {
        request_hash(s.req): (m, i) for m, steps in enumerate(plan.values()) for i, s in enumerate(steps)
    }
    state.calls.sort(key=lambda c: position[c.call.request_hash])  # threads finish out of order
    checks = analyse(state.calls, jev_calls)
    spend = {
        "run_anthropic": round(sum(c.call.cost_usd for c in state.calls if not c.call.replayed), 6),
        "run_openrouter": round(
            sum((j.response.cost_usd or 0.0) for j in jev_calls if j.response and not j.replayed), 8
        ),
        "ledger_remaining_anthropic": round(ledger.remaining("anthropic"), 6),
        "ledger_remaining_openrouter": round(ledger.remaining("openrouter"), 6),
    }
    notes = [f"ABORTED {a}" for a in state.aborted]
    report = SmokeReport(
        run_id=run_id,
        git_sha=runinfo.git_sha(),
        mode=mode,
        models_api=models_api,
        checks=checks,
        spend_usd=spend,
        notes=notes,
    )
    return report, state.calls, jev_calls


def write_run(report: SmokeReport, calls: list[SmokeCall], jev_calls: list[JevCall]) -> None:
    d = ROOT / "runs" / report.run_id
    d.mkdir(parents=True, exist_ok=True)
    with (d / "calls.jsonl").open("w", encoding="utf-8") as f:
        for c in calls:
            row = {"check": c.check, "tag": c.tag, "task": c.task, **c.call.model_dump(mode="json")}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (d / "jev.jsonl").open("w", encoding="utf-8") as f:
        for j in jev_calls:
            row = {
                "request_hash": j.request_hash,
                "item_id": j.item_id,
                "language": j.language,
                "replayed": j.replayed,
                "error": j.error,
                "response": j.response.model_dump(mode="json") if j.response else None,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    SMOKE_JSON.write_text(report.model_dump_json(indent=1), encoding="utf-8")


# --------------------------------------------------------------------------- analysis


def _mean(xs: list[float]) -> float | None:
    return round(statistics.fmean(xs), 1) if xs else None


def _pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(round(q * (len(s) - 1))))], 1)


def config_summary(calls: list[SmokeCall]) -> dict[str, Any]:
    ok = [c.call for c in calls if c.call.error is None]
    thinking = [c.thinking_tokens for c in ok if c.thinking_tokens is not None]
    lat = [c.latency_ms for c in ok]
    return {
        "n": len(calls),
        "errors": [c.call.error for c in calls if c.call.error],
        "parsed_ok": sum(c.call.parsed_ok for c in calls),
        "strict_json": sum(c.strict_json for c in calls),
        "fenced_json_only": sum(c.fenced_json and not c.strict_json for c in calls),
        "truncated_max_tokens": sum(c.stop_reason == "max_tokens" for c in ok),
        "refusals": sum(c.stop_reason == "refusal" for c in ok),
        "output_tokens_mean": _mean([c.output_tokens for c in ok]),
        "output_tokens_max": max((c.output_tokens for c in ok), default=None),
        "thinking_tokens_mean": _mean(thinking),
        "thinking_tokens_max": max(thinking, default=None),
        "thinking_reported": len(thinking),
        "latency_ms_mean": _mean(lat),
        "latency_ms_p50": _pct(lat, 0.5),
        "latency_ms_max": max(lat, default=None),
        "input_tokens_mean": _mean([c.input_tokens for c in ok]),
        "cache_creation_tokens_mean": _mean([c.cache_creation_tokens for c in ok]),
        "cache_read_tokens_mean": _mean([c.cache_read_tokens for c in ok]),
        "cost_usd": round(sum(c.cost_usd for c in ok), 6),
        "cost_usd_nocache": round(sum(c.cost_usd_nocache for c in ok), 6),
    }


def analyse(calls: list[SmokeCall], jev_calls: list[JevCall]) -> dict[str, Any]:
    pb = pricebook()
    by: dict[tuple[str, str], list[SmokeCall]] = {}
    for c in calls:
        by.setdefault((c.check, c.call.config_id), []).append(c)

    per_config = {cid: config_summary(cs) for (chk, cid), cs in by.items() if chk == "matrix"}
    check1 = {
        cid: {
            "pass": s["n"] == len(PROBE_ITEMS) and not s["errors"] and s["parsed_ok"] == s["n"],
            "parsed_ok": f"{s['parsed_ok']}/{s['n']}",
            "errors": s["errors"],
        }
        for cid, s in per_config.items()
    }
    check1_summary = {
        "configs_pass": sorted(c for c, v in check1.items() if v["pass"]),
        "configs_fail": sorted(c for c, v in check1.items() if not v["pass"]),
        "per_config": check1,
    }

    check2: dict[str, Any] = {}
    for model in MODELS:
        short = pb.price(model).short
        rows = {e: per_config.get(f"{short}-{e}", {}) for e in EFFORTS}
        lo, hi = rows["low"], rows["high"]
        out_ratio = (
            round(hi["output_tokens_mean"] / lo["output_tokens_mean"], 2)
            if lo.get("output_tokens_mean") and hi.get("output_tokens_mean")
            else None
        )
        lat_ratio = (
            round(hi["latency_ms_mean"] / lo["latency_ms_mean"], 2)
            if lo.get("latency_ms_mean") and hi.get("latency_ms_mean")
            else None
        )
        check2[model] = {
            "mean_output_tokens": {e: r.get("output_tokens_mean") for e, r in rows.items()},
            "mean_latency_ms": {e: r.get("latency_ms_mean") for e, r in rows.items()},
            "high_over_low_output": out_ratio,
            "high_over_low_latency": lat_ratio,
            "effort_changes_output_measurably": bool(out_ratio and out_ratio >= 1.2),
        }

    check3 = per_config

    check4: dict[str, Any] = {}
    for model in MODELS:
        model_calls = [c for c in calls if c.call.model == model and c.call.error is None]
        steps = []
        for chars in CACHE_PROBE_CHARS:
            pair = [c.call for c in model_calls if c.check == "cache_size" and c.tag == str(chars)]
            if len(pair) == 2:
                first, second = pair
                steps.append(
                    {
                        "prefix_chars": chars,
                        "prompt_tokens": first.input_tokens
                        + first.cache_creation_tokens
                        + first.cache_read_tokens,
                        "first_cache_creation": first.cache_creation_tokens,
                        "repeat_cache_read": second.cache_read_tokens,
                        "cached": second.cache_read_tokens > 0,
                    }
                )
        low = [c.call for c in model_calls if c.check == "matrix" and c.call.effort == "low"]
        full = None
        if low:
            full = {
                "prompt_tokens": low[0].input_tokens
                + low[0].cache_creation_tokens
                + low[0].cache_read_tokens,
                "first_cache_creation": low[0].cache_creation_tokens,
                "later_calls_cache_read": [c.cache_read_tokens for c in low[1:]],
                "cached": any(c.cache_read_tokens > 0 for c in low[1:]),
            }
        cached_sizes = [s["prompt_tokens"] for s in steps if s["cached"]]
        uncached_sizes = [s["prompt_tokens"] for s in steps if not s["cached"]]
        check4[model] = {
            "steps": steps,
            "full_static_prefix": full,
            "smallest_cached_prompt_tokens": min(cached_sizes, default=None),
            "largest_uncached_prompt_tokens": max(uncached_sizes, default=None),
        }

    check5: dict[str, Any] = {}
    for model in MODELS:
        firsts = {}
        for effort in EFFORTS:
            m = [
                c.call
                for c in calls
                if c.check == "matrix"
                and c.call.model == model
                and c.call.effort == effort
                and not c.call.error
            ]
            if m:
                firsts[effort] = {
                    "cache_read_tokens": m[0].cache_read_tokens,
                    "cache_creation_tokens": m[0].cache_creation_tokens,
                }
        shared = [firsts[e]["cache_read_tokens"] > 0 for e in ("medium", "high") if e in firsts]
        check5[model] = {
            "first_call_per_effort": firsts,
            "effort_change_invalidates_cache": (not any(shared)) if shared else None,
        }

    check6: dict[str, Any] = {}
    for model in MODELS:
        rows = []
        for item_id in THINKING_ITEMS:
            for effort in THINKING_EFFORTS:
                d = _find(calls, "matrix", model, effort, item_id)
                a = _find(calls, "thinking", model, effort, item_id)
                rows.append(
                    {
                        "item": item_id,
                        "effort": effort,
                        "omitted": _tok(d),
                        "adaptive": _tok(a),
                    }
                )
        omitted_thinking = [r["omitted"]["thinking_tokens"] for r in rows if r["omitted"]]
        omitted_out = {
            e: _mean([r["omitted"]["output_tokens"] for r in rows if r["effort"] == e and r["omitted"]])
            for e in THINKING_EFFORTS
        }
        adaptive_out = {
            e: _mean([r["adaptive"]["output_tokens"] for r in rows if r["effort"] == e and r["adaptive"]])
            for e in THINKING_EFFORTS
        }
        check6[model] = {
            "rows": rows,
            "thinking_on_when_omitted": (
                any((t or 0) > 0 for t in omitted_thinking)
                if any(t is not None for t in omitted_thinking)
                else None
            ),
            "mean_output_tokens_omitted": omitted_out,
            "mean_output_tokens_adaptive": adaptive_out,
            "adaptive_errors": [
                c.call.error
                for c in calls
                if c.check == "thinking" and c.call.model == model and c.call.error
            ],
        }

    return {
        "1_configs_parseable": check1_summary,
        "2_effort_effect": check2,
        "3_tokens_latency_per_config": check3,
        "4_min_cacheable_prefix": check4,
        "5_effort_vs_cache": check5,
        "6_thinking_vs_effort": check6,
        "7_jev": analyse_jev(jev_calls),
        "truncations": [
            {
                "check": c.check,
                "config": c.call.config_id,
                "item": c.call.ticket_id,
                "output_tokens": c.call.output_tokens,
            }
            for c in calls
            if c.call.stop_reason == "max_tokens"
        ],
        "max_tokens_used": {"matrix_and_thinking": SMOKE_MAX_TOKENS, "cache_size": PROBE_MAX_TOKENS},
    }


def _find(calls: list[SmokeCall], check: str, model: str, effort: str, item_id: str) -> ModelCall | None:
    for c in calls:
        m = c.call
        if c.check == check and m.model == model and m.effort == effort and m.ticket_id == item_id:
            return None if m.error else m
    return None


def _tok(c: ModelCall | None) -> dict[str, Any] | None:
    if c is None:
        return None
    return {
        "output_tokens": c.output_tokens,
        "thinking_tokens": c.thinking_tokens,
        "latency_ms": c.latency_ms,
        "parsed_ok": c.parsed_ok,
    }


def analyse_jev(jev_calls: list[JevCall]) -> dict[str, Any]:
    ok = [j for j in jev_calls if j.response is not None]
    lat = [j.response.latency_ms for j in ok]
    pairs = []
    for item in PROBE_ITEMS:
        en = next((j.response for j in ok if j.item_id == item.id and j.language == "en"), None)
        ar = next((j.response for j in ok if j.item_id == item.id and j.language == "ar"), None)
        if en is None or ar is None:
            pairs.append({"item": item.id, "complete": False})
            continue
        row: dict[str, Any] = {"item": item.id, "complete": True}
        for name in JEV_QUESTIONS_SPEC:
            ve, ce = jev.answer_value(en.answers[name])
            va, ca = jev.answer_value(ar.answers[name])
            row[name] = {"en": ve, "ar": va, "en_conf": ce, "ar_conf": ca}
        row["complexity_agree"] = row["complexity"]["en"] == row["complexity"]["ar"]
        row["max_noul_gap"] = round(
            max(abs(row[n]["en"] - row[n]["ar"]) for n in ("needs_calculation", "missing_information")), 3
        )
        pairs.append(row)
    complete = [p for p in pairs if p["complete"]]
    return {
        "endpoint": jev.DECISIONS_URL,
        "model_requested": jev.JEV_MODEL,
        "models_served": sorted({j.response.served_model for j in ok}),
        "schema_source": "https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request.md",
        "reachable": bool(ok),
        "calls_ok": f"{len(ok)}/{len(jev_calls)}",
        "errors": [j.error for j in jev_calls if j.error],
        "latency_ms": {
            "n": len(lat),
            "mean": _mean(lat),
            "p50": _pct(lat, 0.5),
            "p95": _pct(lat, 0.95),
            "max": max(lat, default=None),
            "first_call": lat[0] if lat else None,
        },
        "arabic": {
            "arabic_calls_ok": sum(1 for j in ok if j.language == "ar"),
            "complexity_agreement_en_ar": f"{sum(p['complexity_agree'] for p in complete)}/{len(complete)}",
            "max_noul_gap_en_ar": max((p["max_noul_gap"] for p in complete), default=None),
            "pairs": pairs,
        },
        "input_tokens_mean": _mean([j.response.input_tokens for j in ok]),
        "cost_usd_total": round(sum((j.response.cost_usd or 0.0) for j in ok), 8),
        "measured_from": "this machine (Hamzah to confirm location is Saudi Arabia)",
    }


def comparable(checks: dict[str, Any]) -> str:
    return json.dumps(checks, sort_keys=True, ensure_ascii=False, default=str)


SUMMARY_COLUMNS = (
    ("config", "{}"),
    ("json_ok", "{}"),
    ("out_mean", "{:.0f}"),
    ("out_max", "{}"),
    ("think_mean", "{:.0f}"),
    ("think_max", "{}"),
    ("lat_mean_ms", "{:,.0f}"),
    ("lat_p50_ms", "{:,.0f}"),
    ("cost_usd", "{:.6f}"),
    ("nocache_usd", "{:.6f}"),
)


def summary_rows(checks: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-config smoke summary. `nocache_usd` prices every prompt token at the base input rate (SPEC §7.5),
    removing the cache-write ordering effect (the first effort run per model paid the cache write)."""
    rows = []
    for cid, s in checks["3_tokens_latency_per_config"].items():
        rows.append(
            {
                "config": cid,
                "json_ok": f"{s['parsed_ok']}/{s['n']}",
                "out_mean": s["output_tokens_mean"],
                "out_max": s["output_tokens_max"],
                "think_mean": s["thinking_tokens_mean"],
                "think_max": s["thinking_tokens_max"],
                "lat_mean_ms": s["latency_ms_mean"],
                "lat_p50_ms": s["latency_ms_p50"],
                "cost_usd": s["cost_usd"],
                "nocache_usd": s["cost_usd_nocache"],
            }
        )
    return rows


def cheapest_effort_nocache(checks: dict[str, Any]) -> dict[str, str]:
    """Per model: the effort with the lowest no-cache cost over the smoke matrix."""
    out: dict[str, str] = {}
    per = checks["3_tokens_latency_per_config"]
    for short in sorted({cid.split("-")[0] for cid in per}):
        costs = {
            cid.split("-")[1]: per[cid]["cost_usd_nocache"] for cid in per if cid.startswith(short + "-")
        }
        out[short] = min(costs, key=costs.__getitem__)
    return out
