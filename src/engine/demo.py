"""`engine demo --replay`: the judge-facing walk-through, no API key needed.

Each demo ticket (the declared demo set in reports/metrics.json, chosen by rule in report/collect.py: demo_set) is
answered by the frozen O1 logic over RECORDED responses (cassettes/), so every answer, cost and latency shown is
the one actually billed and measured on dev. The closing table prints the held-out headline from
reports/metrics.json with the report's own formatter; `--verify` recomputes every metric from the committed runs
and checks it equals that file.
"""

from __future__ import annotations

import json
import time

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from engine.contracts import LLMResponse, Ticket
from engine.eval.baselines import index_cells
from engine.eval.cells import Cell, cells_from_calls, read_calls
from engine.eval.data import load_split
from engine.eval.floors import Floors, TaskFloor
from engine.policy.cascade import O1Options, agree, run_o1
from engine.policy.controller import load_policy
from engine.report import collect as C
from engine.report import theme as T
from engine.report.render import fmt_value

WIDTH = 100
ORDER = ("faq", "intent", "extract", "adjudicate", "escalated")
ACC, GOLD, B1C, GOOD, BAD, MUTED = T.ACCENT, T.GOLD, "#8a8882", "#2e9e2e", T.BAD, "#898781"


def _floors() -> Floors:
    """The frozen floors and budgets (config/policy.yaml, tag floors-v1); only floor and budget are used."""
    cfg = load_policy()
    return Floors(
        per_task={
            t: TaskFloor(
                task=t,
                n=0,
                best_config="",
                best_accuracy=0.0,
                tolerance=0.0,
                floor=cfg.floors[t],
                budget_config="",
                p95_s=0.0,
                budget_s=cfg.latency_budget_s[t],
                tied_best=(),
            )  # fmt: skip
            for t in cfg.floors
        }
    )


def _answer(cell: Cell, store, hashes: dict) -> str:
    cas = store.get("anthropic", hashes[(cell.ticket_id, cell.config_id)])
    text = LLMResponse.model_validate(cas.response).text if cas else ""
    try:
        d = json.loads(text)
        d.pop("inputs", None)
        d.pop("reasons", None)
        text = json.dumps(d, ensure_ascii=False)
    except (ValueError, AttributeError):
        pass
    return text if len(text) <= 78 else text[:75] + "..."


def _check_marks(cell: Cell) -> Text:
    t = Text()
    for v in ("V0", "V1", "V2"):
        ok = v not in cell.failed_checks
        t.append(f"{v} {'✓' if ok else '✗'}  ", style=GOOD if ok else BAD)
    return t


def _rung(label: str, cell: Cell, color: str, note: str = "") -> Table:
    g = Table.grid(padding=(0, 1))
    g.add_column(width=27)
    g.add_column(width=19)
    g.add_column(justify="right", width=11)
    g.add_column(justify="right", width=10)
    g.add_column(justify="right", width=8)
    g.add_row(
        Text(f"┃ {label}", style=f"bold {color}"),
        _check_marks(cell) if cell.task == "adjudicate" else Text("no checks (static)", style=MUTED),
        Text(fmt_value(cell.cost_usd_nocache, "usd5")),
        Text(fmt_value(cell.cost_usd, "usd5"), style=MUTED),
        Text(fmt_value(cell.latency_ms / 1000, "s2")),
    )
    if note:
        g.add_row(Text(f"┃   {note}", style=MUTED), "", "", "", "")
    return g


