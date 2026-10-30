"""Plain-text report of a recorded matrix run: parse rate, accuracy, cost, latency (replay only)."""

from __future__ import annotations

from engine.eval import metrics as K
from engine.eval.cells import build_cells, read_calls
from engine.eval.data import load_split


def format_report(run_id: str, split: str = "dev") -> str:
    cells, problems = build_cells([run_id], load_split(split))
    lines = [f"{run_id}: {len(cells)} cells, {len(problems)} problems"]
    lines += [f"  PROBLEM {p}" for p in problems[:10]]

    lines += ["", "Per config (latency = request sent -> response received; queue wait excluded)"]
    head = [
        "config",
        "n",
        "acc",
        "parse",
        "trunc",
        "p50_s",
        "p95_s",
        "qwait95",
        "out_tok",
        "$cached",
        "$nocache",
    ]
    lines.append("  ".join(f"{h:>9}" for h in head))
    for r in K.config_table(cells):
        values = [
            r["config"],
            r["n"],
            f"{r['accuracy']:.3f}",
            f"{r['parse_rate']:.3f}",
            r["truncated"],
            f"{r['p50_s']:.2f}",
            f"{r['p95_s']:.2f}",
            f"{r['queue_wait_p95_s']:.2f}",
            f"{r['out_tokens_mean']:.0f}",
            f"{r['usd_cached']:.4f}",
            f"{r['usd_nocache']:.4f}",
        ]
        lines.append("  ".join(f"{v:>9}" for v in values))

    acc = K.accuracy_matrix(cells)
    lines += ["", "Accuracy per config x task (n in brackets)"]
    lines.append(f"{'config':>9}  " + "  ".join(f"{t:>14}" for t in K.TASKS))
    for config_id, per_task in acc.items():
        cols = [f"{per_task[t][0]:>8.3f} ({per_task[t][1]:>2})" for t in K.TASKS]
        lines.append(f"{config_id:>9}  " + "  ".join(cols))

    cost = K.cost_stats(cells)
    lines += [
        "",
        f"Totals over {len(cells)} cells: Cost with caching (actual) ${cost['with_caching']:.4f} | "
        f"Cost without caching (headline) ${cost['without_caching']:.4f}",
    ]
    warm = [c for c in read_calls(run_id) if c.role == "probe"]
    lines.append(f"Warm-up calls (not in metrics): {len(warm)}, ${sum(c.cost_usd for c in warm):.4f}")
    return "\n".join(lines)
