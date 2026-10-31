"""Every number in reports/report.html, its figures and the demo: ONE metrics JSON (reports/metrics.json).

Sources (all committed): dev and shifted by replay of their matrices with the frozen dev choices; held-out ONLY
from `runs/heldout-outcomes-freeze-v1/` (exported once at freeze-v1 with the frozen code, D5.2) and the O1 live
run's outcomes and calls. `heldout.jsonl` is never read here. Two values come from generated text reports
(router AUCs and ceiling, name-collision counts); they are parsed strictly and their source file is recorded.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from engine import runinfo
from engine.eval import bootstrap as B
from engine.eval.baselines import Outcome, summarize
from engine.eval.metrics import TASKS, mean, percentile
from engine.llm.pricing import ROOT
from engine.policy.cascade import Trace

DEV_RUN, SHIFTED_RUN = "matrix-dev-full-1", "matrix-shifted-full-1"
HELDOUT_EXPORT = "heldout-outcomes-freeze-v1"
HELDOUT_MATRIX, HELDOUT_LIVE = "matrix-heldout-freeze-v1", "o1-live-heldout-freeze-v1"
OUT = ROOT / "reports" / "metrics.json"
LANGS = ("en", "ar")
FIRST, SECOND, TOP = "haiku-low", "haiku-medium", "opus-low"


def _runs(name: str) -> Path:
    return ROOT / "runs" / name


def _read_outcomes(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]


def _key(name: str) -> str:
    """'B1: always-best (opus-low)' -> 'B1'; 'O1 (frozen...)' -> 'O1'; 'Oracle...' -> 'Oracle'."""
    if name.startswith("Oracle"):
        return "Oracle"
    return name.split(":")[0].split(" ")[0]


# --- statistics ------------------------------------------------------------------------------------


def _arr(outs: list[Outcome], key: str) -> tuple[list[float], list[float]]:
    return [getattr(o, key) for o in outs], [float(o.success) for o in outs]


def _finite(x: float) -> float | None:
    return None if x == float("inf") else x


def stats(outs: list[Outcome], ref: list[Outcome] | None, floors: dict, *, ci: bool = True) -> dict:
    """acc / success / p95 / CPST (both bases) with 95% bootstrap CIs, and the paired saving vs `ref` (B1)."""
    s = summarize(outs)
    d: dict = {
        "n": len(outs),
        "correct": sum(o.correct for o in outs),
        "successes": sum(o.success for o in outs),
        "acc": s["accuracy"],
        "success": s["success_rate"],
        "p50_s": s["p50_s"],
        "p95_s": s["p95_s"],
        "usd_nocache": s["usd_nocache"],
        "usd_cached": s["usd_cached"],
        "cpst_nocache": _finite(s["cpst_nocache"]),
        "cpst_cached": _finite(s["cpst_cached"]),
    }
    if not ci:
        return d
    samples = B.resample_indices(len(outs))
    d["acc_lo"], d["acc_hi"] = B.mean_ci([float(o.correct) for o in outs], samples)
    for base, key in (("nocache", "cost_nocache"), ("cached", "cost_cached")):
        if d[f"cpst_{base}"] is None:
            continue
        d[f"cpst_{base}_lo"], d[f"cpst_{base}_hi"] = B.cpst_ci(*_arr(outs, key), samples)
        if ref is not None:
            r = summarize(ref)[f"cpst_{base}"]
            d[f"saving_{base}"] = (r - d[f"cpst_{base}"]) / r
            d[f"saving_{base}_lo"], d[f"saving_{base}_hi"] = B.paired_diff_ci(
                _arr(ref, key), _arr(outs, key), samples, relative=True
            )
    return d


def per_task(outs: list[Outcome], floors: dict) -> dict:
    out = {}
    for t in TASKS:
        sub = [o for o in outs if o.task == t]
        s = summarize(sub)
        out[t] = {
            "n": len(sub),
            "correct": sum(o.correct for o in sub),
            "acc": s["accuracy"],
            "success": s["success_rate"],
            "p95_s": s["p95_s"],
            "cpst_nocache": _finite(s["cpst_nocache"]),
            "cpst_cached": _finite(s["cpst_cached"]),
            "usd_nocache": s["usd_nocache"],
            "usd_cached": s["usd_cached"],
            "floor": floors[t]["floor"],
            "budget_s": floors[t]["budget_s"],
            "meets_floor": s["accuracy"] >= floors[t]["floor"],
        }
    return out


def breakdown(outs: list[Outcome], ref: list[Outcome], floors: dict) -> dict:
    """SPEC §7.5 per task and per language, with CIs (subset bootstrap, saving vs B1 paired)."""
    ref_by = {o.ticket_id: o for o in ref}
    groups = {f"task_{t}": [o for o in outs if o.task == t] for t in TASKS}
    groups |= {f"lang_{lg}": [o for o in outs if o.language == lg] for lg in LANGS}
    return {k: stats(v, [ref_by[o.ticket_id] for o in v], floors) for k, v in groups.items()}


def meets_all(outs: list[Outcome], floors: dict) -> bool:
    return all(summarize([o for o in outs if o.task == t])["accuracy"] >= floors[t]["floor"] for t in TASKS)


def policy_entry(outs: list[Outcome], b1: list[Outcome], floors: dict, *, detail: bool) -> dict:
    e = stats(outs, None if outs is b1 else b1, floors)
    e["meets_floors"] = meets_all(outs, floors)
    e["per_task"] = per_task(outs, floors)
    if detail:
        e["breakdown"] = breakdown(outs, b1, floors)
    return e


def oracle_gap(b1: dict, pol: dict, orc: dict) -> dict:
    return {
        base: (b1[f"cpst_{base}"] - pol[f"cpst_{base}"]) / (b1[f"cpst_{base}"] - orc[f"cpst_{base}"])
        for base in ("nocache", "cached")
    }


def verifier_correlation(outs: list[Outcome], traces: list[Trace], first_correct: dict[str, bool]) -> dict:
    """On adjudicate: wrong haiku-low answers, and how many O1 still accepted. 'Agreed wrong' = accepted with
    the second opinion in time, i.e. both Haikus passed the checks and gave the same wrong answer."""
    tr = {t.ticket_id: t for t in traces}
    adj = [o for o in outs if o.task == "adjudicate"]
    wrong_first = [o for o in adj if not first_correct[o.ticket_id]]
    accepted_wrong = [o for o in adj if not tr[o.ticket_id].escalated and not o.correct]
    agreed = [o for o in accepted_wrong if not tr[o.ticket_id].second_late]
    return {
        "adjudicate_n": len(adj),
        "first_wrong": len(wrong_first),
        "accepted_wrong": len(accepted_wrong),
        "agreed_wrong": len(agreed),
        "escalated": sum(tr[o.ticket_id].escalated for o in adj),
    }


# --- splits ----------------------------------------------------------------------------------------


def floors_dict(fc) -> dict:
    return {
        t: {"floor": fc.floors.per_task[t].floor, "budget_s": fc.floors.per_task[t].budget_s} for t in TASKS
    }


def replay_split(run_id: str, split: str, fc) -> tuple[dict, object]:
    from engine.eval.phase4_report import SplitContext

    ctx = SplitContext(run_id, split, fc=fc)
    floors = floors_dict(fc)
    o1, traces = ctx.o1()
    pols = {_key(k): v for k, v in ctx.baselines.items()} | {"O1": o1, "Oracle": ctx.oracle}
    b1 = pols["B1"]
    entries = {k: policy_entry(v, b1, floors, detail=k == "O1") for k, v in pols.items()}
    first = {t.id: ctx.index[(t.id, FIRST)].correct for t in ctx.tickets}
    d = {
        "n": len(ctx.tickets),
        "run": run_id,
        "policies": entries,
        "oracle_gap": oracle_gap(entries["B1"], entries["O1"], entries["Oracle"]),
        "verifier": verifier_correlation(o1, traces, first),
        "haiku_suffices": _haiku_suffices(ctx.oracle),
    }
    return d, (ctx, o1, traces)


def _haiku_suffices(orc: list[Outcome]) -> float:
    """Share of tickets whose oracle (cheapest correct config within budget) is a Haiku config."""
    return mean(o.path[0].startswith("haiku") and o.success for o in orc)


def heldout(fc) -> dict:
    floors = floors_dict(fc)
    ex = _runs(HELDOUT_EXPORT)
    rows = _read_outcomes(ex / "outcomes.jsonl")
    pols: dict[str, list[Outcome]] = {}
    for r in rows:
        name = r.pop("policy")
        pols.setdefault(_key(name), []).append(Outcome.model_validate(r))
    for k in pols:
        pols[k].sort(key=lambda o: o.ticket_id)
    live = sorted(
        (Outcome.model_validate(r) for r in _read_outcomes(_runs(HELDOUT_LIVE) / "outcomes.jsonl")),
        key=lambda o: o.ticket_id,
    )
    assert [o.ticket_id for o in live] == [o.ticket_id for o in pols["B1"]], "live and matrix tickets differ"
    pols["O1_live"] = live
    b1 = pols["B1"]
    entries = {k: policy_entry(v, b1, floors, detail=k in ("O1", "O1_live")) for k, v in pols.items()}
    traces = [Trace.model_validate_json(x) for x in (ex / "o1_traces.jsonl").read_text("utf-8").splitlines()]
    cells = _read_outcomes(ex / "cells.jsonl")
    first = {c["ticket_id"]: c["correct"] for c in cells if c["config_id"] == FIRST}
    sim = {o.ticket_id: o for o in pols["O1"]}
    gap = {
        "same_correct": sum(sim[o.ticket_id].correct == o.correct for o in live),
        "same_path": sum(tuple(sim[o.ticket_id].path) == tuple(o.path) for o in live),
        "n": len(live),
    }
    return {
        "n": len(b1),
        "run": f"{HELDOUT_MATRIX} + {HELDOUT_LIVE}",
        "policies": entries,
        "oracle_gap": oracle_gap(entries["B1"], entries["O1"], entries["Oracle"]),
        "oracle_gap_live": oracle_gap(entries["B1"], entries["O1_live"], entries["Oracle"]),
        "verifier": verifier_correlation(pols["O1"], traces, first),
        "sim_vs_live": gap,
        "haiku_suffices": _haiku_suffices(pols["Oracle"]),
        "sankey": sankey(live, floors),
        "spend_by_task": spend_by_task(b1, live),
        "cells": _heatmap(cells),
    }


def sankey(live: list[Outcome], floors: dict) -> dict:
    """Held-out adjudicate, O1 live: where each ticket ended and how. Rung cost = mean headline cost per call of
    that config in the live run (answers and second opinions)."""
    adj = [o for o in live if o.task == "adjudicate"]

    def fate(o: Outcome) -> str:
        return "wrong" if not o.correct else ("in_budget" if o.success else "over_budget")

    acc = Counter(fate(o) for o in adj if TOP not in o.path)
    esc = Counter(fate(o) for o in adj if TOP in o.path)
    calls = [json.loads(x) for x in (_runs(HELDOUT_LIVE) / "calls.jsonl").read_text("utf-8").splitlines()]
    calls = [c for c in calls if c["role"] in ("answer", "verify")]
    adj_ids = {o.ticket_id for o in adj}
    rung = {
        cfg: mean(c["cost_usd_nocache"] for c in calls if c["config_id"] == cfg and c["ticket_id"] in adj_ids)
        for cfg in (FIRST, SECOND, TOP)
        if any(c["config_id"] == cfg and c["ticket_id"] in adj_ids for c in calls)
    }
    fates = ("in_budget", "over_budget", "wrong")
    return {
        "n": len(adj),
        "accepted": sum(acc.values()),
        "escalated": sum(esc.values()),
        "accepted_fate": {f: acc.get(f, 0) for f in fates},
        "escalated_fate": {f: esc.get(f, 0) for f in fates},
        "rung_cost_nocache": rung,
        "budget_s": floors["adjudicate"]["budget_s"],
    }


def spend_by_task(b1: list[Outcome], live: list[Outcome]) -> dict:
    out = {}
    for t in TASKS:
        out[t] = {
            name: {
                "nocache": sum(o.cost_nocache for o in outs if o.task == t),
                "cached": sum(o.cost_cached for o in outs if o.task == t),
            }
            for name, outs in (("B1", b1), ("O1_live", live))
        }
    out["total"] = {
        name: {"nocache": sum(o.cost_nocache for o in outs), "cached": sum(o.cost_cached for o in outs)}
        for name, outs in (("B1", b1), ("O1_live", live))
    }
    return out


def _heatmap(cells: list[dict]) -> dict:
    """Held-out config x task accuracy and mean headline cost per call (stretch heatmap)."""
    out: dict = {}
    for cfg in sorted({c["config_id"] for c in cells}):
        out[cfg] = {}
        for t in TASKS:
            sub = [c for c in cells if c["config_id"] == cfg and c["task"] == t]
            out[cfg][t] = {
                "acc": mean(c["correct"] for c in sub),
                "cost_nocache": mean(c["cost_usd_nocache"] for c in sub),
            }
    return out


# --- dev-only evidence -----------------------------------------------------------------------------


def effort(ctx) -> dict:
    ids = [t.id for t in ctx.tickets]
    out: dict = {}
    for model in ("haiku", "sonnet", "opus"):
        cells = {e: [ctx.index[(i, f"{model}-{e}")] for i in ids] for e in ("low", "medium", "high")}
        low_cost = mean(c.cost_usd for c in cells["low"])
        low_acc = [float(c.correct) for c in cells["low"]]
        out[model] = {}
        for e, cs in cells.items():
            row = {
                "acc": mean(c.correct for c in cs),
                "cost_cached": mean(c.cost_usd for c in cs),
                "cost_nocache": mean(c.cost_usd_nocache for c in cs),
                "x_low": mean(c.cost_usd for c in cs) / low_cost,
                "out_tokens": mean(c.output_tokens for c in cs),
                "think_tokens": mean(c.thinking_tokens or 0 for c in cs),
                "p95_s": percentile([c.latency_ms for c in cs], 95) / 1000,
            }
            if e != "low":
                row["acc_delta"] = row["acc"] - mean(low_acc)
                row["acc_delta_lo"], row["acc_delta_hi"] = B.paired_mean_diff_ci(
                    [float(c.correct) for c in cs], low_acc, ctx.samples
                )
            out[model][e] = row
    return out


def demo_set(ctx, o1: list[Outcome], traces: list[Trace]) -> dict[str, str]:
    """The demo / receipt tickets, by a declared rule on dev (no hand-picking): per task, the first dev ticket by
    id that O1 answers successfully; for adjudicate, the first ARABIC ticket accepted at the Haiku pair with the
    second opinion in time; plus the first adjudicate ticket O1 escalates and still answers successfully."""
    by = {o.ticket_id: o for o in o1}
    tr = {t.ticket_id: t for t in traces}
    lang = {t.id: t.language for t in ctx.tickets}
    ids = sorted(by)
    pick = {}
    for t in ("faq", "intent", "extract"):
        pick[t] = next(i for i in ids if by[i].task == t and by[i].success)
    pick["adjudicate"] = next(
        i
        for i in ids
        if by[i].task == "adjudicate"
        and lang[i] == "ar"
        and by[i].success
        and not tr[i].escalated
        and not tr[i].second_late
    )
    pick["escalated"] = next(
        i for i in ids if by[i].task == "adjudicate" and tr[i].escalated and by[i].success
    )
    return pick


def receipt(ctx, ticket_id: str, o1: list[Outcome], b1: list[Outcome]) -> dict:
    """Two itemised receipts for one dev ticket: B1 (one opus-low call) vs O1 (its actual path)."""
    by_o1 = {o.ticket_id: o for o in o1}[ticket_id]
    by_b1 = {o.ticket_id: o for o in b1}[ticket_id]

    def line(cfg: str, role: str) -> dict:
        c = ctx.index[(ticket_id, cfg)]
        return {
            "config": cfg,
            "role": role,
            "input_tokens": c.input_tokens + c.cache_read_tokens + c.cache_creation_tokens,
            "output_tokens": c.output_tokens,
            "usd_nocache": c.cost_usd_nocache,
            "usd_cached": c.cost_usd,
            "latency_s": c.latency_ms / 1000,
            "checks_pass": c.verified,
            "correct": c.correct,
        }

    roles = {FIRST: "answer", SECOND: "second opinion (parallel)", TOP: "escalation"}
    t = next(x for x in ctx.tickets if x.id == ticket_id)
    return {
        "ticket_id": ticket_id,
        "task": t.task_type,
        "language": t.language,
        "budget_s": ctx.floors.per_task[t.task_type].budget_s,
        "B1": {
            "lines": [line(by_b1.path[0], "answer")],
            "usd_nocache": by_b1.cost_nocache,
            "usd_cached": by_b1.cost_cached,
            "latency_s": by_b1.latency_ms / 1000,
            "correct": by_b1.correct,
            "success": by_b1.success,
        },
        "O1": {
            "lines": [line(cfg, roles.get(cfg, "answer")) for cfg in by_o1.path],
            "usd_nocache": by_o1.cost_nocache,
            "usd_cached": by_o1.cost_cached,
            "latency_s": by_o1.latency_ms / 1000,
            "correct": by_o1.correct,
            "success": by_o1.success,
        },
    }


def problem(ctx) -> dict:
    """Why always-best wastes money (dev): per-call cost and accuracy of the cheapest vs the best config."""
    ids = [t.id for t in ctx.tickets]

    def per(cfg: str) -> dict:
        cs = [ctx.index[(i, cfg)] for i in ids]
        return {"acc": mean(c.correct for c in cs), "cost_nocache": mean(c.cost_usd_nocache for c in cs)}

    lo, hi = per(FIRST), per(TOP)
    return {"cheap": lo, "best": hi, "cost_ratio": hi["cost_nocache"] / lo["cost_nocache"]}


def ablations(ctx) -> dict:
    from engine.eval.phase3_report import ablation_rows

    o1, _ = ctx.o1()
    floors = floors_dict(ctx.fc)
    out = {}
    for name, outs in ablation_rows(ctx):
        e = stats(outs, o1, floors)
        out[name] = {
            "cpst_nocache": e["cpst_nocache"],
            "saving_vs_o1": e.get("saving_nocache"),
            "saving_vs_o1_lo": e.get("saving_nocache_lo"),
            "saving_vs_o1_hi": e.get("saving_nocache_hi"),
            "adjudicate_correct": sum(o.correct for o in outs if o.task == "adjudicate"),
            "meets_floors": meets_all(outs, floors),
        }
    return out


# --- shifted-only evidence -------------------------------------------------------------------------


def shifted_extras(ctx, o1: list[Outcome], fc) -> dict:
    from engine.eval import recalibrate as R

    floors = floors_dict(fc)
    _, scored = R.cross_fold(fc, ctx.tickets, ctx.index)
    ids = [t.id for t in ctx.tickets]
    pooled = {k: [v[i] for i in ids] for k, v in scored.items()}
    b1 = pooled["B1"]
    analysis = {
        "failsafe": policy_entry(pooled["fail-safe"], b1, floors, detail=False),
        "recalibrated": policy_entry(pooled["recalibrated"], b1, floors, detail=False),
        "frozen": policy_entry(pooled["frozen O1"], b1, floors, detail=False),
    }
    source = {"failsafe": "fail-safe", "recalibrated": "recalibrated", "frozen": "frozen O1"}
    for k, src in source.items():
        analysis[k]["per_task_ci"] = {
            t: stats([o for o in pooled[src] if o.task == t], None, floors) for t in TASKS
        }
    scen: dict = {}
    by = {o.ticket_id: o for o in o1}
    for sc in ("normal", "adversarial", "policy_change"):
        sub = [by[t.id] for t in ctx.tickets if t.meta.scenario == sc]
        scen[sc] = {
            "n": len(sub),
            "correct": sum(o.correct for o in sub),
            "acc": summarize(sub)["accuracy"],
            "per_task": {
                t: {"n": sum(o.task == t for o in sub), "correct": sum(o.correct for o in sub if o.task == t)}
                for t in TASKS
                if any(o.task == t for o in sub)
            },
        }
    top_wrong = sum(
        not ctx.index[(t.id, "opus-high")].correct for t in ctx.tickets if t.task_type == "adjudicate"
    )
    best_adj = max(
        mean(ctx.index[(t.id, c)].correct for t in ctx.tickets if t.task_type == "adjudicate")
        for c in {cfg for _, cfg in ctx.index}
    )
    return {
        "analysis": analysis,
        "scenario": scen,
        "opus_high_adjudicate_wrong": top_wrong,
        "best_single_adjudicate_acc": best_adj,
    }


def monitor(fc, dev_ctx, shifted_ctx) -> list[dict]:
    from engine.eval.recalibrate import detection_rates

    rows = detection_rates(
        fc, {"shifted": (shifted_ctx.tickets, shifted_ctx.index), "dev": (dev_ctx.tickets, dev_ctx.index)}
    )
    return [r.model_dump() for r in rows]


def scenarios(fc, ctxs: dict) -> dict:
    from engine.eval.scenarios import PRESETS, evaluate

    dev_cells = ctxs["dev"].cells
    out: dict = {}
    for split, ctx in ctxs.items():
        out[split] = []
        for sc in PRESETS:
            r = evaluate(fc, dev_cells, ctx.cells, ctx.tickets, sc)
            fl = {t: {"floor": r.adapted.floors.per_task[t].floor, "budget_s": 0.0} for t in TASKS}
            e = stats(r.o1, r.b1, fl)
            out[split].append(
                {
                    "name": sc.name,
                    "picks": {**r.adapted.static, "adjudicate_cascade": r.adapted.o1 is not None},
                    "cpst_nocache": e["cpst_nocache"],
                    "cpst_cached": e["cpst_cached"],
                    "b1_cpst_nocache": _finite(summarize(r.b1)["cpst_nocache"]),
                    "saving_nocache": e["saving_nocache"],
                    "saving_nocache_lo": e["saving_nocache_lo"],
                    "saving_nocache_hi": e["saving_nocache_hi"],
                    "acc": e["acc"],
                    "success": e["success"],
                    "meets_floors": meets_all(r.o1, fl),
                }
            )
    return out


# --- parsed from generated reports (strict) -------------------------------------------------------


def _grab(path: Path, pattern: str) -> str:
    m = re.search(pattern, path.read_text("utf-8"))
    if not m:
        raise ValueError(f"{path.name}: pattern not found: {pattern}")
    return m.group(1)


def routers() -> dict:
    loc, jev = ROOT / "reports/phase3/router_local.txt", ROOT / "reports/phase3/router_jev.txt"
    auc = r"ROC AUC on dev \(local: out-of-fold; Jev: zero-shot\) ([0-9.]+)"
    ceil = r"Ceiling: a PERFECT router .*?\(([+-][0-9.]+)%\), p95 ([0-9.]+)s vs ([0-9.]+)s"
    m = re.search(ceil, loc.read_text("utf-8"))
    if not m:
        raise ValueError("router ceiling line not found")
    return {
        "local_auc": float(_grab(loc, auc)),
        "jev_auc": float(_grab(jev, auc)),
        "ceiling_cpst_gain": float(m.group(1)) / 100,
        "ceiling_p95_s": float(m.group(2)),
        "o1_p95_s": float(m.group(3)),
        "bar_cpst": 0.05,
        "bar_p95": 0.20,
        "source": "reports/phase3/router_local.txt, reports/phase3/router_jev.txt",
    }


def name_collisions() -> dict:
    p = ROOT / "reports/phase2/name_collisions.txt"
    text = p.read_text("utf-8")
    m = re.search(r"^opus\s+(\d+)\s+([0-9.]+)\s+(\d+)\s+([0-9.]+)\s*$", text, re.M)
    if not m:
        raise ValueError("name_collisions.txt: opus row not found")
    return {
        "dev_visible": int(_grab(p, r"dev tickets with a visible clash \((\d+)\)")),
        "shifted_visible": int(_grab(p, r"shifted tickets with a visible clash \((\d+)\)")),
        "opus_clash_acc": float(m.group(2)),
        "opus_other_acc": float(m.group(4)),
        "source": "reports/phase2/name_collisions.txt",
    }


# --- provenance ------------------------------------------------------------------------------------


def provenance() -> dict:
    def man(run: str) -> dict:
        d = json.loads((_runs(run) / "manifest.json").read_text("utf-8"))
        return d.get("manifest", d)

    ex = json.loads((_runs(HELDOUT_EXPORT) / "manifest.json").read_text("utf-8"))
    return {
        "build_git_sha": runinfo.git_sha(),
        "runs": {
            "dev": DEV_RUN,
            "shifted": SHIFTED_RUN,
            "heldout_matrix": HELDOUT_MATRIX,
            "heldout_live": HELDOUT_LIVE,
            "heldout_export": HELDOUT_EXPORT,
        },
        "config_hash": {
            "dev": man(DEV_RUN)["config_hash"],
            "shifted": man(SHIFTED_RUN)["config_hash"],
            "heldout": man(HELDOUT_MATRIX)["config_hash"],
        },
        "heldout_tag": ex["tag"],
        "heldout_git_sha": ex["git_sha"],
        "bootstrap": {"resamples": B.RESAMPLES, "seed": B.SEED},
    }


def collect(progress=print) -> dict:
    from engine.policy.frozen import frozen_choices

    fc = frozen_choices()
    progress("dev ...")
    dev, (dctx, do1, dtr) = replay_split(DEV_RUN, "dev", fc)
    progress("shifted ...")
    shifted, (sctx, so1, _) = replay_split(SHIFTED_RUN, "shifted", fc)
    progress("held-out (export + live) ...")
    held = heldout(fc)
    progress("shifted analysis, monitor, scenarios ...")
    shifted |= shifted_extras(sctx, so1, fc)
    demo = demo_set(dctx, do1, dtr)
    m = {
        "provenance": provenance(),
        "floors": floors_dict(fc),
        "o1_config": {
            **fc.static,
            "first": fc.o1.first,
            "second": fc.o1.second,
            "top": fc.o1.top,
            "deadline_s": fc.o1.deadline_s,
            "b1": fc.b1,
        },
        "splits": {"dev": dev, "shifted": shifted, "heldout": held},
        "effort": effort(dctx),
        "problem": problem(dctx),
        "ablations": ablations(dctx),
        "demo": demo,
        "receipt": receipt(dctx, demo["adjudicate"], do1, _b1(dctx)),
        "monitor": monitor(fc, dctx, sctx),
        "scenarios": scenarios(fc, {"dev": dctx, "shifted": sctx}),
        "routers": routers(),
        "names": name_collisions(),
    }
    return m


def _b1(ctx) -> list[Outcome]:
    return next(v for k, v in ctx.baselines.items() if k.startswith("B1"))


def write(m: dict, path: Path = OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(m, indent=1, sort_keys=True, default=_jsonable) + "\n", encoding="utf-8")
    return path


def _jsonable(x):
    if isinstance(x, tuple | set | frozenset):
        return list(x)
    raise TypeError(type(x))


def load(path: Path = OUT) -> dict:
    return json.loads(path.read_text("utf-8"))


def lookup(m: dict, key: str):
    """'splits.heldout.policies.O1.cpst_nocache' -> value (KeyError if missing)."""
    cur = m
    for part in key.split("."):
        cur = cur[int(part)] if isinstance(cur, list) else cur[part]
    return cur
