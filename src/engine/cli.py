"""`engine` command-line entry point."""

from __future__ import annotations

import typer

from engine.contracts import utcnow

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def main() -> None:
    """Efficiency layer CLI (docs/SPEC.md)."""


@app.command()
def version() -> None:
    """Print the package version."""
    from engine import __version__

    typer.echo(__version__)


def _print_estimate(est: dict) -> None:
    typer.echo("Smoke cost estimate (USD)        calls   expected      worst")
    for name, r in est["rows"].items():
        typer.echo(f"  {name:<28} {int(r['calls']):>6} {r['expected']:>10.4f} {r['worst']:>10.4f}")
    exp, worst = est["anthropic_expected"], est["anthropic_worst"]
    typer.echo(f"  {'TOTAL anthropic':<28} {'':>6} {exp:>10.4f} {worst:>10.4f}")
    typer.echo(f"  {'TOTAL openrouter (Jev)':<28} {'':>6} {est['openrouter_expected']:>10.6f}")
    for k, v in est["assumptions"].items():
        typer.echo(f"  assumption {k}: {v}")


def _print_summary(s) -> None:
    import json

    report = json.loads(s.SMOKE_JSON.read_text(encoding="utf-8"))
    typer.echo(f"run {report['run_id']} | git {report['git_sha'][:12]}")
    names = [name for name, _ in s.SUMMARY_COLUMNS]
    typer.echo("  ".join(f"{n:>12}" for n in names))
    for row in s.summary_rows(report["checks"]):
        cells = [fmt.format(row[n]) if row[n] is not None else "-" for n, fmt in s.SUMMARY_COLUMNS]
        typer.echo("  ".join(f"{c:>12}" for c in cells))
    typer.echo(f"cheapest effort per model (no-cache): {s.cheapest_effort_nocache(report['checks'])}")
    typer.echo(
        "cost_usd = Cost with caching (actual) | nocache_usd = Cost without caching (headline)  (D1.4)"
    )


@app.command()
def smoke(
    mode: str = typer.Option("replay", help="replay (no key, no spend) | live | auto"),
    estimate_only: bool = typer.Option(False, "--estimate", help="Print the cost estimate and exit."),
    summary: bool = typer.Option(False, "--summary", help="Print the per-config table from runs/smoke.json."),
    cap_anthropic: float = typer.Option(0.0, help="Approved Anthropic spend cap for this run (USD)."),
    cap_openrouter: float = typer.Option(0.0, help="Approved OpenRouter spend cap for this run (USD)."),
    yes: bool = typer.Option(
        False, "--yes", help="Confirm the estimate was approved; required for paid modes."
    ),
) -> None:
    """Phase 0 smoke checks 1–7 (SPEC §2.3) -> runs/smoke.json."""
    from engine import smoke as s
    from engine.llm.client import Ledger

    if summary:
        _print_summary(s)
        return
    est = s.estimate()
    ledger = Ledger()
    if estimate_only or mode != "replay":
        _print_estimate(est)
        typer.echo(
            f"Ledger remaining: anthropic ${ledger.remaining('anthropic'):.4f} | "
            f"openrouter ${ledger.remaining('openrouter'):.4f}"
        )
    if estimate_only:
        return
    if mode not in ("replay", "live", "auto"):
        raise typer.BadParameter("mode must be replay, live or auto")
    if mode != "replay":
        if not yes or cap_anthropic <= 0 or cap_openrouter <= 0:
            typer.echo(
                "Paid run refused: pass --yes with --cap-anthropic and --cap-openrouter (approved caps)."
            )
            raise typer.Exit(2)
        report, calls, jev_calls = s.run(mode, {"anthropic": cap_anthropic, "openrouter": cap_openrouter})  # type: ignore[arg-type]
        s.write_run(report, calls, jev_calls)
        typer.echo(f"Wrote runs/smoke.json and runs/{report.run_id}/ (spend {report.spend_usd})")
    else:
        report, _, _ = s.run("replay")
        stored = s.SMOKE_JSON.read_text(encoding="utf-8") if s.SMOKE_JSON.exists() else None
        if stored is None:
            typer.echo("No runs/smoke.json to compare against.")
            raise typer.Exit(1)
        import json

        same = s.comparable(report.checks) == s.comparable(json.loads(stored)["checks"])
        typer.echo(f"Replay {'reproduces' if same else 'DOES NOT reproduce'} runs/smoke.json exactly.")
        if not same:
            raise typer.Exit(1)
    for note in report.notes:
        typer.echo(f"NOTE: {note}")


