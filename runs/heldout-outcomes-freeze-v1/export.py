"""One-off held-out outcomes export (approved by Hamzah, Phase 5): run with the frozen code at freeze-v1.

Uses only the frozen path: final.guard() -> load_heldout(token) -> SplitContext (the same code that wrote
reports/final/heldout.txt). Writes per-ticket outcomes per policy, O1 traces and per-cell grades. No ticket
text, no gold values, no verifier reasons are written.
"""

import json
import sys
from pathlib import Path

from engine import final as F
from engine.eval.baselines import summarize
from engine.eval.phase4_report import SplitContext

token = F.guard()
tickets = F.load_heldout(token)
matrix_run, live_run = F.run_ids(token)
ctx = SplitContext(matrix_run, "heldout", tickets=tickets)
sim, traces = ctx.o1()

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
policies = {**ctx.baselines, "O1 (frozen, simulated)": sim, "Oracle": ctx.oracle}
with (out / "outcomes.jsonl").open("w", encoding="utf-8", newline="\n") as f:
    for name, outs in policies.items():
        for o in outs:
            f.write(json.dumps({"policy": name, **o.model_dump(mode="json")}) + "\n")
with (out / "o1_traces.jsonl").open("w", encoding="utf-8", newline="\n") as f:
    for t in traces:
        f.write(t.model_dump_json() + "\n")
keep = (
    "ticket_id task level language config_id model effort correct parsed_ok verified truncated "
    "cost_usd cost_usd_nocache latency_ms output_tokens thinking_tokens"
).split()
with (out / "cells.jsonl").open("w", encoding="utf-8", newline="\n") as f:
    for c in sorted(ctx.cells, key=lambda c: (c.ticket_id, c.config_id)):
        d = c.model_dump(mode="json")
        f.write(json.dumps({k: d[k] for k in keep}) + "\n")
manifest = {
    "what": "held-out per-ticket outcomes, exported once with the frozen code (Phase 5, approved by Hamzah)",
    "tag": token.tag,
    "git_sha": token.sha,
    "matrix_run": matrix_run,
    "live_run": live_run,
    "n_tickets": len(ctx.tickets),
    "n_cells": len(ctx.cells),
    "floors": {k: v for k, v in ctx.floors.model_dump(mode="json").items()},
    "static": dict(ctx.static),
    "summary": {name: summarize(outs) for name, outs in policies.items()},
}
(out / "manifest.json").write_text(json.dumps(manifest, indent=1, default=str) + "\n", encoding="utf-8")
print("wrote", out, len(ctx.tickets), "tickets", len(ctx.cells), "cells")
