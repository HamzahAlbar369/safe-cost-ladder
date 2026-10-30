"""`engine` command-line entry point."""

from __future__ import annotations

import typer

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
def policy() -> None:
    """Render the FICTIONAL policy document (EN + AR, v1 + v2) from data/rules/ (SPEC §4.1)."""
    from engine.datagen.render_policy import write_all
    from engine.llm.pricing import ROOT

    for path in write_all():
        typer.echo(f"wrote {path.relative_to(ROOT).as_posix()}")


@app.command()
def check() -> None:
    """ruff + pytest + replay integrity + gitleaks (run before every commit)."""
    from engine.check import run_all

    if not run_all():
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