@app.command()
def gen() -> None:
    """Generate dev/held-out/shifted, run SPEC §4.4 QA, write MANIFEST + review file. No paid calls."""
    from engine.datagen import gen as G
    from engine.datagen import publish, qa

    splits = G.generate()
    report = qa.run_all(splits)
    failed = qa.blocking_failures(report)
    for name, res in report.items():
        if name.startswith("_") or name == "decision_distribution":
            continue
        typer.echo(
            f"[{'PASS' if res['pass'] else 'FAIL'}] {name}: {res['value']} (threshold: {res['threshold']})"
        )
    dist = report["decision_distribution"]
    for split, d in dist["per_split"].items():
        shares = ", ".join(f"{k} {v:.1%}" for k, v in d["shares"].items())
        typer.echo(f"  decisions {split} (n={d['n_adjudicate']}): {shares}")
    typer.echo(f"  label flags (<10%): {dist['flags'] or 'none'}")
    if failed:
        typer.echo(f"QA FAILED: {failed}; nothing written.")
        raise typer.Exit(1)
    manifest = publish.write(splits, report)
    typer.echo("wrote data/generated/{dev,heldout,shifted}.jsonl, MANIFEST.json, data/review/dev_review.md")
    typer.echo(f"held-out sealed: sha256 {manifest['heldout_sealed']['sha256']}")


@app.command()
def policy() -> None:
    """Render the FICTIONAL policy document (EN + AR, v1 + v2) from data/rules/ (SPEC §4.1)."""
    from engine.datagen.render_policy import write_all
    from engine.llm.pricing import ROOT

    for path in write_all():
        typer.echo(f"wrote {path.relative_to(ROOT).as_posix()}")


@app.command()
def probe(
    mode: str = typer.Option("auto", help="auto (replay if recorded) | live | replay"),
    estimate_only: bool = typer.Option(False, "--estimate", help="Print the cost estimate and exit."),
    cap_anthropic: float = typer.Option(0.0, help="Approved Anthropic spend cap for this run (USD)."),
    yes: bool = typer.Option(False, "--yes", help="Confirm the estimate was approved; required to spend."),
) -> None:
    """Phase 2 entry check (D0.8): structured outputs + effort + adaptive thinking on all models/schemas."""
    from engine.eval import estimate as E
    from engine.eval import probe as P
    from engine.llm.client import CassetteStore, Ledger, request_hash

    reqs = [(t.task_type, P.build_request(t, m, e)) for t, m, e in P.probe_requests()]
    missing = sum(CassetteStore().get("anthropic", request_hash(r)) is None for _, r in reqs)
    est = E.estimate_requests(reqs, concurrency=3)
    typer.echo(E.format_estimate("Probe", est, Ledger().remaining("anthropic")))
    typer.echo(f"  already recorded: {len(reqs) - missing}; would be live: {missing}")
    if estimate_only:
        return
    spends = mode == "live" or (mode == "auto" and missing)
    if spends and (not yes or cap_anthropic <= 0):
        typer.echo("Paid run refused: pass --yes with --cap-anthropic (the approved cap).")
        raise typer.Exit(2)
    from engine import runinfo

    sha = runinfo.git_sha()  # taken before the run writes anything, so it identifies the code that ran
    run_id, calls = P.run(mode, cap_anthropic)  # type: ignore[arg-type]
    out = P.write(run_id, calls, sha)
    for c in calls:
        typer.echo(
            f"{'ok  ' if c.ok else 'FAIL'} {c.config_id:<14} {c.task:<10} {c.call.stop_reason} "
            f"out={c.call.output_tokens} think={c.call.thinking_tokens} cache_r={c.call.cache_read_tokens} "
            f"lat={c.call.latency_ms:.0f}ms graded={c.graded_correct} {c.schema_errors or ''}"
        )
    typer.echo(f"{sum(c.ok for c in calls)}/{len(calls)} ok; wrote {out}")


