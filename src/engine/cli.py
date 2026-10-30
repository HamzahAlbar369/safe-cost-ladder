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
    split: str = typer.Option("dev", help="dev (held-out is sealed; shifted is recorded in Phase 4)"),
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
    if split == "shifted":
        typer.echo("shifted is recorded in Phase 4, not now.")
        raise typer.Exit(2)
    tickets = load_split(split)
    if subset == "pilot":
        tickets = stratified_subset(tickets)
    run_id = run_id or f"matrix-{split}-{subset}-" + utcnow().strftime("%Y%m%dT%H%M%SZ")
    done = M.load_done(M.runs_dir(run_id) / "calls.jsonl")
    cells = [c for c in M.plan_cells(tickets) if (c[0].id, pricebook().config_id(c[1], c[2])) not in done]
    live = M.pending_live(cells, CassetteStore(), done, repeat)
    est = E.estimate_requests(
        [(t.task_type, M.build_request(t, m, e, repeat=repeat)) for t, m, e in live],
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
def check() -> None:
    """ruff + pytest + replay integrity + gitleaks (run before every commit)."""
    from engine.check import run_all

    if not run_all():
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
