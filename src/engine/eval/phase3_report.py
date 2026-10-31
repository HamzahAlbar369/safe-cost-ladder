"""Phase 3 evidence under reports/phase3/ (replay only, no API calls). Every file starts with its provenance
(run id, git SHA, config hash) so no number is typed by hand (CLAUDE.md: Numbers)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from engine import runinfo
from engine.contracts import Ticket
from engine.eval import bootstrap as B
from engine.eval.baselines import CellIndex, Outcome, index_cells, run_policy, static_by_task, summarize
from engine.eval.cells import build_cells
from engine.eval.data import load_split
from engine.eval.floors import Floors
from engine.eval.matrix import config_hash
from engine.eval.metrics import TASKS
from engine.llm.pricing import ROOT
from engine.policy.cascade import O1Options, Trace, passes, run_o1
from engine.policy.controller import floors_for, load_policy
from engine.tier0 import Tier0

OUT = ROOT / "reports" / "phase3"
O1_DEFAULT = O1Options()
DEADLINE_TABLE = (None, 6.0, 5.0)  # D3.2: the deadline values compared on dev


class Context:
    """Everything a Phase 3 report needs, loaded once from the recorded dev matrix."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.tickets: list[Ticket] = sorted(load_split("dev"), key=lambda t: t.id)
        cells, problems = build_cells([run_id], self.tickets)
        if problems:
            raise RuntimeError(f"{len(problems)} cells without a response, e.g. {problems[0]}")
        self.cells = cells
        self.index: CellIndex = index_cells(cells)
        self.policy = load_policy()
        self.floors: Floors = floors_for(cells, self.policy)
        self.static = static_by_task(self.index, self.floors)
        self.samples = B.resample_indices(len(self.tickets))
        self.b1 = run_policy(lambda t: ("opus-low",), self.tickets, self.index, self.floors)
        self.b3 = run_policy(lambda t: (self.static[t.task_type],), self.tickets, self.index, self.floors)

    def o1(self, o: O1Options = O1_DEFAULT) -> tuple[list[Outcome], list[Trace]]:
        return run_o1(self.tickets, self.index, self.floors, self.static, o)


def _arr(outs: list[Outcome], key: str) -> tuple[list[float], list[float]]:
    return [getattr(o, key) for o in outs], [float(o.success) for o in outs]


def _meets(outs: list[Outcome], floors: Floors) -> bool:
    return all(
        summarize([o for o in outs if o.task == t])["accuracy"] >= floors.per_task[t].floor for t in TASKS
    )


def policy_block(name: str, outs: list[Outcome], refs: dict[str, list[Outcome]], ctx: Context) -> list[str]:
    s = summarize(outs)
    lines = [
        name,
        f"    correct {sum(o.correct for o in outs)}/{len(outs)}  accuracy {s['accuracy']:.3f}  success "
        f"{s['success_rate']:.3f}  p50 {s['p50_s']:.2f}s  p95 {s['p95_s']:.2f}s  "
        f"meets every floor: {'yes' if _meets(outs, ctx.floors) else 'NO'}",
    ]
    for key, label, field in (
        ("cost_nocache", "Cost without caching (headline)", "cpst_nocache"),
        ("cost_cached", "Cost with caching (actual)", "cpst_cached"),
    ):
        lo, hi = B.cpst_ci(*_arr(outs, key), ctx.samples)
        lines.append(f"    CPST, {label + ':':<33} ${s[field]:.5f} [{lo:.5f}, {hi:.5f}]")
        for ref_name, ref in refs.items():
            r = summarize(ref)[field]
            clo, chi = B.paired_diff_ci(_arr(ref, key), _arr(outs, key), ctx.samples, relative=True)
            lines.append(
                f"        vs {ref_name}: ${r:.5f} -> ${s[field]:.5f}  saving {(r - s[field]) / r:+.1%} "
                f"[{clo:+.1%}, {chi:+.1%}]"
            )
    return lines


def per_task_lines(outs: list[Outcome], ctx: Context) -> list[str]:
    lines = [
        f"    {'task':<11}{'n':>4}{'correct':>9}{'acc':>7}{'floor':>7}{'success':>9}{'p95 s':>8}{'budget s':>10}"
    ]
    for t in TASKS:
        mine = [o for o in outs if o.task == t]
        s = summarize(mine)
        f = ctx.floors.per_task[t]
        flag = "" if s["accuracy"] >= f.floor else "  FLOOR BREACH"
        lines.append(
            f"    {t:<11}{len(mine):>4}{sum(o.correct for o in mine):>9}{s['accuracy']:>7.3f}{f.floor:>7.3f}"
            f"{s['success_rate']:>9.3f}{s['p95_s']:>8.2f}{f.budget_s:>10.1f}{flag}"
        )
    for lang in ("en", "ar"):
        s = summarize([o for o in outs if o.language == lang])
        lines.append(
            f"    language {lang}: n={s['n']}  accuracy {s['accuracy']:.3f}  success {s['success_rate']:.3f}"
        )
    return lines