@app.command()
def matrix(
    split: str = typer.Option("dev", help="dev | shifted (held-out is sealed: only `engine final`)"),
    subset: str = typer.Option("all", help="pilot (40 stratified items) | all"),
    mode: str = typer.Option("auto", help="auto (replay if recorded) | live | replay"),
    run_id: str = typer.Option("", help="Run id; pass an existing one to resume it."),
    estimate_only: bool = typer.Option(False, "--estimate", help="Print the estimate and exit."),
    cap_anthropic: float = typer.Option(0.0, help="Approved Anthropic spend cap for this run (USD)."),
    concurrency: int = typer.Option(6, help="Max calls in flight per model (the pacer adapts below it)."),
    repeat: int = typer.Option(0, help="Recording epoch: a different value records everything afresh."),
    yes: bool = typer.Option(False, "--yes", help="Confirm the estimate was approved; required to spend."),
) -> None:
    """Record the 9-config matrix (SPEC §7.4): paid, resumable, paced by the API rate-limit headers."""
    from engine import runinfo
    from engine.eval import estimate as E
    from engine.eval import matrix as M
    from engine.eval.data import load_split
    from engine.eval.subsets import stratified_subset
    from engine.llm.client import CassetteStore, Ledger
    from engine.llm.pricing import pricebook

    if split not in ("dev", "shifted"):
        raise typer.BadParameter("split must be dev or shifted (held-out is only run by `engine final`)")
    tickets = load_split(split)
    if subset == "pilot":
        tickets = stratified_subset(tickets)
    run_id = run_id or f"matrix-{split}-{subset}-" + utcnow().strftime("%Y%m%dT%H%M%SZ")
    done = M.load_done(M.runs_dir(run_id) / "calls.jsonl")
    cells = [c for c in M.plan_cells(tickets) if (c[0].id, pricebook().config_id(c[1], c[2])) not in done]
    live = M.pending_live(cells, CassetteStore(), done, repeat)
    est = E.estimate_requests(
        [(c[0].task_type, M.cell_request(c, repeat)) for c in live],
        concurrency=3 * concurrency,
    )
    typer.echo(
        f"run {run_id}: {len(tickets)} tickets, {len(cells)} cells to do, {len(cells) - len(live)} replayable"
    )
    typer.echo(E.format_estimate("Live calls", est, Ledger().remaining("anthropic")))
    if estimate_only:
        return
    if live and mode != "replay" and (not yes or cap_anthropic <= 0):
        typer.echo("Paid run refused: pass --yes with --cap-anthropic (the approved cap).")
        raise typer.Exit(2)
    summary = M.run_matrix(
        split,
        tickets,
        mode=mode,  # type: ignore[arg-type]
        run_id=run_id,
        cap_usd=cap_anthropic,
        per_model_concurrency=concurrency,
        repeat=repeat,
        git_sha=runinfo.git_sha(),
        progress=typer.echo,
    )
    typer.echo(summary.model_dump_json(indent=1))
    if summary.n_errors:
        typer.echo(f"{summary.n_errors} cells have no response: re-run with --run-id {run_id} to retry them.")
        raise typer.Exit(1)


@app.command("cells-report")
def cells_report(
    run_id: str = typer.Argument(..., help="matrix run id, e.g. matrix-dev-pilot-1"),
    split: str = typer.Option("dev"),
) -> None:
    """Parse rate, accuracy per config and task, cost and latency of a recorded matrix run (replay only)."""
    from engine.eval.report_text import format_report

    typer.echo(format_report(run_id, split))


@app.command()
def floors(
    run_id: str = typer.Option("matrix-dev-full-1", help="recorded dev matrix run"),
    write: bool = typer.Option(
        False, "--write", help="Write the proposal to config/policy.yaml (status: proposed)."
    ),
    budget_rule: str = typer.Option("cheapest", help="cheapest | premium: which tied config sets the budget"),
    freeze: bool = typer.Option(
        False, "--freeze", help="With --write: mark the policy frozen (sign-off given)."
    ),
) -> None:
    """Derive per-task accuracy floors and latency budgets from the dev matrix (SPEC 7.2). Not frozen."""
    from engine import runinfo
    from engine.eval.analysis_text import format_floors
    from engine.eval.cells import build_cells
    from engine.eval.data import load_split
    from engine.eval.floors import derive_floors, write_policy_yaml

    cells, problems = build_cells([run_id], load_split("dev"))
    if problems:
        typer.echo(f"{len(problems)} problems, e.g. {problems[0]}")
        raise typer.Exit(1)
    result = derive_floors(cells, budget_rule)
    typer.echo(format_floors(result))
    if write:
        write_policy_yaml(result, [run_id], runinfo.git_sha(), budget_rule=budget_rule, frozen=freeze)
        state = "frozen" if freeze else "proposed"
        typer.echo(f"wrote config/policy.yaml (status: {state}). Tag floors-v1 only after sign-off.")


@app.command()
def evaluate(
    run_id: str = typer.Option("matrix-dev-full-1", help="recorded dev matrix run"),
    budget_rule: str = typer.Option("cheapest", help="cheapest | premium: which tied config sets the budget"),
) -> None:
    """Baselines B1-B5, oracle and gap, Pareto ladders, router headroom, all by replay (SPEC 7.3-7.7)."""
    from engine.eval.analysis import analyse
    from engine.eval.analysis_text import format_analysis
    from engine.eval.cells import build_cells
    from engine.eval.data import load_split
    from engine.eval.floors import derive_floors

    tickets = load_split("dev")
    cells, problems = build_cells([run_id], tickets)
    if problems:
        typer.echo(f"{len(problems)} problems, e.g. {problems[0]}")
        raise typer.Exit(1)
    typer.echo(format_analysis(analyse(cells, tickets, derive_floors(cells, budget_rule))))


