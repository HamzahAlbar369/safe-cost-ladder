"""`engine final` (SPEC §7.6): the one held-out run, part of the frozen code.

Order is the protection:
1. `guard()`: HEAD must carry a `freeze-*` tag and the tree must have no code changes (run outputs under
   runs/, cassettes/, reports/ excepted, D2.6). Nothing touches held-out before this passes.
2. `load_heldout(token)`: only with the guard's token; the file's sha256 must equal MANIFEST `heldout_sealed`.
3. estimate (printed by the CLI) -> explicit `--yes` and a cap >= the estimate.
4. O1 live on held-out (separate recording epoch, so never served from matrix cassettes), then the 9-config
   held-out matrix (baselines, oracle, simulated O1), then the simulated-vs-live report.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from engine import runinfo
from engine.contracts import Frozen, Ticket
from engine.eval import estimate as E
from engine.eval.data import GENERATED
from engine.llm.pricing import ROOT

FREEZE_PREFIX = "freeze-"
HELDOUT = GENERATED / "heldout.jsonl"
MANIFEST = GENERATED / "MANIFEST.json"
MATRIX_REPEAT = 1  # same recording epoch as the dev and shifted matrices
LIVE_REPEAT = 2  # O1 live: distinct cassette keys, so every live call is really sent
DEV_ESCALATION_RATE = 11 / 180  # O1 adjudicate escalations on dev (reports/phase3/o1.txt); estimate only


class FinalRefused(RuntimeError):
    pass


class GuardToken(Frozen):
    tag: str
    sha: str


def freeze_tags() -> list[str]:
    return [t for t in runinfo._git("tag", "--points-at", "HEAD").split() if t.startswith(FREEZE_PREFIX)]


def guard() -> GuardToken:
    """Refuse unless HEAD is a clean commit tagged freeze-*. Reads git only, never data."""
    changes = runinfo.code_changes()
    if changes:
        raise FinalRefused(f"engine final refused: working tree has code changes ({changes[0][3:]}, ...)")
    tags = freeze_tags()
    if not tags:
        raise FinalRefused("engine final refused: HEAD carries no freeze-* tag (tagged only with sign-off)")
    return GuardToken(tag=sorted(tags)[-1], sha=runinfo._git("rev-parse", "HEAD").strip())


def load_heldout(token: GuardToken, path: Path = HELDOUT, manifest: Path = MANIFEST) -> list[Ticket]:
    if not isinstance(token, GuardToken):
        raise FinalRefused("held-out needs the token from guard()")
    raw = path.read_bytes()
    sealed = json.loads(manifest.read_text(encoding="utf-8"))["heldout_sealed"]["sha256"]
    if hashlib.sha256(raw).hexdigest() != sealed:
        raise FinalRefused("held-out file does not match its sealed sha256 in MANIFEST.json")
    return [Ticket.model_validate_json(x) for x in raw.decode("utf-8").splitlines() if x.strip()]


def run_ids(token: GuardToken) -> tuple[str, str]:
    """(matrix run, O1 live run)."""
    return f"matrix-heldout-{token.tag}", f"o1-live-heldout-{token.tag}"


def live_outcomes(token: GuardToken) -> int:
    """Outcomes already written by this tag's O1 live run (0 = not started)."""
    path = ROOT / "runs" / run_ids(token)[1] / "outcomes.jsonl"
    return sum(1 for x in path.read_text("utf-8").splitlines() if x.strip()) if path.exists() else 0


class FinalEstimate(Frozen):
    o1_live: E.Estimate
    matrix: E.Estimate
    total_with_caching: float
    worst_case: float


def _by_id() -> dict[str, tuple[str, str]]:
    from engine.tasks.request import configs

    return {cid: (m, e) for m, e, cid in configs()}


def estimate(tickets: list[Ticket], token: GuardToken, static: dict[str, str], o1) -> FinalEstimate:
    from engine.eval import matrix as M
    from engine.llm.client import CassetteStore

    by_id = _by_id()

    def req(t: Ticket, cid: str):
        return (t.task_type, M.cell_request((t, *by_id[cid]), LIVE_REPEAT))  # type: ignore[arg-type]

    live = []
    for t in tickets:
        if t.task_type == "adjudicate":
            live += [req(t, o1.first), req(t, o1.second)]
        else:
            live.append(req(t, static[t.task_type]))
    adj = [t for t in tickets if t.task_type == "adjudicate"]
    top = E.estimate_requests([req(t, o1.top) for t in adj], concurrency=4)
    base = E.estimate_requests(live, concurrency=4)
    rate = DEV_ESCALATION_RATE
    o1_est = base.model_copy(
        update={
            "cost_with_caching": base.cost_with_caching + rate * top.cost_with_caching,
            "cost_without_caching": base.cost_without_caching + rate * top.cost_without_caching,
            "worst_case": base.worst_case + top.worst_case,
            "assumptions": {**base.assumptions, "escalation": f"dev rate {rate:.3f} x {o1.top}"},
        }
    )
    matrix_run, _ = run_ids(token)
    done = M.load_done(M.runs_dir(matrix_run) / "calls.jsonl")
    pending = M.pending_live(M.plan_cells(tickets), CassetteStore(), done, MATRIX_REPEAT)
    mx = E.estimate_requests(
        [(c[0].task_type, M.cell_request(c, MATRIX_REPEAT)) for c in pending], concurrency=18
    )
    return FinalEstimate(
        o1_live=o1_est,
        matrix=mx,
        total_with_caching=o1_est.cost_with_caching + mx.cost_with_caching,
        worst_case=o1_est.worst_case + mx.worst_case,
    )