def ticket_panel(t: Ticket, out, trace, index, floors: Floors, o: O1Options, store, hashes) -> Panel:
    cells = [index[(t.id, cfg)] for cfg in out.path]
    head = Table.grid(padding=(0, 1))
    head.add_column(width=27)
    head.add_column(width=19)
    head.add_column(justify="right", width=11)
    head.add_column(justify="right", width=10)
    head.add_column(justify="right", width=8)
    head.add_row(*(Text(h, style=MUTED) for h in ("rung", "checks", "headline $", "cached $", "latency")))
    rows: list = [head]
    if t.task_type == "adjudicate":
        a, b = index[(t.id, o.first)], index[(t.id, o.second)]
        rows.append(
            _rung(f"{o.first} ‖ {o.second}", a, ACC, f"{o.second}: {fmt_value(b.latency_ms / 1000, 's2')}")
        )
        v3 = (
            Text("V3 second opinion late → decide on V0-V2", style=MUTED)
            if trace.second_late
            else Text("V3 both Haikus agree ✓", style=GOOD)
            if agree(a, b)
            else Text("V3 Haikus disagree ✗", style=BAD)
        )
        rows.append(Text("┃   ") + v3)
        if trace.escalated:
            rows.append(Text(f"┃   ▲ escalate: {trace.reason}", style=f"bold {GOLD}"))
            rows.append(_rung(o.top, index[(t.id, o.top)], GOLD))
    else:
        rows.append(_rung(cells[0].config_id, cells[0], ACC))
    final = cells[-1]
    budget = floors.per_task[t.task_type].budget_s
    verdict = Text()
    verdict.append("✓ correct" if out.correct else "✗ wrong", style=f"bold {GOOD if out.correct else BAD}")
    verdict.append(
        f"   latency {fmt_value(out.latency_ms / 1000, 's2')} / budget {fmt_value(budget, 's1')} ",
        style=MUTED,
    )
    verdict.append("✓ in budget" if out.success else "✗ over budget", style=GOOD if out.success else BAD)
    verdict.append(f"   total {fmt_value(out.cost_nocache, 'usd5')} headline", style="bold")
    text = " ".join(t.text.split())
    body = Group(
        Text(text if len(text) <= 190 else text[:187] + "...", style="italic"),
        Text(""),
        *rows,
        Text(""),
        Text("answer  ", style=MUTED) + Text(_answer(final, store, hashes)),
        verdict,
    )
    title = f"[bold]{t.id}[/] · {t.task_type} · {'Arabic' if t.language == 'ar' else 'English'}"
    return Panel(body, title=title, title_align="left", border_style=ACC, box=box.ROUNDED, width=WIDTH)


def headline_table(m: dict) -> Table:
    H = m["splits"]["heldout"]["policies"]
    tab = Table(title="Held-out (sealed, evaluated once) · CPST = USD per successful task", box=box.SIMPLE_HEAD,
                width=WIDTH, title_style="bold", header_style=MUTED)  # fmt: skip
    for col, j in (("policy", "left"), ("accuracy", "right"), ("success", "right"), ("p95", "right"),
                   (T.HEADLINE, "right"), (T.CACHED, "right"), ("floors", "left")):  # fmt: skip
        tab.add_column(col, justify=j, no_wrap=col == "policy")
    rows = (("B1", "B1 always-best", B1C), ("B2", "B2 always-cheapest", B1C), ("B3", "B3 static per task", B1C),
            ("O1", "O1 (simulated)", ACC), ("O1_live", "O1 (live)", ACC), ("Oracle", "Oracle", GOLD))  # fmt: skip
    for k, name, color in rows:
        e = H[k]
        tab.add_row(
            Text(name, style=f"bold {color}" if k.startswith("O1") else color),
            fmt_value(e["acc"], "f3"),
            fmt_value(e["success"], "f3"),
            fmt_value(e["p95_s"], "s2"),
            fmt_value(e["cpst_nocache"], "usd5"),
            fmt_value(e["cpst_cached"], "usd5"),
            Text("✓ all met", style=GOOD) if e["meets_floors"] else Text("✗ breach", style=BAD),
        )
    return tab


