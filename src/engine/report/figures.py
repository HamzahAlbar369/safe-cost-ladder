"""Figures for report.html and reports/figures/*.png, built ONLY from metrics.json.

Every title is GENERATED from the results: a list of segments (plain text, or a (metric key, format) pair)
chosen by a stated condition. The HTML renders the segments through the render helper (data-metric spans);
the PNG renders the same segments with the same formatter, so a finding can't read differently in the two.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from engine.eval.metrics import TASKS
from engine.report import theme as T
from engine.report.collect import lookup
from engine.report.render import fmt_value

Segment = str | tuple[str, str]


@dataclass
class Figure:
    name: str  # file stem under reports/figures/
    title: list[Segment]
    claim: str  # one line for reports/figures/INDEX.md
    sources: list[str]  # run ids
    build: Callable[[dict, T.Size], go.Figure]
    html_height: int = 420


def title_text(m: dict, segs: list[Segment]) -> str:
    return "".join(s if isinstance(s, str) else fmt_value(lookup(m, s[0]), s[1]) for s in segs)


def caption(m: dict, name: str) -> str:
    """run id(s) · git SHA of the build · config hash(es), for the figure `name` (SOURCES below)."""
    p = m["provenance"]
    keys = SOURCES[name]
    runs = " + ".join(p["runs"][k] for k in keys)
    hashes = sorted({p["config_hash"]["heldout" if k.startswith("heldout") else k] for k in keys})
    held = any(k.startswith("heldout") for k in keys)
    sha = f"git {p['build_git_sha'][:12]}" + (
        f" (held-out run at {p['heldout_tag']} {p['heldout_git_sha'][:12]})" if held else ""
    )
    return f"Source: {runs} · {sha} · config {', '.join(hashes)}"


H = "splits.heldout.policies"


# --- 1. CPST forest plot: policy x split, CIs ----------------------------------------------------------

FOREST_ROWS = ("B1", "B3", "B2", "O1_live", "O1", "Oracle")  # top to bottom
FOREST_TICKS = (0.0003, 0.001, 0.003, 0.01, 0.03, 0.1)


def forest_title(m: dict) -> list[Segment]:
    sav = f"{H}.O1_live.saving_nocache"
    segs: list[Segment] = [
        "On held-out, O1 (live) costs ",
        (sav, "pct1"),
        " less per successful task than always-best",
    ]
    b2_meets = lookup(m, f"{H}.B2.meets_floors")
    b2_cheaper = lookup(m, f"{H}.B2.cpst_nocache") < lookup(m, f"{H}.O1_live.cpst_nocache")
    if b2_meets and b2_cheaper:
        segs += ["; always-cheapest is cheaper there but breaches a floor on dev"
                 if not lookup(m, "splits.dev.policies.B2.meets_floors") else "; always-cheapest is cheaper"]  # fmt: skip
    return segs


def forest(m: dict, s: T.Size) -> go.Figure:
    splits = ("dev", "shifted", "heldout")
    fig = make_subplots(rows=1, cols=3, shared_yaxes=True, horizontal_spacing=0.03,
                        subplot_titles=[T.SPLIT_LABEL[x] for x in splits])  # fmt: skip
    rows = list(reversed(FOREST_ROWS))
    labels = {k: T.POLICY[k].label for k in rows}
    vals = []
    for col, sp in enumerate(splits, start=1):
        pols = m["splits"][sp]["policies"]
        for k in rows:
            if k not in pols:
                continue
            e, st = pols[k], T.POLICY[k]
            x, lo, hi = e["cpst_nocache"], e["cpst_nocache_lo"], e["cpst_nocache_hi"]
            vals += [lo, hi]
            meets = e["meets_floors"]
            fig.add_trace(
                go.Scatter(
                    x=[x], y=[labels[k]], mode="markers",
                    error_x={"type": "data", "symmetric": False, "array": [hi - x], "arrayminus": [x - lo],
                             "color": st.color, "thickness": s.line, "width": 0},
                    marker={"size": s.marker * (1.25 if k.startswith("O1") else 1), "symbol": st.symbol
                            if meets or st.symbol.endswith("-open") else st.symbol + "-open", "color": st.color,
                            "line": {"color": st.color, "width": s.line}},
                    hovertemplate=f"{st.label}<br>{T.SPLIT_LABEL[sp]}: %{{x:$.5f}} [{lo:.5f}, {hi:.5f}]"
                    + ("" if meets else "<br>✗ breaches a floor") + "<extra></extra>",
                ),
                row=1, col=col,
            )  # fmt: skip
            if not meets:
                fig.add_annotation(x=math.log10(hi), y=labels[k], text="✗ floor", showarrow=False, xanchor="left",
                                   xshift=6, font={"color": T.BAD, "size": s.small}, row=1, col=col)  # fmt: skip
    lo_all, hi_all = min(vals), max(vals)
    rng = [math.log10(lo_all) - 0.15, math.log10(hi_all) + 0.35]
    for col in (1, 2, 3):
        ticks = [t for t in FOREST_TICKS if rng[0] <= math.log10(t) <= rng[1]]
        fig.update_xaxes(type="log", range=rng, tickvals=ticks, ticktext=[f"${t:g}" for t in ticks], row=1, col=col,
                         title_text="CPST, " + T.HEADLINE + ", log scale" if col == 2 else None,
                         title_font={"size": s.small, "color": T.MUTED})  # fmt: skip
    fig.update_yaxes(tickfont={"size": s.label, "color": T.INK_2}, categoryorder="array",
                     categoryarray=[labels[k] for k in rows])  # fmt: skip
    fig.update_annotations(selector={"text": "dev"}, font={"size": s.label, "color": T.INK})
    T.layout(fig, s, title=title_text(m, forest_title(m)), caption=caption(m, "cpst_forest"), height=430)
    for a in fig.layout.annotations:
        if a.text in ("dev", "shifted", "held-out"):
            a.font = {"size": s.label, "color": T.INK, "family": T.DISPLAY_FONT}
    return fig


# --- 2. spend by task: B1 vs O1 live on held-out -------------------------------------------------------


def spend_title(m: dict) -> list[Segment]:
    k = "splits.heldout.spend_by_task.total"
    return ["Across ", ("splits.heldout.n", "int"), " held-out tickets O1 (live) spent ", (f"{k}.O1_live.nocache", "usd2"), " where always-best spent ",
            (f"{k}.B1.nocache", "usd2"), " (" + T.HEADLINE + ")"]  # fmt: skip


def spend(m: dict, s: T.Size) -> go.Figure:
    d = m["splits"]["heldout"]["spend_by_task"]
    tasks = list(reversed(TASKS))
    fig = go.Figure()
    for k in ("B1", "O1_live"):
        st = T.POLICY[k]
        xs = [d[t][k]["nocache"] for t in tasks]
        fig.add_trace(go.Bar(
            y=tasks, x=xs, orientation="h", name=st.label, marker={"color": st.color, "cornerradius": 4},
            text=[f"{st.label}  {fmt_value(x, 'usd2')}" for x in xs], textposition="outside", cliponaxis=False,
            textfont={"size": s.label, "color": T.INK_2},
            hovertemplate=st.label + " · %{y}: %{x:$.2f} (" + T.HEADLINE + ")<extra></extra>",
        ))  # fmt: skip
    fig.update_layout(barmode="group", bargap=0.35, bargroupgap=0.08)
    xmax = max(d[t]["B1"]["nocache"] for t in TASKS)
    fig.update_xaxes(range=[0, xmax * 1.45], tickprefix="$", title_text="USD spent on held-out, " + T.HEADLINE,
                     title_font={"size": s.small, "color": T.MUTED})  # fmt: skip
    fig.update_yaxes(tickfont={"size": s.label, "color": T.INK_2}, showgrid=False)
    T.layout(fig, s, title=title_text(m, spend_title(m)),
             caption=caption(m, "spend_by_task"))  # fmt: skip
    return fig


# --- 3. Sankey: one adjudicate request, held-out live ---------------------------------------------------

SK = "splits.heldout.sankey"


def sankey_title(m: dict) -> list[Segment]:
    return ["Live on held-out, the Haiku pair settled ", (f"{SK}.accepted", "int"), " of ", (f"{SK}.n", "int"),
            " adjudicate tickets; ", (f"{SK}.escalated", "int"), " went up to opus-low"]  # fmt: skip


def sankey(m: dict, s: T.Size) -> go.Figure:
    d = m["splits"]["heldout"]["sankey"]
    rc = d["rung_cost_nocache"]
    fate_label = {
        "in_budget": "✓ correct, in budget",
        "over_budget": "! correct, over budget",
        "wrong": "✗ wrong",
    }
    fate_color = {"in_budget": T.GOOD, "over_budget": T.WARN, "wrong": T.BAD}
    nodes = [
        f"haiku-low ‖ haiku-medium<br>{d['n']} tickets · {fmt_value(rc['haiku-low'], 'usd4')} + "
        f"{fmt_value(rc['haiku-medium'], 'usd4')} per call",
        f"accepted (checks pass; agreed, or second opinion late)<br>{d['accepted']}",
        f"escalated to opus-low<br>{d['escalated']} · {fmt_value(rc.get('opus-low', 0), 'usd4')} per call",
    ]
    fates = [f for f in fate_label if d["accepted_fate"][f] + d["escalated_fate"][f] > 0]
    nodes += [f"{fate_label[f]}<br>{d['accepted_fate'][f] + d['escalated_fate'][f]}" for f in fates]
    src, tgt, val, col = [0, 0], [1, 2], [d["accepted"], d["escalated"]], [T.ACCENT_SOFT, "#e6d3a8"]
    for i, f in enumerate(fates):
        for parent, key in ((1, "accepted_fate"), (2, "escalated_fate")):
            if d[key][f]:
                (
                    src.append(parent),
                    tgt.append(3 + i),
                    val.append(d[key][f]),
                    col.append(_rgba(fate_color[f], 0.35)),
                )
    fig = go.Figure(go.Sankey(
        arrangement="fixed",
        node={"label": nodes, "pad": 40, "x": [0.001, 0.45, 0.45] + [0.999] * len(fates),
              "y": [0.4, 0.4, 0.93] + [0.35, 0.82, 0.97][: len(fates)], "thickness": 22 if not s.png else 40,
              "color": [T.ACCENT, T.ACCENT, T.GOLD] + [fate_color[f] for f in fates], "line": {"width": 0}},
        link={"source": src, "target": tgt, "value": val, "color": col},
        textfont={"size": s.label, "color": T.INK, "family": T.TEXT_FONT},
    ))  # fmt: skip
    T.layout(fig, s, title=title_text(m, sankey_title(m)), caption=caption(m, "adjudicate_sankey"))
    return fig


def _rgba(hex_: str, a: float) -> str:
    h = hex_.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


# --- 4. effort ----------------------------------------------------------------------------------------


def effort_title(m: dict) -> list[Segment]:
    e = m["effort"]
    sig = [(mo, ef) for mo in e for ef in ("medium", "high") if e[mo][ef]["acc_delta_lo"] > 0]
    worst = max(((mo, ef) for mo in e for ef in ("medium", "high")), key=lambda k: e[k[0]][k[1]]["x_low"])
    segs: list[Segment] = ["Raising effort costs up to ", (f"effort.{worst[0]}.{worst[1]}.x_low", "x2"),
                           " per call (" + T.CACHED + ")"]  # fmt: skip
    segs += ["; no accuracy gain over low effort is significant on dev"] if not sig else \
        ["; a significant accuracy gain only for " + ", ".join(f"{mo}-{ef}" for mo, ef in sig)]  # fmt: skip
    return segs


def effort(m: dict, s: T.Size) -> go.Figure:
    e = m["effort"]
    models = ("haiku", "sonnet", "opus")
    fig = make_subplots(
        rows=1, cols=3, subplot_titles=[x.capitalize() for x in models], horizontal_spacing=0.07
    )
    for col, mo in enumerate(models, start=1):
        effs = ("low", "medium", "high")
        ys = [e[mo][ef]["cost_cached"] for ef in effs]
        text = []
        for ef in effs:
            r = e[mo][ef]
            if ef == "low":
                text.append(f"acc {fmt_value(r['acc'], 'f3')}")
            else:
                text.append(f"{fmt_value(r['x_low'], 'x2')}<br>Δacc {r['acc_delta']:+.3f}<br>"
                            f"[{r['acc_delta_lo']:+.3f}, {r['acc_delta_hi']:+.3f}]")  # fmt: skip
        fig.add_trace(go.Bar(
            x=list(effs), y=ys, marker={"color": [T.ACCENT_SOFT, "#86b6ef", T.ACCENT], "cornerradius": 4},
            text=text, textposition="outside", cliponaxis=False, textfont={"size": s.small, "color": T.INK_2},
            constraintext="none", textangle=0,
            hovertemplate=mo + "-%{x}: %{y:$.6f} per call (" + T.CACHED + ")<extra></extra>",
        ), row=1, col=col)  # fmt: skip
        fig.update_yaxes(range=[0, max(ys) * 1.75], tickformat="$.4f", row=1, col=col)
    fig.update_yaxes(title_text="USD per call, " + T.CACHED, title_font={"size": s.small, "color": T.MUTED},
                     row=1, col=1)  # fmt: skip
    fig.update_xaxes(tickfont={"size": s.label, "color": T.INK_2})
    T.layout(fig, s, title=title_text(m, effort_title(m)), caption=caption(m, "effort"))
    for a in fig.layout.annotations:
        if a.text in ("Haiku", "Sonnet", "Opus"):
            a.font = {"size": s.label, "color": T.INK, "family": T.DISPLAY_FONT}
    fig.update_layout(bargap=0.3)
    return fig


# --- 5. simulated vs live (held-out) --------------------------------------------------------------------


def simlive_title(m: dict) -> list[Segment]:
    sim, live = f"{H}.O1.p95_s", f"{H}.O1_live.p95_s"
    segs: list[Segment] = ["Live p95 latency was ", (live, "s2"), " vs ", (sim, "s2"), " " + T.SIMULATED]
    over = [
        t for t in TASKS if lookup(m, f"{H}.O1_live.per_task.{t}.p95_s") > lookup(m, f"floors.{t}.budget_s")
    ]
    if over:
        segs += [
            "; "
            + " and ".join(over)
            + (" ran" if len(over) == 1 else " ran")
            + " over its latency budget live"
        ]
    return segs


def simlive(m: dict, s: T.Size) -> go.Figure:
    fig = make_subplots(rows=1, cols=2, horizontal_spacing=0.12,
                        subplot_titles=["p95 latency by task (s)", "success rate by task"])  # fmt: skip
    tasks = list(reversed(TASKS))
    for col, field in ((1, "p95_s"), (2, "success")):
        sim = [lookup(m, f"{H}.O1.per_task.{t}.{field}") for t in tasks]
        live = [lookup(m, f"{H}.O1_live.per_task.{t}.{field}") for t in tasks]
        for t, a, b in zip(tasks, sim, live, strict=True):
            fig.add_trace(go.Scatter(x=[a, b], y=[t, t], mode="lines", line={"color": T.AXIS, "width": s.line},
                                     hoverinfo="skip"), row=1, col=col)  # fmt: skip
        fig.add_trace(go.Scatter(x=sim, y=tasks, mode="markers+text", text=[T.SIMULATED] * 4, textposition="top center",
                                 textfont={"size": s.small, "color": T.MUTED},
                                 marker={"size": s.marker, "color": T.SURFACE, "line": {"color": T.ACCENT, "width": s.line}},
                                 hovertemplate=T.SIMULATED + " %{y}: %{x}<extra></extra>"), row=1, col=col)  # fmt: skip
        fig.add_trace(go.Scatter(x=live, y=tasks, mode="markers+text", text=[T.LIVE] * 4, textposition="bottom center",
                                 textfont={"size": s.small, "color": T.ACCENT},
                                 marker={"size": s.marker, "color": T.ACCENT},
                                 hovertemplate=T.LIVE + " %{y}: %{x}<extra></extra>"), row=1, col=col)  # fmt: skip
        if field == "p95_s":
            budgets = [lookup(m, f"floors.{t}.budget_s") for t in tasks]
            fig.add_trace(go.Scatter(x=budgets, y=tasks, mode="markers+text", text=["budget"] + [""] * 3,
                                     textposition="top center", textfont={"size": s.small, "color": T.BAD},
                                     marker={"symbol": "line-ns", "size": s.marker * 1.8, "line": {"color": T.BAD, "width": s.line}},
                                     hovertemplate="budget %{y}: %{x} s<extra></extra>"), row=1, col=col)  # fmt: skip
            fig.update_xaxes(range=[0, max(budgets + live) * 1.25], ticksuffix=" s", row=1, col=col)
        else:
            fig.update_xaxes(
                range=[0, 1.15], tickvals=[0, 0.2, 0.4, 0.6, 0.8, 1.0], tickformat=".0%", row=1, col=col
            )
    fig.update_yaxes(tickfont={"size": s.label, "color": T.INK_2})
    fig.update_annotations(font={"size": s.label, "color": T.INK, "family": T.DISPLAY_FONT})
    T.layout(fig, s, title=title_text(m, simlive_title(m)),
             caption=caption(m, "sim_vs_live"))  # fmt: skip
    return fig


# --- 6. robustness: per-task accuracy vs floor ----------------------------------------------------------

ROB = (
    ("dev", "splits.dev.policies.O1", "O1 · dev (" + T.SIMULATED + ")", "O1"),
    ("heldout", f"{H}.O1_live", "O1 · held-out (" + T.LIVE + ")", "O1_live"),
    ("shifted", "splits.shifted.policies.O1", "O1 · shifted (" + T.SIMULATED + ")", "O1"),
    ("failsafe", "splits.shifted.analysis.failsafe", "fail-safe · shifted (analysis)", "failsafe"),
)
BEST = "best single config · shifted"


def robust_title(m: dict) -> list[Segment]:
    breach = [t for t in TASKS if not lookup(m, f"splits.shifted.policies.O1.per_task.{t}.meets_floor")]
    held_ok = all(lookup(m, f"{H}.O1_live.per_task.{t}.meets_floor") for t in TASKS)
    segs: list[Segment] = [
        "O1 meets every floor on dev and held-out" if held_ok else "O1 misses a floor on held-out"
    ]
    if breach:
        segs += ["; under the shifted traffic it breaches " + " and ".join(breach)]
    return segs


def robust(m: dict, s: T.Size) -> go.Figure:
    tasks = list(TASKS)
    fig = make_subplots(rows=1, cols=4, shared_yaxes=True, horizontal_spacing=0.02, subplot_titles=tasks)
    allv, rows = [], []
    for col, t in enumerate(tasks, start=1):
        fl = lookup(m, f"floors.{t}.floor")
        ys = [r[2] for r in ROB]
        xs = [lookup(m, f"{r[1]}.per_task.{t}.acc") for r in ROB]
        allv += xs + [fl]
        fig.add_shape(type="line", x0=fl, x1=fl, y0=0, y1=1, yref="y domain", line={"color": T.INK_2,
                      "width": s.line, "dash": "dot"}, row=1, col=col)  # fmt: skip
        fig.add_annotation(x=fl, y=1, yref="y domain", text=f"floor {fl:.3f}", showarrow=False, yanchor="bottom",
                           xanchor="right", font={"size": s.small, "color": T.INK_2}, row=1, col=col)  # fmt: skip
        best = lookup(m, f"splits.shifted.best_single.{t}")
        allv.append(best["acc"])
        rows.append((xs, ys, best, fl, t))
    lo = math.floor(min(allv) * 20) / 20 - 0.05
    for col, (xs, ys, best, fl, t) in enumerate(rows, start=1):
        for x, y, r in zip(xs, ys, ROB, strict=True):
            ok = x >= fl
            st = T.POLICY[r[3]]
            fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers", marker={"size": s.marker, "color": st.color, "symbol": st.symbol},
                                     hovertemplate=f"{r[2]} · {t}: {x:.3f} vs floor {fl:.3f}<extra></extra>"), row=1, col=col)  # fmt: skip
            fig.add_annotation(x=lo, y=y, text=("✓ " if ok else "✗ ") + f"{x:.3f}", showarrow=False, xanchor="left",
                               xshift=4, font={"size": s.small, "color": T.GOOD if ok else T.BAD}, row=1, col=col)  # fmt: skip
        ok = best["acc"] >= fl
        fig.add_trace(go.Scatter(x=[best["acc"]], y=[BEST], mode="markers", marker={"size": s.marker, "color": T.SURFACE,
                                 "symbol": "diamond", "line": {"color": T.INK_2, "width": s.line}},
                                 hovertemplate=f"{best['config']} on shifted · {t}: {best['acc']:.3f}<extra></extra>"), row=1, col=col)  # fmt: skip
        fig.add_annotation(x=lo, y=BEST, text=("✓ " if ok else "✗ ") + f"{best['acc']:.3f} {best['config']}", showarrow=False,
                           xanchor="left", xshift=4, font={"size": s.small, "color": T.GOOD if ok else T.BAD}, row=1, col=col)  # fmt: skip
    for col in range(1, 5):
        fig.update_xaxes(range=[lo, 1.02], tickformat=".2f", row=1, col=col)
    fig.update_xaxes(title_text=f"accuracy (axis starts at {lo:.2f})", title_font={"size": s.small, "color": T.MUTED},
                     row=1, col=2)  # fmt: skip
    fig.update_yaxes(tickfont={"size": s.label, "color": T.INK_2}, autorange="reversed")
    T.layout(fig, s, title=title_text(m, robust_title(m)), caption=caption(m, "robustness"))
    for a in fig.layout.annotations:
        if a.text in TASKS:
            a.font = {"size": s.label, "color": T.INK, "family": T.DISPLAY_FONT}
            a.yshift = 22 if not s.png else 44
    return fig


# --- 7. receipt (one dev ticket) as a figure for the deck -----------------------------------------------


def receipt_title(m: dict) -> list[Segment]:
    r = "receipt"
    return ["One dev ticket (", (f"{r}.ticket_id", "raw"), "): always-best ", (f"{r}.B1.usd_nocache", "usd5"),
            " vs O1 ", (f"{r}.O1.usd_nocache", "usd5"), " (" + T.HEADLINE + ")"]  # fmt: skip


def receipt(m: dict, s: T.Size) -> go.Figure:
    """Two itemised receipts in one table: a shaded header row per policy, its calls, a bold total."""
    r = m["receipt"]
    hdr = ["call", "model-effort", "tokens in / out*", T.HEADLINE, T.CACHED, "latency", "checks / verdict"]
    rows, fills, colors = [], [], []
    for pol in ("B1", "O1"):
        p, st = r[pol], T.POLICY[pol]
        n = len(p["lines"])
        rows.append([f"<b>{st.label}</b>", f"{n} call" + ("s" if n > 1 else ""), "", "", "", "", ""])
        fills.append("#eef4fc" if pol == "O1" else "#f1f0ec")
        colors.append(st.color if pol == "O1" else T.INK)
        for ln in p["lines"]:
            rows.append([ln["role"], ln["config"], f"{ln['input_tokens']:,} / {ln['output_tokens']:,}",
                         fmt_value(ln["usd_nocache"], "usd5"), fmt_value(ln["usd_cached"], "usd5"),
                         fmt_value(ln["latency_s"], "s2"), "✓ pass" if ln["checks_pass"] else "✗ fail"])  # fmt: skip
            fills.append(T.SURFACE)
            colors.append(T.INK_2)
        verdict = ("✓ correct" if p["correct"] else "✗ wrong") + (
            ", in budget" if p["success"] else ", over budget"
        )
        rows.append(["<b>total</b>", "", "", f"<b>{fmt_value(p['usd_nocache'], 'usd5')}</b>",
                     f"<b>{fmt_value(p['usd_cached'], 'usd5')}</b>", f"<b>{fmt_value(p['latency_s'], 's2')}</b>",
                     f"<b>{verdict}</b>"])  # fmt: skip
        fills.append(T.SURFACE)
        colors.append(T.INK)
    cols = [list(c) for c in zip(*rows, strict=True)]
    fig = go.Figure(go.Table(
        columnwidth=[2.6, 1.7, 1.9, 2.3, 2.1, 1.2, 2.6],
        header={"values": [f"<b>{h}</b>" for h in hdr], "fill_color": T.SURFACE, "line_color": T.AXIS,
                "align": ["left", "left", "right", "right", "right", "right", "left"],
                "font": {"size": s.small, "color": T.MUTED}, "height": 70 if s.png else 30},
        cells={"values": cols, "fill_color": [fills] * len(hdr), "line_color": T.GRID,
               "align": ["left", "left", "right", "right", "right", "right", "left"],
               "font": {"size": s.label + (4 if s.png else 0), "color": [colors] * len(hdr)},
               "height": 78 if s.png else 30},
        domain={"x": [0, 1], "y": [0, 1]},
    ))  # fmt: skip
    T.layout(fig, s, title=title_text(m, receipt_title(m)),
             caption=caption(m, "receipt") + " · *each model counts tokens with its own tokenizer; not comparable "
             "across models · the two Haiku calls run in parallel, so O1's latency is the slower one")  # fmt: skip
    return fig


FIGURES: tuple[Figure, ...] = (
    Figure(
        "cpst_forest",
        [],
        "O1 vs baselines and the oracle: cost per successful task with 95% CIs on dev, shifted and held-out",
        [],
        forest,
        430,
    ),  # fmt: skip
    Figure(
        "spend_by_task",
        [],
        "Where the money goes on held-out: spend by task, always-best vs O1 live",
        [],
        spend,
        360,
    ),
    Figure(
        "adjudicate_sankey",
        [],
        "Inside adjudicate on held-out (live): accepted at the Haiku pair vs escalated, and how each ended",
        [],
        sankey,
        380,
    ),  # fmt: skip
    Figure(
        "effort",
        [],
        "Effort level: cost per call rises with effort, accuracy does not (dev)",
        [],
        effort,
        380,
    ),
    Figure(
        "sim_vs_live",
        [],
        "Held-out O1: simulated (replay) vs live latency and success by task",
        [],
        simlive,
        360,
    ),
    Figure(
        "robustness",
        [],
        "Per-task accuracy vs the frozen floor: dev, held-out (live), shifted, fail-safe",
        [],
        robust,
        330,
    ),  # fmt: skip
    Figure(
        "receipt",
        [],
        "One dev ticket itemised: always-best vs O1 (calls, tokens, USD, latency, verdict)",
        [],
        receipt,
        330,
    ),  # fmt: skip
)

TITLES = {
    "cpst_forest": forest_title,
    "spend_by_task": spend_title,
    "adjudicate_sankey": sankey_title,
    "effort": effort_title,
    "sim_vs_live": simlive_title,
    "robustness": robust_title,
    "receipt": receipt_title,
}

SOURCES = {
    "cpst_forest": ("dev", "shifted", "heldout_matrix", "heldout_live"),
    "spend_by_task": ("heldout_matrix", "heldout_live"),
    "adjudicate_sankey": ("heldout_live",),
    "effort": ("dev",),
    "sim_vs_live": ("heldout_matrix", "heldout_live"),
    "robustness": ("dev", "shifted", "heldout_live"),
    "receipt": ("dev",),
}
