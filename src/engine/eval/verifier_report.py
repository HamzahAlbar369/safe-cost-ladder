"""Verifier quality over a recorded matrix (SPEC §6.3: false-accept rate measured per task on dev).

A *false accept* is a wrong answer that passed every check (V0-V2): the verifier would have let it through.
A *false reject* is a correct answer that failed a check: the verifier would have escalated needlessly.
Replay only; no API calls.
"""

from __future__ import annotations

from collections import Counter

from engine.contracts import Ticket
from engine.eval.cells import Cell
from engine.eval.metrics import TASKS, group

LEVELS = ("V0", "V1", "V2")


def _rate(k: int, n: int) -> str:
    return f"{k / n:.1%}" if n else "-"


def _caught(cells: list[Cell]) -> str:
    c = Counter(level for cell in cells for level in cell.failed_checks)
    return "/".join(str(c[level]) for level in LEVELS)


def table(cells: list[Cell]) -> list[str]:
    head = (
        f"{'task':<11}{'config':<14}{'wrong':>6}{'false acc':>10}{'FAR':>8}"
        f"{'wrong caught V0/V1/V2':>24}{'correct':>9}{'false rej':>10}{'FRR':>8}{'rejected by V0/V1/V2':>22}"
    )
    lines = [head]
    totals = {t: [0, 0, 0, 0] for t in TASKS}
    for task in TASKS:
        for (config,), cs in sorted(
            group([c for c in cells if c.task == task], lambda c: (c.config_id,)).items()
        ):
            wrong = [c for c in cs if not c.correct]
            right = [c for c in cs if c.correct]
            fa = [c for c in wrong if c.verified]
            fr = [c for c in right if not c.verified]
            for i, v in enumerate((len(wrong), len(fa), len(right), len(fr))):
                totals[task][i] += v
            lines.append(
                f"{task:<11}{config:<14}{len(wrong):>6}{len(fa):>10}{_rate(len(fa), len(wrong)):>8}"
                f"{_caught([c for c in wrong if not c.verified]):>24}{len(right):>9}{len(fr):>10}"
                f"{_rate(len(fr), len(right)):>8}{_caught(fr):>22}"
            )
        w, fa, r, fr = totals[task]
        lines.append(
            f"{task:<11}{'ALL 9':<14}{w:>6}{fa:>10}{_rate(fa, w):>8}{'':>24}{r:>9}{fr:>10}{_rate(fr, r):>8}"
        )
        lines.append("")
    return lines


def false_rejects(cells: list[Cell]) -> list[str]:
    """Every correct answer a check rejected, with the check and reason."""
    rows = sorted(
        (c for c in cells if c.correct and not c.verified), key=lambda c: (c.task, c.ticket_id, c.config_id)
    )
    return [f"{c.ticket_id}  {c.config_id:<14}{c.task:<11}{' | '.join(c.check_reasons)}" for c in rows] or [
        "none"
    ]


def cheap_adjudicate_misses(cells: list[Cell], tickets: list[Ticket], configs: tuple[str, ...]) -> list[str]:
    by_id = {t.id: t for t in tickets}
    lines = [
        f"{'config':<14}{'ticket':<10}{'level':<6}{'lang':<5}{'design':<26}{'wrong fields':<18}flagged by"
    ]
    for config in configs:
        misses = sorted(
            (c for c in cells if c.config_id == config and c.task == "adjudicate" and not c.correct),
            key=lambda c: c.ticket_id,
        )
        for c in misses:
            t = by_id[c.ticket_id]
            wrong = ",".join(k for k, ok in c.fields.items() if not ok) or (
                "format" if not c.parsed_ok else "-"
            )
            flagged = ", ".join(c.check_reasons) if c.failed_checks else "NOT FLAGGED (false accept)"
            lines.append(
                f"{config:<14}{c.ticket_id:<10}{c.level:<6}{c.language:<5}{t.meta.design:<26}{wrong:<18}{flagged}"
            )
        lines.append(
            f"{config}: {len(misses)} adjudicate misses, {sum(1 for c in misses if c.verified)} not flagged"
        )
        lines.append("")
    return lines


def format_verifier_report(cells: list[Cell], tickets: list[Ticket]) -> str:
    out = [
        "Verifier quality, V0-V2 (V3 second opinion is a Phase 3 policy layer, not measured here)",
        "FAR = false-accept rate = wrong answers that passed every check / wrong answers.",
        "FRR = false-reject rate = correct answers that failed a check / correct answers.",
        "Check columns count how many answers each check rejected (an answer can fail more than one check).",
        "",
        *table(cells),
        "False rejects (correct answers rejected by a check)",
        *false_rejects(cells),
        "",
        "haiku-low and haiku-medium adjudicate misses",
        *cheap_adjudicate_misses(cells, tickets, ("haiku-low", "haiku-medium")),
    ]
    return "\n".join(out)