def _one_per_task_version(tickets: list[Ticket]) -> list[Ticket]:
    seen: dict[tuple[str, str], Ticket] = {}
    for t in tickets:
        seen.setdefault((t.task_type, t.rules_version), t)
    return list(seen.values())


def run_o1_live(
    token: GuardToken, tickets: list[Ticket], cap_usd: float, progress=print, concurrency: int = 4
):
    """O1 live on every held-out ticket -> runs/<o1 run>/calls.jsonl + outcomes.jsonl. Not resumable on
    purpose: held-out O1 runs once (a crash leaves a partial log, which the report labels as partial)."""
    from engine.eval.matrix import _Sink, _warm_up
    from engine.llm.client import LLMClient, RunBudget
    from engine.policy.frozen import frozen_choices
    from engine.policy.live import make_caller, run_live

    _, run_id = run_ids(token)
    out = ROOT / "runs" / run_id
    if (out / "outcomes.jsonl").exists():
        raise FinalRefused(f"{run_id} already exists: held-out O1 runs once")
    fc = frozen_choices()
    client = LLMClient("live", run_id, run_budget=RunBudget({"anthropic": cap_usd}))
    sink = _Sink(out / "calls.jsonl")
    by_id = _by_id()
    used = sorted({*fc.static.values(), fc.o1.first, fc.o1.second, fc.o1.top})
    # same warm-up as the matrix: connections first, then one tiny call per (model, task, version) prefix
    client.warm_connections(2 * concurrency)
    warm = [(t, *by_id[c]) for t in _one_per_task_version(tickets) for c in used]
    _warm_up(warm, client, sink, progress)  # type: ignore[arg-type]
    outcomes_f = (out / "outcomes.jsonl").open("w", encoding="utf-8")
    n = 0

    def on_result(r) -> None:
        nonlocal n
        for c in r.calls:
            sink.write(c)
        outcomes_f.write(r.outcome.model_dump_json() + "\n")
        outcomes_f.flush()
        n += 1
        if n % 25 == 0 or n == len(tickets):
            progress(f"  O1 live {n}/{len(tickets)} | spend ${client.run_budget.spent['anthropic']:.4f}")

    caller = make_caller(client, LIVE_REPEAT)
    try:
        results = run_live(
            tickets, caller, fc.floors, fc.static, fc.o1, concurrency=concurrency, on_result=on_result
        )
    finally:
        outcomes_f.close()
        sink.close()
    return run_id, results


def run_matrix(
    token: GuardToken, tickets: list[Ticket], cap_usd: float, progress=print, concurrency: int = 6
):
    from engine.eval import matrix as M

    matrix_run, _ = run_ids(token)
    return M.run_matrix(
        "heldout",
        tickets,
        mode="auto",
        run_id=matrix_run,
        cap_usd=cap_usd,
        per_model_concurrency=concurrency,
        repeat=MATRIX_REPEAT,
        git_sha=token.sha,
        progress=progress,
    )


def report(token: GuardToken, tickets: list[Ticket]) -> Path:
    """Held-out results: baselines and the simulated O1 (replay of the held-out matrix) vs live O1."""
    from engine.eval.baselines import Outcome, summarize
    from engine.eval.phase3_report import CAVEATS, per_task_lines, policy_block
    from engine.eval.phase4_report import SplitContext, baselines_table, breakdown

    matrix_run, live_run = run_ids(token)
    ctx = SplitContext(matrix_run, "heldout", tickets=tickets)
    sim, _ = ctx.o1()
    rows = (ROOT / "runs" / live_run / "outcomes.jsonl").read_text("utf-8").splitlines()
    by_id = {o.ticket_id: o for o in (Outcome.model_validate_json(x) for x in rows if x.strip())}
    live = [by_id[t.id] for t in ctx.tickets if t.id in by_id]
    complete = len(live) == len(ctx.tickets)
    sim_by = {o.ticket_id: o for o in sim}
    paired_sim = [sim_by[o.ticket_id] for o in live]
    lines = [
        f"run: {matrix_run} + {live_run} | split: heldout | tag: {token.tag} | git: {token.sha}",
        "",
        f"Held-out (n={len(ctx.tickets)}; live O1 outcomes: {len(live)}"
        + ("" if complete else ", PARTIAL")
        + "). Configs, floors and budgets frozen on dev.",
        "",
        *baselines_table(ctx, sim),
        "",
        *policy_block("O1 simulated (replay of the held-out matrix)", sim, {"B1": ctx.b1, "B3": ctx.b3}, ctx),
        "",
        "Simulated vs live O1 (SPEC 7.5; live = real calls, real parallelism, wall-clock latency)",
        f"    {'':<12}{'n':>5}{'acc':>8}{'success':>9}{'p95 s':>8}{'CPST headline':>15}{'CPST cached':>13}",
    ]
    for name, outs in (("simulated", paired_sim), ("live", live)):
        s = summarize(outs)
        lines.append(
            f"    {name:<12}{len(outs):>5}{s['accuracy']:>8.3f}{s['success_rate']:>9.3f}{s['p95_s']:>8.2f}"
            f"{s['cpst_nocache']:>15.5f}{s['cpst_cached']:>13.5f}"
        )
    same_correct = sum(a.correct == b.correct for a, b in zip(paired_sim, live, strict=True))
    same_path = sum(a.path == b.path for a, b in zip(paired_sim, live, strict=True))
    lines += [
        f"    same correctness on {same_correct}/{len(live)} tickets; same path on {same_path}/{len(live)}"
    ]
    if complete:
        lines += ["", "Per task (O1 live)", *per_task_lines(live, ctx), "", *breakdown("O1 live", live, ctx)]
    lines += ["", *CAVEATS]
    out = ROOT / "reports" / "final" / "heldout.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
