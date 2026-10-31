"""Phase 4 evidence under reports/phase4/: the FROZEN policy scored on the shifted split by replay (SPEC §8).

Every choice comes from dev (`policy.frozen`): floors and budgets from config/policy.yaml, static per-task
configs and the B1 / B4 configs picked on the dev matrix, O1 options as approved in Phase 3. Shifted results
are only measured, never tuned on. No API calls. Every file starts with its provenance line.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from engine import runinfo
from engine.contracts import Ticket
from engine.eval import bootstrap as B
from engine.eval.baselines import CellIndex, Outcome, index_cells, oracle, run_policy, summarize
from engine.eval.cells import build_cells
from engine.eval.data import load_split
from engine.eval.matrix import config_hash, split_versions
from engine.eval.metrics import TASKS
from engine.eval.phase3_report import (
    ABLATIONS,
    CAVEATS,
    O1_DEFAULT,
    _arr,
    _meets,
    ablations_report,
    misses,
    oracle_gap,
    per_task_lines,
    policy_block,
    v3_coverage,
    v3_quality,
)
from engine.llm.pricing import ROOT
from engine.policy.cascade import O1Options, Trace, run_o1
from engine.policy.controller import load_policy
from engine.policy.frozen import FrozenChoices, frozen_baselines, frozen_choices
from engine.tier0 import Tier0

OUT = ROOT / "reports" / "phase4"
SHIFTED_RUN = "matrix-shifted-full-1"
SCENARIOS = ("normal", "adversarial", "policy_change")


class SplitContext:
    """A recorded split scored with the frozen dev choices. Duck-types the Phase 3 `Context`, so the Phase 3
    report blocks (policy_block, per_task_lines, v3_*, misses, ablations) run unchanged on it."""

    def __init__(
        self, run_id: str, split: str, fc: FrozenChoices | None = None, tickets: list[Ticket] | None = None
    ):
        self.run_id, self.split = run_id, split
        self.fc = fc or frozen_choices()
        self.tickets = sorted(tickets if tickets is not None else load_split(split), key=lambda t: t.id)
        cells, problems = build_cells([run_id], self.tickets)
        if problems:
            raise RuntimeError(f"{len(problems)} cells without a response, e.g. {problems[0]}")
        self.cells = cells
        self.index: CellIndex = index_cells(cells)
        self.policy = load_policy()
        self.floors = self.fc.floors  # frozen (dev), never re-derived on this split
        self.static = self.fc.static
        self.samples = B.resample_indices(len(self.tickets))
        self.baselines = {
            name: run_policy(ch, self.tickets, self.index, self.floors)
            for name, ch in frozen_baselines(self.fc, self.index).items()
        }
        self.b1 = next(v for k, v in self.baselines.items() if k.startswith("B1"))
        self.b3 = next(v for k, v in self.baselines.items() if k.startswith("B3"))
        self.oracle = run_policy(oracle(self.index, self.floors), self.tickets, self.index, self.floors)

    def o1(self, o: O1Options = O1_DEFAULT) -> tuple[list[Outcome], list[Trace]]:
        return run_o1(self.tickets, self.index, self.floors, self.static, o)


def _sel(outs: list[Outcome], ids: set[str]) -> list[Outcome]:
    return [o for o in outs if o.ticket_id in ids]


def cpst_lines(label: str, outs: list[Outcome], ref: list[Outcome]) -> list[str]:
    """CPST (both cost bases) with a bootstrap CI over this subset, and the paired saving vs `ref` (B1)."""
    samples = B.resample_indices(len(outs))
    s, r = summarize(outs), summarize(ref)
    lines = [f"    {label:<22} n={len(outs):>3}  acc {s['accuracy']:.3f}  success {s['success_rate']:.3f}"]
    for key, field, name in (
        ("cost_nocache", "cpst_nocache", "headline"),
        ("cost_cached", "cpst_cached", "with caching"),
    ):
        lo, hi = B.cpst_ci(*_arr(outs, key), samples)
        if r[field] == float("inf") or s[field] == float("inf"):
            lines.append(f"        CPST {name:<13} ${s[field]:.5f}")
            continue
        slo, shi = B.paired_diff_ci(_arr(ref, key), _arr(outs, key), samples, relative=True)
        saving = (r[field] - s[field]) / r[field]
        lines.append(
            f"        CPST {name:<13} ${s[field]:.5f} [{lo:.5f}, {hi:.5f}]  "
            f"saving vs B1 {saving:+.1%} [{slo:+.1%}, {shi:+.1%}]"
        )
    return lines


def breakdown(name: str, outs: list[Outcome], ctx: SplitContext) -> list[str]:
    """SPEC §7.5: overall, per task and per language, CPST with 95% bootstrap CIs and the saving vs B1."""
    lines = [f"{name}: CPST by subset (CI = 95% bootstrap over the subset's tickets; saving vs B1 paired)"]
    b1 = {o.ticket_id: o for o in ctx.b1}
    groups: list[tuple[str, set[str]]] = [("overall", {t.id for t in ctx.tickets})]
    groups += [(f"task {t}", {x.id for x in ctx.tickets if x.task_type == t}) for t in TASKS]
    groups += [(f"language {lg}", {x.id for x in ctx.tickets if x.language == lg}) for lg in ("en", "ar")]
    for label, ids in groups:
        mine = _sel(outs, ids)
        lines += cpst_lines(label, mine, [b1[o.ticket_id] for o in mine])
    return lines


def baselines_table(ctx: SplitContext, o1: list[Outcome]) -> list[str]:
    rows = [
        *ctx.baselines.items(),
        ("O1 (frozen)", o1),
        ("Oracle: cheapest correct config within budget", ctx.oracle),
    ]
    lines = [
        f"Policies on {ctx.split} (n={len(ctx.tickets)}), configs and floors frozen on dev. "
        "CPST = cost / successes.",
        f"    {'policy':<62}{'acc':>7}{'success':>9}{'p95 s':>7}"
        f"{'CPST headline':>15}{'CPST cached':>13}  floors",
    ]
    for name, outs in rows:
        s = summarize(outs)
        lines.append(
            f"    {name:<62}{s['accuracy']:>7.3f}{s['success_rate']:>9.3f}{s['p95_s']:>7.2f}"
            f"{s['cpst_nocache']:>15.5f}{s['cpst_cached']:>13.5f}  "
            + ("all met" if _meets(outs, ctx.floors) else "BREACH")
        )
    return lines


def scenario_breakout(ctx: SplitContext, o1: list[Outcome]) -> list[str]:
    """Adversarial and policy-change (rules v2) items reported separately (SPEC §4.3, §8)."""
    by_id = {t.id: t for t in ctx.tickets}
    lines = ["By scenario (O1; per-task accuracy against the frozen floors; small n, so read the counts)"]
    for sc in SCENARIOS:
        ids = {t.id for t in ctx.tickets if t.meta.scenario == sc}
        mine = _sel(o1, ids)
        if not mine:
            continue
        s = summarize(mine)
        lines.append(
            f"  {sc}: n={len(mine)}  correct {sum(o.correct for o in mine)}  accuracy {s['accuracy']:.3f}  "
            f"success {s['success_rate']:.3f}  CPST headline ${s['cpst_nocache']:.5f}  "
            f"with caching ${s['cpst_cached']:.5f}"
        )
        for t in TASKS:
            sub = [o for o in mine if o.task == t]
            if not sub:
                continue
            acc = summarize(sub)["accuracy"]
            floor = ctx.floors.per_task[t].floor
            lines.append(
                f"      {t:<11} n={len(sub):>3}  correct {sum(o.correct for o in sub):>3}  "
                f"accuracy {acc:.3f}  "
                f"floor {floor:.3f}{'' if acc >= floor else '  BELOW FLOOR'}"
            )
        if sc == "adversarial":
            lines.append("      item-level (adversarial kind as generated):")
            for o in mine:
                t = by_id[o.ticket_id]
                kind = t.meta.adversarial_kind
                lines.append(
                    f"        {o.ticket_id}  {o.task:<11}{t.language}  {kind or t.template_family:<28}"
                    f"{'correct' if o.correct else 'WRONG':<8}{'ok' if o.success else 'fail':<5} "
                    f"path {' > '.join(o.path)}"
                )
    return lines


def floor_diagnosis(ctx: SplitContext, o1: list[Outcome]) -> list[str]:
    """Every per-task floor breach of O1 on this split, with each wrong ticket and whether stronger configs
    solved it (a ticket no config solves points at the data, not the policy)."""
    lines = ["Floor check (O1 vs the frozen per-task floors)"]
    by_id = {t.id: t for t in ctx.tickets}
    any_breach = False
    for t in TASKS:
        sub = [o for o in o1 if o.task == t]
        acc = summarize(sub)["accuracy"]
        floor = ctx.floors.per_task[t].floor
        ok = acc >= floor
        any_breach |= not ok
        lines.append(f"    {t:<11} accuracy {acc:.3f} vs floor {floor:.3f}: {'met' if ok else 'BREACHED'}")
        if ok:
            continue
        for o in sub:
            if o.correct:
                continue
            tk = by_id[o.ticket_id]
            solved = [c for c in sorted({cfg for _, cfg in ctx.index}) if ctx.index[(o.ticket_id, c)].correct]
            final = ctx.index[(o.ticket_id, o.path[-1])] if not o.path[0].startswith("tier0") else None
            why = "; ".join(final.check_reasons) if final and final.check_reasons else "passed every check"
            lines.append(
                f"      {o.ticket_id} {tk.meta.scenario}/{tk.rules_version}/{tk.language}/{tk.level}  path "
                f"{' > '.join(o.path)}  final answer checks: {why}  configs correct: {len(solved)}/9 "
                f"({', '.join(solved) or 'none'})"
            )
    if not any_breach:
        lines.append("    no floor breached")
    lines += reachability(ctx, o1)
    return lines


def reachability(ctx: SplitContext, o1: list[Outcome]) -> list[str]:
    """Is each floor reachable on this split at all? The best single config per task (by accuracy here, for
    diagnosis only; nothing is chosen from it), and O1 restricted to tickets the strongest config solves."""
    configs = sorted({cfg for _, cfg in ctx.index})
    lines = ["    Reachability (diagnosis only; nothing is selected from these numbers)"]
    for t in TASKS:
        ids = [x.id for x in ctx.tickets if x.task_type == t]
        accs = {c: sum(ctx.index[(i, c)].correct for i in ids) / len(ids) for c in configs}
        best = max(accs.values())
        top = [c for c, a in accs.items() if a == best]
        unsolved = [i for i in ids if not any(ctx.index[(i, c)].correct for c in configs)]
        lines.append(
            f"      {t:<11} best single config {best:.3f} ({', '.join(top)}) vs floor "
            f"{ctx.floors.per_task[t].floor:.3f}: "
            + ("reachable" if best >= ctx.floors.per_task[t].floor else "NOT reachable by any single config")
            + f"; tickets no config solves: {len(unsolved)}"
        )
    hard = {x.id for x in ctx.tickets if not ctx.index[(x.id, "opus-high")].correct}
    for t in TASKS:
        sub = [o for o in o1 if o.task == t and o.ticket_id not in hard]
        n_hard = sum(o.task == t for o in o1) - len(sub)
        if n_hard:
            acc = summarize(sub)["accuracy"]
            lines.append(
                f"      {t:<11} O1 on the {len(sub)} tickets opus-high solves (excluding {n_hard}): "
                f"accuracy {acc:.3f}"
                f" vs floor {ctx.floors.per_task[t].floor:.3f}"
            )
    return lines


def tier0_rule(ctx: SplitContext, o1: list[Outcome]) -> list[str]:
    """D3.6 (pre-registered): Tier 0 is removed before freeze-v1 if it answers no shifted item correctly."""
    t0 = Tier0()
    hits = [(t, t0.check(t.id, t.task_type, t.text)) for t in ctx.tickets]
    actions = Counter(h.action for _, h in hits)
    lang_ok = sum(h.language == t.language for t, h in hits)
    by_id = {o.ticket_id: o for o in o1}
    answered = [(t, h) for t, h in hits if h.action != "pass"]
    correct = [t for t, _ in answered if by_id[t.id].correct]
    keep = bool(correct)
    lines = [
        f"Tier 0 on {ctx.split} (n={len(ctx.tickets)}): "
        + ", ".join(f"{a} {k}" for a, k in sorted(actions.items())),
        f"    answered without a model: {len(answered)}; answered correctly: {len(correct)}",
        f"    language detection agrees with the ticket label on {lang_ok}/{len(ctx.tickets)}",
    ]
    for t, h in answered:
        lines.append(
            f"      {t.id} {t.task_type} {h.action} -> {'correct' if by_id[t.id].correct else 'wrong'}"
        )
    lines.append(
        "    D3.6 rule (pre-registered): remove Tier 0 before freeze-v1 if it answers no shifted item "
        "correctly -> "
        + ("KEEP (it answered at least one correctly)" if keep else "REMOVE (it answered none correctly)")
    )
    return lines


def router_ceiling(ctx: SplitContext, traces: list[Trace], o1: list[Outcome]) -> list[str]:
    """Context only (D3.4: both routers already dropped on dev; no Jev call on shifted)."""
    esc = frozenset(tr.ticket_id for tr in traces if tr.escalated)
    perfect, _ = ctx.o1(O1_DEFAULT.model_copy(update={"direct_top": esc}))
    s, p = summarize(o1), summarize(perfect)
    cpst_gain = (s["cpst_nocache"] - p["cpst_nocache"]) / s["cpst_nocache"]
    p95_gain = (s["p95_s"] - p["p95_s"]) / s["p95_s"] if s["p95_s"] else 0.0
    return [
        "Perfect-router ceiling on shifted (context only: routers dropped on dev, D3.4; no Jev run here)",
        f"    a router sending exactly the {len(esc)} tickets O1 escalates straight to {O1_DEFAULT.top}:",
        f"    CPST headline ${p['cpst_nocache']:.5f} vs O1 ${s['cpst_nocache']:.5f} ({cpst_gain:+.1%}), "
        f"p95 {p['p95_s']:.2f}s vs {s['p95_s']:.2f}s ({p95_gain:+.1%}); SPEC 7.7 bars: 5% CPST, 20% p95",
    ]


def shifted_report(ctx: SplitContext) -> str:
    outs, traces = ctx.o1()
    adj = [x for x in outs if x.task == "adjudicate"]
    reasons = Counter(t.reason for t in traces if t.escalated)
    cov, n = v3_coverage(ctx, O1_DEFAULT.deadline_s)
    late = sum(t.second_late for t in traces)
    lines = [
        f"Shifted split (n={len(ctx.tickets)}): the FROZEN policy scored by replay of {ctx.run_id}.",
        "Nothing below was tuned on shifted. Floors/budgets: config/policy.yaml (frozen).",
        f"Static configs (picked on {ctx.fc.dev_run}): "
        + ", ".join(f"{t} {c}" for t, c in ctx.static.items()),
        f"O1 adjudicate: {O1_DEFAULT.first} || {O1_DEFAULT.second}, D = {O1_DEFAULT.deadline_s}s, "
        f"early escalation to {O1_DEFAULT.top}. Composition: "
        + ", ".join(f"{k} {v}" for k, v in sorted(Counter(t.meta.scenario for t in ctx.tickets).items()))
        + ", rules v2 items "
        + str(sum(t.rules_version == "v2" for t in ctx.tickets))
        + ".",
        "",
        *baselines_table(ctx, outs),
        "",
        *policy_block("O1 (frozen) on shifted", outs, {"B1": ctx.b1, "B3": ctx.b3}, ctx),
        "",
        *oracle_gap(outs, ctx),
        "",
        *breakdown("O1", outs, ctx),
        "",
        "Per task (O1)",
        *per_task_lines(outs, ctx),
        "",
        *floor_diagnosis(ctx, outs),
        "",
        *scenario_breakout(ctx, outs),
        "",
        f"Adjudicate (O1): correct {sum(x.correct for x in adj)}/{len(adj)}  "
        f"success {sum(x.success for x in adj)}/{len(adj)}  "
        f"escalated {sum(t.escalated for t in traces)}/{len(traces)}",
        "    escalation reasons: " + (", ".join(f"{r} {k}" for r, k in reasons.most_common()) or "none"),
        f"    V3 coverage (second opinion in time, by max(haiku-low latency, D)): {cov}/{n} ({cov / n:.1%}); "
        f"late {late}/{n}",
        "",
        *v3_quality(traces, ctx, O1_DEFAULT),
        "",
        *tier0_rule(ctx, outs),
        "",
        *router_ceiling(ctx, traces, outs),
        "",
        *misses(outs, ctx),
    ]
    return "\n".join(lines)


def baselines_breakdown_report(ctx: SplitContext) -> str:
    lines = [f"Baselines on {ctx.split} by subset (configs chosen on dev), CPST with 95% bootstrap CIs", ""]
    for name, outs in ctx.baselines.items():
        lines += [*breakdown(name, outs, ctx), ""]
    return "\n".join(lines)


def header(ctx: SplitContext) -> str:
    return (
        f"run: {ctx.run_id} | split: {ctx.split} | frozen choices from: {ctx.fc.dev_run} | "
        f"git: {runinfo.git_sha()} | config_hash: {config_hash(split_versions(ctx.tickets))}\n\n"
    )


REPORTS = {
    "shifted.txt": shifted_report,
    "shifted_baselines.txt": baselines_breakdown_report,
    "shifted_ablations.txt": ablations_report,
}


def write(run_id: str = SHIFTED_RUN, out: Path = OUT) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    ctx = SplitContext(run_id, "shifted")
    paths = []
    for name, fn in REPORTS.items():
        path = out / name
        path.write_text(header(ctx) + fn(ctx) + "\n\n" + "\n".join(CAVEATS) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


__all__ = ["ABLATIONS", "REPORTS", "SplitContext", "write"]
