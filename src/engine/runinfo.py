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


def git_sha() -> str:
    try:
        return _git("rev-parse", "HEAD").strip() + ("-dirty" if tree_status() else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def require_clean_tree() -> None:
    """Paid runs must be tied to a clean commit so their git SHA identifies the exact code and prompts."""
    status = tree_status()
    if status:
        files = ", ".join(line[3:] for line in status.splitlines()[:5])
        raise DirtyTree(f"paid run refused: working tree is dirty ({files}); commit or stash first")
