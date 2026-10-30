"""Verifier false-accept / false-reject accounting on hand-built cells."""

from engine.eval.verifier_report import cheap_adjudicate_misses, false_rejects, format_verifier_report, table
from tests.test_analysis import cell, tickets


def test_false_accept_and_reject_counts_and_catching_check():
    ts = [t for t in tickets() if t.task_type == "adjudicate"]
    a, b = ts[0], ts[1]
    cells = [
        cell(a, "haiku-low", correct=False).model_copy(update={"verified": True}),  # false accept
        cell(b, "haiku-low", correct=False).model_copy(
            update={"verified": False, "failed_checks": ("V2",), "check_reasons": ("V2: payout mismatch",)}
        ),  # wrong and caught by V2
        cell(a, "sonnet-low", correct=True).model_copy(
            update={"verified": False, "failed_checks": ("V1",), "check_reasons": ("V1: amount not found",)}
        ),  # false reject by V1
        cell(b, "sonnet-low", correct=True),
    ]
    row = next(line for line in table(cells) if line.startswith("adjudicate") and "haiku-low" in line)
    assert " 2 " in row and "50.0%" in row and "0/0/1" in row  # 2 wrong, FAR 50%, one caught by V2
    sonnet = next(line for line in table(cells) if line.startswith("adjudicate") and "sonnet-low" in line)
    assert "50.0%" in sonnet and "0/1/0" in sonnet  # FRR 50%, rejected by V1
    assert any(a.id in line and "V1: amount not found" in line for line in false_rejects(cells))
    misses = "\n".join(cheap_adjudicate_misses(cells, ts, ("haiku-low",)))
    assert (
        "NOT FLAGGED" in misses
        and "V2: payout mismatch" in misses
        and "2 adjudicate misses, 1 not flagged" in misses
    )
    assert "Verifier quality" in format_verifier_report(cells, ts)