@app.command()
def solvability(
    run_id: str = typer.Option("matrix-dev-full-1"),
    config: str = typer.Option("opus-high", help="config whose failures are listed"),
) -> None:
    """List every failure of one config with ticket, gold, model output, verdicts and rule trace."""
    from engine.eval.cells import build_cells
    from engine.eval.data import load_split
    from engine.eval.solvability import failures

    tickets = load_split("dev")
    cells, _ = build_cells([run_id], tickets)
    found = failures(run_id, config, tickets, cells)
    typer.echo(f"{len(found)} failures of {config} in {run_id}")
    for f in found:
        typer.echo(f.model_dump_json(indent=1))


@app.command("phase2-report")
def phase2_report(
    run_id: str = typer.Option("matrix-dev-full-1"),
    repeat: int = typer.Option(1, help="the run's recording epoch"),
) -> None:
    """Write reports/phase2/* (cells, replay check, floors, baselines under both budget rules, failures)."""
    from engine.eval.phase2_report import write_all

    for path in write_all(run_id, repeat):
        typer.echo(f"wrote {path.relative_to(path.parents[2]).as_posix()}")


@app.command("phase3-report")
def phase3_report(run_id: str = typer.Option("matrix-dev-full-1")) -> None:
    """Write reports/phase3/* (O1, ablations, routers) by replay of the dev matrix; no API calls."""
    from engine.eval.phase3_report import REPORTS, write

    for path in write(run_id, REPORTS):
        typer.echo(f"wrote {path.relative_to(path.parents[2]).as_posix()}")


@app.command("phase4-report")
def phase4_report(run_id: str = typer.Option("matrix-shifted-full-1")) -> None:
    """Write reports/phase4/* (frozen policy on shifted, baselines, ablations) by replay; no API calls."""
    from engine.eval.phase4_report import write

    for path in write(run_id):
        typer.echo(f"wrote {path.relative_to(path.parents[2]).as_posix()}")


@app.command("jev-router")
def jev_router(
    yes: bool = typer.Option(False, "--yes", help="make the paid calls (otherwise print the estimate only)"),
    cap: float = typer.Option(0.10, help="OpenRouter cap for this run, USD (approved: $0.10, D3.3)"),
) -> None:
    """Ask Jev the D3.3 router questions about every dev adjudicate ticket (paid; estimate first)."""
    from engine.eval.data import load_split
    from engine.router import jev_router as J

    tickets = [t for t in load_split("dev") if t.task_type == "adjudicate"]
    est = J.estimate(tickets)
    typer.echo(f"Jev router on dev: {len(tickets)} calls + 1 warm-up, estimate ${est:.5f} (cap ${cap:.2f})")
    if est > cap:
        typer.echo("estimate exceeds the cap; aborting")
        raise typer.Exit(1)
    if not yes:
        typer.echo("dry run: pass --yes to spend")
        return
    answers = J.run(tickets, "auto", cap)
    typer.echo(f"{len(answers)}/{len(tickets)} answered; log runs/{J.RUN_ID}/jev.jsonl")


@app.command("audit-names")
def audit_names() -> None:
    """Count tickets where two people share a first name (caller vs driver or claimant); no data change."""
    from engine.datagen.audit_names import audit, format_audit

    counts, ids = audit()
    typer.echo(format_audit(counts, ids))


@app.command("replay-check")
def replay_check(
    run_id: str = typer.Option("matrix-dev-full-1"),
    repeat: int = typer.Option(1, help="the run's recording epoch (--repeat it was recorded with)"),
    split: str = typer.Option("dev", help="dev | shifted"),
) -> None:
    """Replay a recorded matrix with no key and confirm it reproduces the live metrics exactly."""
    from engine.eval import replay
    from engine.eval.data import load_split

    problems = replay.compare(run_id, load_split(split), repeat)
    for p in problems[:20]:
        typer.echo(f"MISMATCH {p}")
    typer.echo("replay reproduces the live run exactly" if not problems else f"{len(problems)} mismatches")
    if problems:
        raise typer.Exit(1)


@app.command()
def check(
    fast: bool = typer.Option(
        False, "--fast", help="ruff + tests not marked slow only (WIP commits; never for tags or phase gates)"
    ),
) -> None:
    """ruff + pytest + replay integrity + gitleaks (run before every commit)."""
    from engine.check import run_all

    if not run_all(fast=fast):
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
