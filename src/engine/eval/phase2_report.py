"""Writes the Phase 2 evidence files under reports/phase2/. Every file starts with its provenance (run id,
git SHA, config hash) so no number in the docs is typed by hand (CLAUDE.md: Numbers)."""

from __future__ import annotations

import json
from pathlib import Path

from engine import runinfo
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