def summary_lines(m: dict) -> Group:
    H, S = m["splits"]["heldout"]["policies"], m["splits"]["shifted"]["policies"]
    live = H["O1_live"]
    t = Text()
    t.append("O1 live vs always-best: ", style="bold")
    t.append(fmt_value(live["saving_nocache"], "pct1"), style=f"bold {ACC}")
    t.append(f" lower CPST ({T.HEADLINE}), 95% CI [{fmt_value(live['saving_nocache_lo'], 'pct1')}, "
             f"{fmt_value(live['saving_nocache_hi'], 'pct1')}]")  # fmt: skip
    D = m["splits"]["dev"]["policies"]
    breached = [sp for sp, P in (("dev", D), ("shifted", S)) if not P["B2"]["meets_floors"]]
    n_breach = sum(not e["meets_floor"] for e in S["O1"]["per_task"].values())
    b2_line = (
        f"B2 always-cheapest {'met every floor' if H['B2']['meets_floors'] else 'breached a floor'} on held-out at "
        f"{fmt_value(H['B2']['cpst_nocache'], 'usd5')} "
        f"({'cheaper' if H['B2']['cpst_nocache'] < live['cpst_nocache'] else 'dearer'} than O1)"
        + (f" but breached floors on {' and '.join(breached)}. " if breached else ". ")
    )
    b2 = Text(
        "Read with it: " + b2_line + f"Live p95 {fmt_value(live['p95_s'], 's2')} vs "
        f"{fmt_value(H['O1']['p95_s'], 's2')} simulated. Shifted: O1 accuracy {fmt_value(S['O1']['acc'], 'f3')} vs B1 "
        f"{fmt_value(S['B1']['acc'], 'f3')} ({n_breach} task floor{'s' if n_breach != 1 else ''} breached).",
        style=MUTED,
    )
    return Group(t, b2)


def run(pause: bool = False, verify: bool = False, console: Console | None = None) -> int:
    con = console or Console(width=WIDTH, highlight=False)
    m = C.load()
    demo = m["demo"]
    con.print(Panel(
        Text.assemble(("Deliver AI with less compute", "bold"), " · replay demo (no API key)\n",
                      ("Fictional insurer, synthetic tickets; not Najm, SAMA or any real insurer rules.\n", T.WARN),
                      ("Every answer below is a recorded response from cassettes/, run through the frozen O1 policy.",
                       MUTED)),  # fmt: skip
        border_style=ACC, width=WIDTH,
    ))  # fmt: skip
    ids = [demo[k] for k in ORDER]
    tickets = {t.id: t for t in load_split("dev") if t.id in ids}
    calls = [
        (m["provenance"]["runs"]["dev"], c)
        for c in read_calls(m["provenance"]["runs"]["dev"])
        if c.ticket_id in ids
    ]
    from engine.llm.client import CassetteStore

    store = CassetteStore()
    hashes = {(c.ticket_id, c.config_id): c.request_hash for _, c in calls if c.role == "answer"}
    cells, problems = cells_from_calls(calls, list(tickets.values()), store)
    if problems:
        con.print(Text(f"replay problem: {problems[0]}", style=BAD))
        return 1
    index, floors = index_cells(cells), _floors()
    static = {t: m["o1_config"][t] for t in ("faq", "intent", "extract", "adjudicate")}
    o = O1Options()
    for key in ORDER:
        t = tickets[demo[key]]
        outs, traces = run_o1([t], index, floors, static, o)
        out, trace = outs[0], (traces[0] if traces else None)
        con.print(ticket_panel(t, out, trace, index, floors, o, store, hashes))
        if pause:
            con.input(Text("  [Enter] next ", style=MUTED))
    con.print(headline_table(m))
    con.print(summary_lines(m))
    p = m["provenance"]
    con.print(Text(f"source: {p['runs']['heldout_matrix']} + {p['runs']['heldout_live']} · held-out run at "
                   f"{p['heldout_tag']} · full report: reports/report.html", style=MUTED))  # fmt: skip
    if verify:
        con.print(
            Text(
                "verifying: recomputing every metric from the committed runs (a few minutes) ...", style=MUTED
            )
        )
        start = time.time()
        fresh = json.loads(json.dumps(C.collect(progress=lambda _: None), default=C._jsonable))
        for d in (fresh, m):
            d["provenance"].pop("build_git_sha", None)
        ok = fresh == m
        con.print(Text(f"{'✓ matches' if ok else '✗ DIFFERS from'} reports/metrics.json ({time.time() - start:.0f} s)",
                       style=f"bold {GOOD if ok else BAD}"))  # fmt: skip
        return 0 if ok else 1
    return 0
