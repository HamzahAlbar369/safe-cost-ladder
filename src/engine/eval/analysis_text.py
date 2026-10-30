"""Plain-text rendering of the Phase 2 analysis and floors (what is shown to Hamzah at the gate)."""

from __future__ import annotations

from engine.eval.analysis import Analysis
from engine.eval.floors import Floors
from engine.eval.metrics import TASKS


def format_floors(floors: Floors) -> str:
    lines = [
        "Floors and latency budgets (SPEC 7.2; proposed, NOT frozen)",
        f"{'task':<11}{'n':>4}{'best config':>14}{'best acc':>10}{'tol':>6}{'floor':>8}{'budget cfg':>14}{'p95 s':>8}{'budget s':>10}",
    ]
    for t in TASKS:
        f = floors.per_task[t]
        lines.append(
            f"{t:<11}{f.n:>4}{f.best_config:>14}{f.best_accuracy:>10.3f}{f.tolerance:>6.2f}{f.floor:>8.3f}"
            f"{f.budget_config:>14}{f.p95_s:>8.2f}{f.budget_s:>10.1f}"
        )
    lines.append(
        "Configs tied for best accuracy (tie-break: lower Cost without caching (headline)) and their p95:"
    )
    for t in TASKS:
        tied = floors.per_task[t].tied_best
        lines.append(
            f"  {t:<11}"
            + ", ".join(f"{s.config} p95 {s.p95_s:.2f}s ${s.mean_cost_nocache:.4f}" for s in tied)
        )
    return "\n".join(lines)


def _ci(ci: tuple[float, float], scale: float = 1.0, fmt: str = ".4f") -> str:
    return f"[{ci[0] * scale:{fmt}}, {ci[1] * scale:{fmt}}]"


def format_analysis(a: Analysis) -> str:
    lines = [
        "Policies (dev; success = correct AND within the task latency budget; CPST = cost per successful task)"
    ]
    for r in a.rows:
        s = r.summary
        gap = f"{r.gap_captured:.0%}" if r.gap_captured is not None else "-"
        floors_ok = "yes" if r.meets_floors else "NO"
        lines += [
            f"{r.name}",
            f"    accuracy {s['accuracy']:.3f}  success {s['success_rate']:.3f}  p50 {s['p50_s']:.2f}s  p95 {s['p95_s']:.2f}s"
            f"  oracle gap captured {gap}  meets every floor: {floors_ok}",
            f"    CPST, Cost without caching (headline): ${s['cpst_nocache']:.5f} {_ci(r.cpst_nocache_ci, fmt='.5f')}"
            f"   total ${s['usd_nocache']:.2f}",
            f"    CPST, Cost with caching (actual):      ${s['cpst_cached']:.5f} {_ci(r.cpst_cached_ci, fmt='.5f')}"
            f"   total ${s['usd_cached']:.2f}",
            f"    CPST change vs B1 (headline): {r.gain_vs_b1_nocache:+.1%} {_ci(r.gain_vs_b1_ci, 100, '+.1f')}%",
        ]
    lines += ["", "Per task accuracy / success / CPST (headline) / p95 s"]
    for name, per in a.per_task.items():
        lines.append(name)
        for t in TASKS:
            s = per[t]
            lines.append(
                f"    {t:<11} n={s['n']:<4.0f} acc {s['accuracy']:.3f}  success {s['success_rate']:.3f}"
                f"  CPST ${s['cpst_nocache']:.5f}  p95 {s['p95_s']:.2f}s"
            )
    lines += ["", "Per language accuracy / success"]
    for name, per in a.per_language.items():
        lines.append(
            f"{name}: "
            + "; ".join(
                f"{lg} acc {s['accuracy']:.3f} success {s['success_rate']:.3f} (n={s['n']:.0f})"
                for lg, s in per.items()
            )
        )
    lines += [
        "",
        "Pareto ladder per task (dominated configs removed; cost = mean Cost without caching (headline))",
    ]
    for t in TASKS:
        rungs = " -> ".join(
            f"{r.config} (acc {r.accuracy:.3f}, ${r.mean_cost_nocache:.4f}, p95 {r.p95_s:.1f}s)"
            for r in a.ladders[t]
        )
        lines.append(f"  {t:<11}{rungs}")
        lines.append(f"  {'':<11}dominated: {', '.join(a.dominated[t]) or 'none'}")
    lines += ["", "Oracle choice counts per task (tickets sent to each config)"]
    for t in TASKS:
        lines.append(f"  {t:<11}{a.oracle_choice_counts[t]}")
    h = a.headroom
    lines += [
        "",
        "Router go/no-go headroom (SPEC 7.7; upper bound; B1-B5 policies that meet every floor)",
        f"  best non-router policy: {h['best_non_router']} (CPST ${h['best_non_router_cpst_nocache']:.5f})",
        f"  oracle CPST ${h['oracle_cpst_nocache']:.5f}; headroom {h['headroom_cpst']:.1%} vs the {h['threshold']:.0%} keep threshold"
        f" -> {'GO' if h['go'] else 'NO-GO'}",
    ]
    return "\n".join(lines)
