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


def _p95_gain_ci(base: list[Outcome], other: list[Outcome], samples: list[list[int]]) -> tuple[float, float]:
    from engine.eval.metrics import percentile

    diffs = []
    for idx in samples:
        a = percentile([base[i].latency_ms for i in idx], 95)
        b = percentile([other[i].latency_ms for i in idx], 95)
        diffs.append((a - b) / a)
    return B.percentile_ci(diffs)


def evaluate_router(
    ctx: Context, name: str, probs: dict[str, float], overhead: dict[str, tuple[float, float]] | None = None
) -> list[str]:
    """Tune the threshold on dev out-of-fold probabilities (lowest headline CPST meeting every floor), then
    apply SPEC §7.7 on dev. Provisional: §7.7 also needs the shifted split (Phase 4)."""
    from sklearn.metrics import roc_auc_score

    from engine.eval.baselines import oracle
    from engine.eval.metrics import percentile

    base, traces = ctx.o1()
    escalates = {tr.ticket_id: tr.escalated for tr in traces}
    adj = [t for t in ctx.tickets if t.task_type == "adjudicate"]
    y = [escalates[t.id] for t in adj]
    p = [probs[t.id] for t in adj]
    best = None
    for tau in sorted({*p, 1.01}):
        routed = frozenset(t.id for t in adj if probs[t.id] >= tau)
        outs, _ = ctx.o1(
            O1_DEFAULT.model_copy(update={"direct_top": routed, "router_overhead": overhead or {}})
        )
        if not _meets(outs, ctx.floors):
            continue
        cpst = summarize(outs)["cpst_nocache"]
        if best is None or cpst < best[0] - 1e-12:
            best = (cpst, tau, routed, outs)
    _, tau, routed, outs = best
    choose = oracle(ctx.index, ctx.floors)
    above_oracle = sum(choose(t)[0] != O1_DEFAULT.top for t in adj if t.id in routed)
    tp = sum(escalates[i] for i in routed)
    s_base, s = summarize(base), summarize(outs)
    gain = (s_base["cpst_nocache"] - s["cpst_nocache"]) / s_base["cpst_nocache"]
    glo, ghi = B.paired_diff_ci(
        _arr(base, "cost_nocache"), _arr(outs, "cost_nocache"), ctx.samples, relative=True
    )
    p95_gain = (
        percentile([o.latency_ms for o in base], 95) - percentile([o.latency_ms for o in outs], 95)
    ) / (percentile([o.latency_ms for o in base], 95))
    plo, phi = _p95_gain_ci(base, outs, ctx.samples)
    cpst_ok = gain >= 0.05 and glo > 0
    p95_ok = p95_gain >= 0.20 and plo > 0
    floors_ok = _meets(outs, ctx.floors)
    keep = (cpst_ok or p95_ok) and floors_ok
    perfect, _ = ctx.o1(
        O1_DEFAULT.model_copy(update={"direct_top": frozenset(i for i, e in escalates.items() if e)})
    )
    sp = summarize(perfect)
    return [
        f"Ceiling: a PERFECT router (routes exactly the {sum(y)} tickets O1 escalates) gives CPST (headline) "
        f"${sp['cpst_nocache']:.5f} vs O1 ${s_base['cpst_nocache']:.5f} "
        f"({(s_base['cpst_nocache'] - sp['cpst_nocache']) / s_base['cpst_nocache']:+.1%}), p95 {sp['p95_s']:.2f}s vs "
        f"{s_base['p95_s']:.2f}s, success {sp['success_rate']:.3f} vs {s_base['success_rate']:.3f}",
        "",
        f"{name}: label = 'O1 escalates this adjudicate ticket' ({sum(y)}/{len(y)} positive on dev)",
        f"    ROC AUC on dev (local: out-of-fold; Jev: zero-shot) {roc_auc_score(y, p):.3f}"
        if 0 < sum(y) < len(y)
        else "    AUC undefined",
        f"    threshold (tuned on dev; lowest headline CPST meeting every floor): "
        f"{'never route' if tau > 1 else f'{tau:.3f}'}",
        f"    routed straight to opus-low: {len(routed)}/{len(adj)}  (would have escalated: {tp}; "
        f"misroute up = routed but O1 would not escalate: {len(routed) - tp}; "
        f"misroute down = escalated but not routed: {sum(y) - tp})",
        f"    collapse check: routed tickets whose oracle rung is below opus-low: {above_oracle}/{len(routed)}"
        if routed
        else "    collapse check: nothing routed",
        "",
        *policy_block(f"O1 + {name}", outs, {"O1": base}, ctx),
        f"    p95 latency: O1 {s_base['p95_s']:.2f}s -> {s['p95_s']:.2f}s  improvement {p95_gain:+.1%} [{plo:+.1%}, {phi:+.1%}]",
        "",
        "SPEC 7.7 on dev only (PROVISIONAL: final only with the Phase 4 shifted matrix)",
        f"    (a) CPST improves >= 5% with CI excluding 0: {'yes' if cpst_ok else 'no'} ({gain:+.1%} [{glo:+.1%}, {ghi:+.1%}])",
        f"        or p95 improves >= 20% with CI excluding 0: {'yes' if p95_ok else 'no'} ({p95_gain:+.1%} [{plo:+.1%}, {phi:+.1%}])",
        f"    (b) no per-task floor breached: {'yes' if floors_ok else 'no'}",
        f"    dev verdict: {'passes on dev' if keep else 'fails on dev -> drop (7.7 needs BOTH dev and shifted; shifted cannot reverse this)'}",
        "",
        "Per task (with router)",
        *per_task_lines(outs, ctx),
    ]


