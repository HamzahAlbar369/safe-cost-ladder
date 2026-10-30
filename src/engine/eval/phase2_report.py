"""Writes the Phase 2 evidence files under reports/phase2/. Every file starts with its provenance (run id,
git SHA, config hash) so no number in the docs is typed by hand (CLAUDE.md: Numbers)."""

from __future__ import annotations

import json
from pathlib import Path

from engine import runinfo
from engine.datagen.audit_names import audit, format_audit
from engine.eval import replay
from engine.eval.analysis import analyse
from engine.eval.analysis_text import format_analysis, format_floors
from engine.eval.cells import build_cells
from engine.eval.data import load_split
from engine.eval.floors import derive_floors
from engine.eval.matrix import config_hash
from engine.eval.report_text import format_report
from engine.eval.solvability import failures
from engine.eval.verifier_report import format_verifier_report
from engine.llm.pricing import ROOT

OUT = ROOT / "reports" / "phase2"
SOLVABILITY_CONFIGS = ("opus-high", "opus-medium", "opus-low")


def write_all(run_id: str, repeat: int, out: Path = OUT) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    sha, chash = runinfo.git_sha(), config_hash()
    header = f"run: {run_id} | split: dev | git: {sha} | config_hash: {chash}\n\n"
    tickets = load_split("dev")
    cells, problems = build_cells([run_id], tickets)
    if problems:
        raise RuntimeError(f"{len(problems)} cells without a response, e.g. {problems[0]}")
    files: dict[str, str] = {
        "cells_report.txt": format_report(run_id),
        "verifiers.txt": format_verifier_report(cells, tickets),
    }
    mismatches = replay.compare(run_id, tickets, repeat)
    files["replay_check.txt"] = (
        "replay reproduces the live run exactly (per-call cost, latency, tokens, parse flag, metrics)\n"
        if not mismatches
        else "\n".join(mismatches)
    )
    for rule in ("cheapest", "premium"):
        floors = derive_floors(cells, rule)
        files[f"floors_{rule}.txt"] = f"budget rule: {rule}\n\n" + format_floors(floors)
        files[f"evaluate_{rule}.txt"] = f"budget rule: {rule}\n\n" + format_analysis(
            analyse(cells, tickets, floors)
        )
    counts, flagged = audit()
    files["name_collisions.txt"] = "\n\n".join(
        [format_audit(counts, flagged), collision_impact(cells, flagged["dev"])]
    )
    paths = []
    for name, body in files.items():
        path = out / name
        path.write_text(header + body + "\n", encoding="utf-8")
        paths.append(path)
    for config in SOLVABILITY_CONFIGS:
        found = failures(run_id, config, tickets, cells)
        path = out / f"failures_{config}.json"
        path.write_text(
            json.dumps(
                {
                    "run": run_id,
                    "git": sha,
                    "config_hash": chash,
                    "config": config,
                    "failures": [f.model_dump(mode="json") for f in found],
                },
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        paths.append(path)
    return paths


def collision_impact(cells: list, flagged_dev: list[str]) -> str:
    """Dev accuracy of each model family on the tickets with a visible name clash vs all other tickets of the
    same tasks (adjudicate tickets only: the clash lines occur in claim narratives)."""
    clash = set(flagged_dev)
    lines = [
        f"Dev outcome on the {len(clash)} visible-clash tickets vs other adjudicate tickets (all efforts)",
        f"{'model':<8}{'clash n':>9}{'clash acc':>11}{'other n':>9}{'other acc':>11}",
    ]
    for model in ("haiku", "sonnet", "opus"):
        mine = [c for c in cells if c.config_id.startswith(model) and c.task == "adjudicate"]
        a = [c for c in mine if c.ticket_id in clash]
        b = [c for c in mine if c.ticket_id not in clash]
        acc = lambda xs: sum(c.correct for c in xs) / len(xs) if xs else 0.0  # noqa: E731
        lines.append(f"{model:<8}{len(a):>9}{acc(a):>11.3f}{len(b):>9}{acc(b):>11.3f}")
    return "\n".join(lines)
