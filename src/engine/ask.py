"""`engine ask`: one fresh demo ticket through the frozen O1, LIVE (real calls, real cost, wall-clock latency).

- Tickets: data/demo/tickets.jsonl (5 fresh tickets, datagen/demo_tickets.py; not in any evaluated split).
- O1 runs through `policy.live.run_ticket`, the code path of the held-out live run. `--compare` also sends the
  same ticket to B1 (always-best, opus-low) and prints both side by side.
- `--rules v2` points the request at the v2 policy document (policy-change scenario); when that differs from the
  ticket's own rules version the gold label does not apply, so the answer is shown ungraded.
- Money: the estimate is printed first; spending needs `--yes`. All `engine ask` runs together are capped at
  DEMO_CAP_USD (summed from the ledger over run ids `demo-*`); each run gets its own RunBudget on top.
- `--replay` (or no API key): the recorded responses from an earlier live `ask` are returned from cassettes/
  (same request keys, epoch ASK_REPEAT); if none were recorded, it says so. The key is never printed.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from engine.contracts import Ticket
from engine.datagen.demo_tickets import load as load_demo
from engine.eval.cells import Cell
from engine.policy.cascade import O1Options
from engine.policy.live import LiveCall, make_caller, run_ticket
from engine.report import collect as C
from engine.report import theme as T
from engine.report.render import fmt_value

DEMO_CAP_USD = 1.00  # all `engine ask` runs together (Hamzah, Phase 5)
ASK_REPEAT = 3  # recording epoch: matrix = 1, held-out live = 2, ask = 3 (never served from other runs)
WIDTH = 100


def demo_spent() -> float:
    from engine.llm.client import Ledger

    return sum(
        e.cost_usd for e in Ledger().entries() if e.run_id.startswith("demo-") and e.provider == "anthropic"
    )


def has_key() -> bool:
    from dotenv import load_dotenv

    from engine.llm.pricing import ROOT

    load_dotenv(ROOT / ".env", override=False)
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def plan(t: Ticket, o: O1Options, static: dict[str, str], b1: str, compare: bool) -> list[str]:
    """Configs that may be called (worst case: the adjudicate ladder escalates)."""
    cfgs = [o.first, o.second, o.top] if t.task_type == "adjudicate" else [static[t.task_type]]
    return cfgs + ([b1] if compare else [])


def estimate(t: Ticket, cfgs: list[str]):
    from engine.eval import estimate as E
    from engine.eval.matrix import cell_request
    from engine.tasks.request import configs

    by_id = {cid: (m, e) for m, e, cid in configs()}
    reqs = [(t.task_type, cell_request((t, *by_id[c]), ASK_REPEAT)) for c in cfgs]
    return E.estimate_requests(reqs, concurrency=len(reqs))


def _caller_recording(caller, seen: dict[str, Cell]):
    def call(ticket, config_id, role) -> LiveCall:
        r = caller(ticket, config_id, role)
        if r.cell is not None:
            seen[config_id] = r.cell
        return r

    return call


def _summary(name: str, color: str, cost_n: float, cost_c: float, ms: float, correct: bool | None, budget: float,
             path: list[str]) -> Table:  # fmt: skip
    g = Table.grid(padding=(0, 2))
    for _ in range(5):
        g.add_column()
    verdict = (
        Text("not graded (rules override)", style=T.MUTED)
        if correct is None
        else Text("✓ correct" if correct else "✗ wrong", style=T.GOOD if correct else T.BAD)
    )
    in_budget = ms <= budget * 1000
    g.add_row(
        Text(name, style=f"bold {color}"),
        Text(" → ".join(path)),
        Text(f"{fmt_value(cost_n, 'usd5')} headline / {fmt_value(cost_c, 'usd5')} billed"),
        Text(
            f"{fmt_value(ms / 1000, 's2')} ({'in' if in_budget else 'over'} {fmt_value(budget, 's1')} budget)",
            style=T.GOOD if in_budget else T.BAD,
        ),  # fmt: skip
        verdict,
    )
    return g


def run(ticket_id: str, *, compare: bool, rules: str | None, replay: bool, yes: bool, cap: float,
        console: Console | None = None) -> int:  # fmt: skip
    from engine.llm.client import LLMClient, ReplayMiss, RunBudget

    con = console or Console(width=WIDTH, highlight=False)
    m = C.load()
    tickets = {t.id: t for t in load_demo()}
    if ticket_id not in tickets:
        con.print(f"unknown demo ticket {ticket_id!r}; choose from: {', '.join(sorted(tickets))}")
        return 2
    t = tickets[ticket_id]
    graded = rules is None or rules == t.rules_version
    if not graded:
        t = t.model_copy(update={"rules_version": rules})
    static = {k: m["o1_config"][k] for k in ("faq", "intent", "extract", "adjudicate")}
    b1, o = m["o1_config"]["b1"], O1Options()
    floors = _floors()
    budget = floors.per_task[t.task_type].budget_s
    mode = "replay" if (replay or not has_key()) else "live"
    con.print(Panel(Text.assemble(
        (f"{t.id} · {t.task_type} · {'Arabic' if t.language == 'ar' else 'English'} · rules {t.rules_version}", "bold"),
        "\n", (" ".join(t.text.split()), "italic"),
        "\n", ("Fictional insurer and ticket; not official rules or legal advice.", T.WARN),
    ), border_style=T.ACCENT, width=WIDTH))  # fmt: skip
    if mode == "replay":
        con.print(Text("replay: returning the responses recorded by an earlier live `engine ask` (no key, no cost)"
                       + ("" if replay else " - no ANTHROPIC_API_KEY found"), style=T.MUTED))  # fmt: skip
    else:
        est = estimate(t, plan(t, o, static, b1, compare))
        left = DEMO_CAP_USD - demo_spent()
        con.print(Text(
            f"estimate: {fmt_value(est.cost_with_caching, 'usd4')} billed (with caching) · "
            f"{fmt_value(est.cost_without_caching, 'usd4')} headline · worst case {fmt_value(est.worst_case, 'usd4')}"
            f" · demo budget left {fmt_value(left, 'usd4')} of {fmt_value(DEMO_CAP_USD, 'usd2')}", style=T.MUTED))  # fmt: skip
        if est.cost_with_caching > min(left, cap):
            con.print(Text("refused: the estimate exceeds the remaining demo budget or --cap", style=T.BAD))
            return 2
        if not yes:
            con.print(Text("dry run: add --yes to make these live calls", style=T.MUTED))
            return 0
    run_id = f"demo-{ticket_id}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    client = LLMClient(
        mode, run_id, run_budget=RunBudget({"anthropic": min(cap, DEMO_CAP_USD - demo_spent())})
    )
    seen: dict[str, Cell] = {}
    caller = _caller_recording(make_caller(client, ASK_REPEAT), seen)
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            res = run_ticket(t, caller, floors, static, o, pool)
            b1_res = None
            if compare:
                import time

                start = time.perf_counter()
                r = caller(t, b1, "answer")
                b1_res = (r, (time.perf_counter() - start) * 1000)
    except ReplayMiss:
        con.print(
            Text("no recording of this ticket yet: run it live once with an API key (`--yes`)", style=T.BAD)
        )
        return 1
    out, trace = res.outcome, res.trace
    if mode == "replay":
        # wall clock of a replay is meaningless: score the recorded calls with the replay cascade instead
        # (recorded latencies, modelled parallel timing), labelled simulated
        from engine.eval.baselines import index_cells
        from engine.policy.cascade import run_o1

        outs, traces = run_o1([t], index_cells(list(seen.values())), floors, static, o)
        out, trace = outs[0], (traces[0] if traces else None)
        if b1_res is not None and b1_res[0].cell is not None:
            b1_res = (b1_res[0], b1_res[0].cell.latency_ms)
        con.print(
            Text(f"latency below = recorded call latencies ({T.SIMULATED} parallel timing)", style=T.MUTED)
        )
    con.print(_summary("O1", T.ACCENT, out.cost_nocache, out.cost_cached, out.latency_ms,
                       out.correct if graded else None, budget, list(out.path)))  # fmt: skip
    if trace is not None and trace.escalated:
        con.print(Text(f"   escalated: {trace.reason}", style=T.GOLD))
    final = seen.get(out.path[-1])
    if final is not None:
        con.print(Text("   checks " + " ".join(f"{v} {'✗' if v in final.failed_checks else '✓'}"
                                             for v in ("V0", "V1", "V2")), style=T.MUTED))  # fmt: skip
    if b1_res is not None:
        r, ms = b1_res
        c = r.calls[0]
        ok = (r.cell.correct if r.cell else False) if graded else None
        con.print(_summary("B1", T.INK_2, c.cost_usd_nocache, c.cost_usd, ms, ok, budget, [b1]))
        if c.cost_usd_nocache > 0:
            con.print(Text(f"   O1 cost {fmt_value(out.cost_nocache / c.cost_usd_nocache, 'pct1')} of B1 on this ticket "
                           f"({T.HEADLINE})", style=T.MUTED))  # fmt: skip
    spent = sum(x.cost_usd for x in res.calls) + (b1_res[0].calls[0].cost_usd if b1_res else 0.0)
    con.print(Text(f"run {run_id} · {mode} · billed {fmt_value(spent, 'usd5')} (with caching)"
                   if mode == "live" else f"run {run_id} · replay · no cost", style=T.MUTED))  # fmt: skip
    return 0


def _floors():
    from engine.demo import _floors as f

    return f()
