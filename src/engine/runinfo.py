"""Run provenance: git SHA and the clean-working-tree rule for paid runs (DECISIONS D0.8)."""

from __future__ import annotations

import subprocess

from engine.llm.pricing import ROOT


class DirtyTree(RuntimeError):
    pass


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True, encoding="utf-8"
    ).stdout.rstrip("\n")  # keep leading spaces: porcelain status columns are positional


def tree_status() -> str:
    """`git status --porcelain` (tracked changes and untracked, non-ignored files)."""
    return _git("status", "--porcelain")


# Files the harness itself writes while running (run logs, the spend ledger, recorded responses). They cannot
# change what code or prompts a run used, so they do not make the tree "dirty" for the paid-run rule (D2.6).
OUTPUT_PREFIXES = ("runs/", "cassettes/")


def code_changes() -> list[str]:
    """Porcelain lines for everything except the harness's own output paths."""
    return [line for line in tree_status().splitlines() if not line[3:].startswith(OUTPUT_PREFIXES)]


def git_sha() -> str:
    try:
        return _git("rev-parse", "HEAD").strip() + ("-dirty" if code_changes() else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def require_clean_tree() -> None:
    """Paid runs must be tied to a clean commit so their git SHA identifies the exact code and prompts."""
    changes = code_changes()
    if changes:
        files = ", ".join(line[3:] for line in changes[:5])
        raise DirtyTree(f"paid run refused: working tree is dirty ({files}); commit or stash first")
