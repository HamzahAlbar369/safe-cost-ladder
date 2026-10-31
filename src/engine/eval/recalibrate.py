"""Audit-and-recalibrate loop (Phase 4, D4.6). RECALIBRATION ANALYSIS; the held-out run uses the dev-frozen O1.

Product framing: a human QA team labels a small sample of recent traffic (the audit sample). The layer
(a) scores the policy it is running on that sample, per task, against the FROZEN floors (drift detection), and
(b) re-applies the frozen selection rules (the controller, unchanged) to the sample to re-pick configs:
- per task: the cheapest config (mean headline cost on the sample) whose sample accuracy meets the floor;
- adjudicate ladder: `first` || `second` as frozen (haiku-low || haiku-medium), `top` = the adjudicate pick above;
  the cascade is kept iff it meets the adjudicate floor on the sample (the acceptance test that admitted it on
  dev in Phase 3), otherwise adjudicate goes straight to `top`;
(c) where no config meets a floor on the sample: the most accurate config, flagged "floor unreachable on this
traffic".
Floors and budgets never move. Replay only: every number is a lookup in recorded matrices.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict

from engine.contracts import Frozen, Ticket
from engine.eval import bootstrap as B
from engine.eval.baselines import CellIndex, Outcome, run_policy, summarize
from engine.eval.floors import Floors
from engine.eval.metrics import TASKS, mean
from engine.eval.scenarios import Adapted, run_adapted
from engine.policy.cascade import run_o1
from engine.policy.frozen import FrozenChoices

LABEL = "RECALIBRATION ANALYSIS; the held-out run uses the dev-frozen O1"
SEED = 20261031
SAMPLE_SIZES = (20, 40, 100, 150, 200)  # 200 = all of shifted (drawn without replacement)
RESAMPLES = 500
ALPHA = 0.05


class Recalibration(Frozen):
    drift: dict[str, bool]  # task -> frozen O1 accuracy on the sample is below the floor (naive)
    drift_binomial: dict[str, bool]  # task -> one-sided binomial test rejects accuracy >= floor (alpha 0.05)
    sample_accuracy: dict[str, float]  # frozen O1, per task, on the sample
    picks: dict[str, str]  # task -> re-picked config
    unreachable: dict[str, bool]  # task -> no config meets the floor on the sample
    cascade_kept: bool
    adapted: Adapted


def _configs(index: CellIndex) -> list[str]:
    return sorted({cfg for _, cfg in index})


def _task_acc(index: CellIndex, ids: list[str], cfg: str) -> float:
    return mean(index[(i, cfg)].correct for i in ids)


def _task_cost(index: CellIndex, ids: list[str], cfg: str) -> float:
    return mean(index[(i, cfg)].cost_usd_nocache for i in ids)


def frozen_o1(fc: FrozenChoices, tickets: list[Ticket], index: CellIndex) -> list[Outcome]:
    return run_o1(tickets, index, fc.floors, fc.static, fc.o1)[0]


def recalibrate(fc: FrozenChoices, audit: list[Ticket], index: CellIndex) -> Recalibration:
    floors: Floors = fc.floors
    current = frozen_o1(fc, audit, index)
    acc = {t: summarize([o for o in current if o.task == t])["accuracy"] for t in TASKS}
    drift = {t: acc[t] < floors.per_task[t].floor for t in TASKS}
    tested = {}
    for t in TASKS:
        sub = [o for o in current if o.task == t]
        tested[t] = binomial_drift(sum(o.correct for o in sub), len(sub), floors.per_task[t].floor)
    picks, unreachable = {}, {}
    for t in TASKS:
        ids = [x.id for x in audit if x.task_type == t]
        ok = [c for c in _configs(index) if _task_acc(index, ids, c) >= floors.per_task[t].floor]
        unreachable[t] = not ok
        if ok:
            picks[t] = min(ok, key=lambda c: _task_cost(index, ids, c))
        else:
            picks[t] = min(
                _configs(index), key=lambda c: (-_task_acc(index, ids, c), _task_cost(index, ids, c))
            )
    o1 = fc.o1.model_copy(update={"top": picks["adjudicate"]})
    adj = [x for x in audit if x.task_type == "adjudicate"]
    cascade = run_o1(adj, index, floors, picks, o1)[0]
    kept = summarize(cascade)["accuracy"] >= floors.per_task["adjudicate"].floor
    adapted = Adapted(floors=floors, static=picks, b1=fc.b1, o1=o1 if kept else None)
    return Recalibration(
        drift=drift,
        drift_binomial=tested,
        sample_accuracy=acc,
        picks=picks,
        unreachable=unreachable,
        cascade_kept=kept,
        adapted=adapted,
    )


def failsafe(fc: FrozenChoices, r: Recalibration) -> Adapted:
    """D4.7 fail-safe (added AFTER observing shifted; it selects nothing from shifted or from the sample): every
    task whose binomial detector fired reverts to B1's config for that task (`fc.b1`, chosen on dev); every
    other task keeps its frozen O1 config. An alarmed adjudicate drops the cascade and calls B1 alone."""
    static = {t: fc.b1 if r.drift_binomial[t] else c for t, c in fc.static.items()}
    return Adapted(
        floors=fc.floors, static=static, b1=fc.b1, o1=None if r.drift_binomial["adjudicate"] else fc.o1
    )


def stratified_folds(tickets: list[Ticket], k: int = 2, seed: int = SEED) -> list[list[Ticket]]:
    strata: dict[tuple[str, str], list[Ticket]] = defaultdict(list)
    for t in sorted(tickets, key=lambda t: t.id):
        strata[(t.task_type, t.language)].append(t)
    rng = random.Random(seed)
    folds: list[list[Ticket]] = [[] for _ in range(k)]
    offset = 0
    for key in sorted(strata):
        group = strata[key]
        rng.shuffle(group)
        for i, t in enumerate(group):
            folds[(i + offset) % k].append(t)
        offset += len(group)  # alternate which fold gets the odd item
    return folds


def stratified_sample(tickets: list[Ticket], n: int, rng: random.Random) -> list[Ticket]:
    """n tickets, task shares as in `tickets` (largest remainder), uniformly within each task."""
    by_task: dict[str, list[Ticket]] = defaultdict(list)
    for t in tickets:
        by_task[t.task_type].append(t)
    exact = {t: n * len(v) / len(tickets) for t, v in by_task.items()}
    quota = {t: int(x) for t, x in exact.items()}
    for t in sorted(exact, key=lambda t: exact[t] - quota[t], reverse=True)[: n - sum(quota.values())]:
        quota[t] += 1
    return [x for t, v in sorted(by_task.items()) for x in rng.sample(v, quota[t])]


# --- report ---------------------------------------------------------------------------------------


def _row(name: str, outs: list[Outcome], ref: list[Outcome], floor: float) -> list[str]:
    samples = B.resample_indices(len(outs))
    s = summarize(outs)
    alo, ahi = B.mean_ci([float(o.correct) for o in outs], samples)
    lines = [
        f"      {name:<22} acc {s['accuracy']:.3f} [{alo:.3f}, {ahi:.3f}]  floor {floor:.3f} "
        f"{'met' if s['accuracy'] >= floor else 'MISSED':<6}  success {s['success_rate']:.3f}"
    ]
    for key, field, label in (
        ("cost_nocache", "cpst_nocache", "headline"),
        ("cost_cached", "cpst_cached", "cached"),
    ):
        cost, succ = [getattr(o, key) for o in outs], [float(o.success) for o in outs]
        if s[field] == float("inf"):
            lines.append(f"          CPST {label:<8} no successes")
            continue
        lo, hi = B.cpst_ci(cost, succ, samples)
        r = summarize(ref)[field]
        rlo, rhi = B.paired_diff_ci(([getattr(o, key) for o in ref], [float(o.success) for o in ref]), (cost, succ),
                                    samples, relative=True)  # fmt: skip
        lines.append(
            f"          CPST {label:<8} ${s[field]:.5f} [{lo:.5f}, {hi:.5f}]  vs B1 {(r - s[field]) / r:+.1%} "
            f"[{rlo:+.1%}, {rhi:+.1%}]"
        )
    return lines


def cross_fold(fc: FrozenChoices, tickets: list[Ticket], index: CellIndex) -> tuple[list[str], dict]:
    folds = stratified_folds(tickets)
    scored: dict[str, dict[str, Outcome]] = {"frozen O1": {}, "recalibrated": {}, "fail-safe": {}, "B1": {}}
    lines = []
    for i, (audit, score) in enumerate(((folds[0], folds[1]), (folds[1], folds[0]))):
        r = recalibrate(fc, audit, index)
        lines += [
            f"  fold {'AB'[i]} audits (n={len(audit)}), fold {'BA'[i]} is scored (n={len(score)})",
            "    drift detection (frozen O1 on the audit sample vs frozen floor): "
            + ", ".join(
                f"{t} {r.sample_accuracy[t]:.3f} naive {'FIRED' if r.drift[t] else 'ok'} / "
                f"binomial {'FIRED' if r.drift_binomial[t] else 'ok'}"
                for t in TASKS
            ),
            "    re-picked: "
            + ", ".join(
                f"{t} {fc.static[t]}->{r.picks[t]}{' (floor unreachable on this traffic)' if r.unreachable[t] else ''}"
                for t in TASKS
            ),
            f"    adjudicate ladder: {'cascade kept' if r.cascade_kept else 'cascade dropped (missed the floor on the sample)'}"
            f", top {r.picks['adjudicate']}",
            "    fail-safe (D4.7): "
            + ", ".join(
                f"{t} {fc.b1 + ' (binomial alarm)' if r.drift_binomial[t] else fc.static[t] + ' (no alarm, frozen)'}"
                for t in TASKS
            ),
            "    scored-fold n per task: "
            + ", ".join(f"{t} {sum(x.task_type == t for x in score)}" for t in TASKS),
        ]
        for o in frozen_o1(fc, score, index):
            scored["frozen O1"][o.ticket_id] = o
        for o in run_adapted(r.adapted, score, index):
            scored["recalibrated"][o.ticket_id] = o
        for o in run_adapted(failsafe(fc, r), score, index):
            scored["fail-safe"][o.ticket_id] = o
        for o in run_policy(lambda t: (fc.b1,), score, index, fc.floors):
            scored["B1"][o.ticket_id] = o
    return lines, scored


def binomial_drift(correct: int, n: int, floor: float, alpha: float = ALPHA) -> bool:
    """One-sided exact binomial test: fire iff P(X <= correct | n, p = floor) < alpha, i.e. the sample is
    unlikely if the true accuracy were at the floor."""
    if n == 0:
        return False
    p = sum(math.comb(n, k) * floor**k * (1 - floor) ** (n - k) for k in range(correct + 1))
    return p < alpha


DETECTORS = {
    "naive": lambda k, n, f: n > 0 and k / n < f,  # sample accuracy below the floor
    "binomial": binomial_drift,  # statistically guarded (alpha = 0.05)
}


def detection_table(fc: FrozenChoices, splits: dict[str, tuple[list[Ticket], CellIndex]]) -> list[str]:
    lines = [
        f"Audit sample size vs drift detection ({RESAMPLES} stratified resamples per size). On shifted a firing is",
        "a DETECTION (the drift is real, D4.2); on dev it is a FALSE ALARM (O1 meets every floor on dev).",
        "Detectors on frozen O1's per-task result in the sample: naive = sample accuracy below the frozen floor;",
        f"binomial = one-sided exact binomial test rejects 'accuracy >= floor' at alpha {ALPHA}.",
        f"    {'split':<9}{'n':>5}{'faq n':>7}{'adj n':>7}  {'detector':<10}{'faq fires':>11}{'adj fires':>11}"
        f"{'either fires':>14}",
    ]
    for split, (tickets, index) in splits.items():
        outs = {o.ticket_id: o for o in frozen_o1(fc, tickets, index)}
        for n in SAMPLE_SIZES:
            rng = random.Random(f"{SEED}:{split}:{n}")
            fires = {d: {"faq": 0, "adjudicate": 0, "either": 0} for d in DETECTORS}
            sizes: dict[str, int] = {}
            for _ in range(RESAMPLES):
                sample = stratified_sample(tickets, n, rng)
                counts = {}
                for t in ("faq", "adjudicate"):
                    sub = [outs[x.id] for x in sample if x.task_type == t]
                    sizes[t] = len(sub)
                    counts[t] = (sum(o.correct for o in sub), len(sub))
                for d, fn in DETECTORS.items():
                    hit = {t: fn(*counts[t], fc.floors.per_task[t].floor) for t in counts}
                    for t in hit:
                        fires[d][t] += hit[t]
                    fires[d]["either"] += hit["faq"] or hit["adjudicate"]
            for d in DETECTORS:
                f = fires[d]
                lines.append(
                    f"    {split:<9}{n:>5}{sizes['faq']:>7}{sizes['adjudicate']:>7}  {d:<10}"
                    f"{f['faq'] / RESAMPLES:>11.1%}{f['adjudicate'] / RESAMPLES:>11.1%}{f['either'] / RESAMPLES:>14.1%}"
                )
    return lines


def report() -> str:
    from engine.eval.baselines import index_cells
    from engine.eval.cells import build_cells
    from engine.eval.data import load_split
    from engine.eval.scenarios import RUNS
    from engine.policy.frozen import frozen_choices

    fc = frozen_choices()
    data = {}
    for split in ("shifted", "dev"):
        tickets = sorted(load_split(split), key=lambda t: t.id)
        cells, problems = build_cells([RUNS[split]], tickets)
        if problems:
            raise RuntimeError(problems[0])
        data[split] = (tickets, index_cells(cells))
    tickets, index = data["shifted"]
    fold_lines, scored = cross_fold(fc, tickets, index)
    lines = [
        LABEL,
        "",
        "Audit-and-recalibrate on shifted, 2 folds stratified by task x language (seed "
        f"{SEED}): audit fold A -> score fold B, then swap; every ticket is scored once, by the policy calibrated on",
        "the OTHER fold. Floors and budgets are the frozen ones. Selection rules: src/engine/eval/recalibrate.py.",
        "Detector history: the statistical (binomial, alpha 0.05) detector was added AFTER the naive check (sample",
        "accuracy below the floor) falsely alarmed on dev, where O1 meets every floor (see the audit-size table).",
        "Fail-safe (D4.7, added after observing shifted; selects nothing from shifted): a task whose binomial",
        "detector fires on the audit fold reverts to B1's config (chosen on dev) on the scored fold.",
        "",
        *fold_lines,
        "",
        "Per task, pooled over both scored folds (CI = 95% bootstrap; 'vs B1' = CPST saving vs B1, paired;",
        "n per fold in each task header = scored tickets in fold B (audited on A) + fold A (audited on B))",
    ]
    for t in TASKS:
        ids = [x.id for x in tickets if x.task_type == t]
        b1 = [scored["B1"][i] for i in ids]
        per_fold = " + ".join(
            str(sum(x.task_type == t for x in f)) for f in reversed(stratified_folds(tickets))
        )
        lines.append(f"  {t} (n={len(ids)} = {per_fold})")
        for name in ("frozen O1", "recalibrated", "fail-safe", "B1"):
            lines += _row(name, [scored[name][i] for i in ids], b1, fc.floors.per_task[t].floor)
    lines.append("  overall (n=200)")
    for name in ("frozen O1", "recalibrated", "fail-safe", "B1"):
        s = summarize([scored[name][x.id] for x in tickets])
        lines.append(
            f"      {name:<22} acc {s['accuracy']:.3f}  success {s['success_rate']:.3f}  "
            f"CPST headline ${s['cpst_nocache']:.5f}  cached ${s['cpst_cached']:.5f}"
        )
    lines += ["", *detection_table(fc, data), "", LABEL]
    return "\n".join(lines)