def v3_quality(traces: list[Trace], ctx: Context, o: O1Options) -> list[str]:
    """False accepts of the first answer with V0-V2 alone vs with V3 added (adjudicate, dev)."""
    escalated = {tr.ticket_id for tr in traces if tr.escalated}
    firsts = [ctx.index[(tr.ticket_id, o.first)] for tr in traces]
    wrong = [c for c in firsts if not c.correct]
    right = [c for c in firsts if c.correct]
    fa_v02 = [c for c in wrong if passes(c, o.checks)]
    fa_v3 = [c for c in wrong if c.ticket_id not in escalated]
    fr_v02 = [c for c in right if not passes(c, o.checks)]
    fr_v3 = [c for c in right if c.ticket_id in escalated]
    pct = lambda k, n: f"{k}/{n} ({k / n:.1%})" if n else "-"  # noqa: E731
    return [
        f"Verifier quality on the {o.first} adjudicate answer (n={len(firsts)}; wrong {len(wrong)}, correct {len(right)})",
        f"    false-accept rate, V0-V2 only:        {pct(len(fa_v02), len(wrong))}",
        f"    false-accept rate, V0-V2 + V3 (O1):   {pct(len(fa_v3), len(wrong))}"
        f"   still accepted: {', '.join(c.ticket_id for c in fa_v3) or 'none'}",
        f"    false-reject rate, V0-V2 only:        {pct(len(fr_v02), len(right))}",
        f"    false-reject rate, V0-V2 + V3 (O1):   {pct(len(fr_v3), len(right))}  (correct answers escalated)",
    ]


def deadline_table(ctx: Context) -> list[str]:
    lines = [
        "Deadline for the second opinion (D3.2; tuned on dev only; late calls charged in full)",
        f"    {'D':>6}{'correct':>9}{'success':>9}{'escalated':>11}{'second late':>13}  adjudicate CPST (headline)",
    ]
    for d in DEADLINE_TABLE:
        outs, traces = ctx.o1(O1_DEFAULT.model_copy(update={"deadline_s": d}))
        adj = [x for x in outs if x.task == "adjudicate"]
        s = summarize(adj)
        lines.append(
            f"    {'none' if d is None else f'{d:.1f}s':>6}{sum(x.correct for x in adj):>9}"
            f"{sum(x.success for x in adj):>9}{sum(t.escalated for t in traces):>11}"
            f"{sum(t.second_late for t in traces):>13}  ${s['cpst_nocache']:.5f}"
        )
    return lines


def misses(outs: list[Outcome], ctx: Context) -> list[str]:
    lines = ["Remaining failures (wrong, or correct but over the task's latency budget)"]
    for x in outs:
        if x.success:
            continue
        why = "wrong" if not x.correct else "over budget"
        budget = ctx.floors.per_task[x.task].budget_s
        lines.append(
            f"    {x.ticket_id}  {x.task:<11}{why:<12}{x.latency_ms / 1000:>6.2f}s / {budget:.1f}s  "
            f"path {' > '.join(x.path)}"
        )
    return lines


def o1_report(ctx: Context) -> str:
    outs, traces = ctx.o1()
    adj = [x for x in outs if x.task == "adjudicate"]
    reasons = Counter(t.reason for t in traces if t.escalated)
    o = O1_DEFAULT
    lines = [
        "O1 = per-task cheapest config meeting the floor + risk-tiered verification on adjudicate (SPEC 7.3)",
        f"    faq/intent/extract: {', '.join(f'{t} {ctx.static[t]}' for t in TASKS if t != 'adjudicate')} "
        "(no verification)",
        f"    adjudicate: {o.first} || {o.second} in parallel; wait for {o.second} at most {o.deadline_s}s; "
        f"accept {o.first} iff V0-V2 pass and the two agree (decision, payout +-1 SAR); "
        f"if {o.second} is late, iff {o.first} passes V0-V2; else escalate to {o.top}",
        f"    floors and budgets: config/policy.yaml (frozen, budget rule {ctx.policy.budget_rule})",
        "    Tier 0 in front of every task: empty reject, exact-duplicate reuse, FAQ table (empty by default)",
        "",
        f"Adjudicate: correct {sum(x.correct for x in adj)}/{len(adj)}  success {sum(x.success for x in adj)}/"
        f"{len(adj)}  escalated {sum(t.escalated for t in traces)}/{len(traces)} "
        f"({sum(t.escalated for t in traces) / len(traces):.1%})  second opinion late "
        f"{sum(t.second_late for t in traces)}",
        "    escalation reasons: " + ", ".join(f"{r} {n}" for r, n in reasons.most_common()),
        "",
        *policy_block("O1", outs, {"B1 (opus-low)": ctx.b1, "B3 (static per task)": ctx.b3}, ctx),
        "",
        "Per task (O1)",
        *per_task_lines(outs, ctx),
        "",
        *v3_quality(traces, ctx, o),
        "",
        *deadline_table(ctx),
        "",
        *tier0_lines(ctx),
        "",
        *misses(outs, ctx),
    ]
    return "\n".join(lines)