def local_router_report(ctx: Context) -> str:
    from engine.router.local import FOLDS, out_of_fold

    _, traces = ctx.o1()
    escalates = {tr.ticket_id: tr.escalated for tr in traces}
    adj = [t for t in ctx.tickets if t.task_type == "adjudicate"]
    probs = out_of_fold(adj, [escalates[t.id] for t in adj])
    return "\n".join(
        [
            "Local router (SPEC 6.4): TF-IDF char 2-5-grams (char_wb) + length, language, digits, amounts, dates",
            f"-> logistic regression (class_weight balanced), {FOLDS}-fold stratified out-of-fold on dev adjudicate.",
            "faq / intent / extract: no router action (O1 already starts at the cheapest config meeting the floor).",
            "",
            *evaluate_router(ctx, "local router", probs),
        ]
    )


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


def jev_router_report(ctx: Context) -> str:
    from collections import Counter as C

    from engine.router import jev_router as J

    adj = [t for t in ctx.tickets if t.task_type == "adjudicate"]
    answers = J.run(adj, "replay")  # recorded run jev-router-dev-1; no key, no spend
    probs = {i: J.p_complex(r) for i, r in answers.items()}
    overhead = {i: (r.cost_usd or 0.0, r.latency_ms) for i, r in answers.items()}
    _, traces = ctx.o1()
    esc = {tr.ticket_id: tr.escalated for tr in traces}
    by_choice = C((answers[t.id].answers["complexity"]["choice"], esc[t.id]) for t in adj)
    total = sum(c for c, _ in overhead.values())
    return "\n".join(
        [
            f"Jev router (D3.3): run {J.RUN_ID}, model {J.JEV_MODEL}, ticket text only; zero-shot, so no folds.",
            "Mapping (declared before the run): straight to opus-low iff P(complexity = complex) >= tau.",
            f"Jev spend on the 180 dev adjudicate tickets: ${total:.6f}; its cost and latency are added to every one.",
            "complexity answer vs 'O1 escalates': "
            + ", ".join(
                f"{ch} {sum(n for (c, e), n in by_choice.items() if c == ch)} "
                f"(escalated {by_choice[(ch, True)]})"
                for ch in ("simple", "moderate", "complex")
            ),
            "",
            *evaluate_router(ctx, "Jev router", probs, overhead),
        ]
    )


def effort_report(ctx: Context) -> str:
    """Per model: accuracy and cost by effort level, over the same 400 dev tickets (paired)."""
    from engine.eval.metrics import mean, percentile

    efforts = ("low", "medium", "high")
    ids = [t.id for t in ctx.tickets]
    lines = [
        "Effort finding (dev, 400 tickets, every config answers every ticket; all matrix calls read a warm cache)",
        "Cost per call is the mean over all 400 tickets. Accuracy delta vs low: paired bootstrap 95% CI.",
        "",
        f"{'model':<8}{'effort':<8}{'acc':>7}{'adjud.':>8}{'vs low (acc)':>24}{'with caching $/call':>21}"
        f"{'x low':>7}{'headline $/call':>17}{'out tok':>9}{'think tok':>10}{'p50 s':>7}{'p95 s':>7}",
    ]
    for model in ("haiku", "sonnet", "opus"):
        cells = {e: [ctx.index[(i, f"{model}-{e}")] for i in ids] for e in efforts}
        low_cost = mean(c.cost_usd for c in cells["low"])
        for e in efforts:
            cs = cells[e]
            acc = mean(c.correct for c in cs)
            adj = mean(c.correct for c in cs if c.task == "adjudicate")
            if e == "low":
                delta = ""
            else:
                lo, hi = B.paired_mean_diff_ci(
                    [float(c.correct) for c in cs], [float(c.correct) for c in cells["low"]], ctx.samples
                )
                delta = f"{acc - mean(c.correct for c in cells['low']):+.3f} [{lo:+.3f}, {hi:+.3f}]"
            cost = mean(c.cost_usd for c in cs)
            lines.append(
                f"{model:<8}{e:<8}{acc:>7.3f}{adj:>8.3f}{delta:>24}{cost:>21.6f}{cost / low_cost:>7.2f}"
                f"{mean(c.cost_usd_nocache for c in cs):>17.6f}{mean(c.output_tokens for c in cs):>9.0f}"
                f"{mean(c.thinking_tokens or 0 for c in cs):>10.0f}"
                f"{percentile([c.latency_ms for c in cs], 50) / 1000:>7.2f}"
                f"{percentile([c.latency_ms for c in cs], 95) / 1000:>7.2f}"
            )
        lines.append("")
    lines.append(
        "Reading: compare rows within a model. 'x low' = Cost with caching (actual) per call relative to the same "
        "model at low effort."
    )
    return "\n".join(lines)


REPORTS = {
    "o1.txt": o1_report,
    "ablations.txt": ablations_report,
    "router_local.txt": local_router_report,
    "router_jev.txt": jev_router_report,
    "effort.txt": effort_report,
}
