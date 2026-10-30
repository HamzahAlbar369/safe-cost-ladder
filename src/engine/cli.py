"""`engine` command-line entry point."""

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


if __name__ == "__main__":
    app()