def tier0_lines(ctx: Context) -> list[str]:
    t0 = Tier0()
    hits = [t0.check(t.id, t.task_type, t.text) for t in ctx.tickets]
    actions = Counter(h.action for h in hits)
    lang_ok = sum(h.language == t.language for h, t in zip(hits, ctx.tickets, strict=True))
    n = len(ctx.tickets)
    answered = n - actions["pass"]
    return [
        f"Tier 0 on dev (n={n}): answered without a model {answered}/{n} ({answered / n:.1%}); "
        + ", ".join(f"{a} {k}" for a, k in sorted(actions.items())),
        f"    language detection agrees with the ticket label on {lang_ok}/{n}",
        "    dev has no empty tickets and no exact duplicates by construction (Phase 1 QA), and no FAQ table exists;",
        "    Tier 0 is kept for robustness (shifted adversarial / near-empty items, Phase 4), not for dev savings.",
    ]


ABLATIONS: dict[str, O1Options] = {
    "O1 as specified (no deadline)": O1_DEFAULT.model_copy(update={"deadline_s": None}),
    "drop V3 (haiku-low -> opus-low on a V0-V2 failure)": O1_DEFAULT.model_copy(update={"second": None}),
    "drop V2 (V0-V1 + V3 only)": O1_DEFAULT.model_copy(update={"checks": ("V0", "V1")}),
    "drop Tier 0": O1_DEFAULT.model_copy(update={"tier0": False}),
}


def ablation_rows(ctx: Context) -> list[tuple[str, list[Outcome]]]:
    return [(name, ctx.o1(o)[0]) for name, o in ABLATIONS.items()]


def ablations_report(ctx: Context) -> str:
    """Each O1 layer toggled off one at a time (SPEC 7.5), compared with O1 on the same tickets (paired)."""
    base, _ = ctx.o1()
    lines = [
        "Ablations: one O1 layer off at a time, paired against O1 on the same 400 dev tickets",
        "'saving' > 0 = the ablation is cheaper per successful task than O1 (the layer costs money and is kept only",
        "if it is needed to meet a floor). Accuracy/success deltas are ablation - O1 (paired bootstrap 95% CI).",
        "",
        "O1 (all layers)",
        *per_task_lines(base, ctx),
    ]
    for name, outs in ablation_rows(ctx):
        lines += ["", *policy_block(name, outs, {"O1": base}, ctx)]
        for task in ("adjudicate", None):
            sel = [i for i, x in enumerate(outs) if task in (None, x.task)]
            a = [float(outs[i].correct) for i in sel]
            b = [float(base[i].correct) for i in sel]
            sa = [float(outs[i].success) for i in sel]
            sb = [float(base[i].success) for i in sel]
            sub = B.resample_indices(len(sel))
            lo, hi = B.paired_mean_diff_ci(a, b, sub)
            slo, shi = B.paired_mean_diff_ci(sa, sb, sub)
            lines.append(
                f"    {task or 'overall'}: accuracy delta {(sum(a) - sum(b)) / len(sel):+.3f} [{lo:+.3f}, {hi:+.3f}]  "
                f"success delta {(sum(sa) - sum(sb)) / len(sel):+.3f} [{slo:+.3f}, {shi:+.3f}]  "
                f"correct {int(sum(a))} vs {int(sum(b))}"
            )
        lines += [f"    per task ({name})", *per_task_lines(outs, ctx)]
    return "\n".join(lines)


def write(run_id: str, reports: dict[str, callable], out: Path = OUT) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    header = f"run: {run_id} | split: dev | git: {runinfo.git_sha()} | config_hash: {config_hash()}\n\n"
    ctx = Context(run_id)
    paths = []
    for name, fn in reports.items():
        path = out / name
        path.write_text(header + fn(ctx) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


REPORTS = {"o1.txt": o1_report, "ablations.txt": ablations_report}
