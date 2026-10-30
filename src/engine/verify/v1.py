"""V1 grounding: every literal the model extracted or stated must appear in the ticket (SPEC §6.3).

Catches invented policy / report numbers, dates and amounts. Both sides go through `normalise`, so Arabic
digits, thousands separators and date formats match. A null value is not a literal and always passes (V1
cannot tell a wrongly-null field from a right one; that is the grader's job).
"""

from __future__ import annotations

import re
from typing import Any

from engine.contracts import TaskType
from engine.datagen.normalize import normalise
from engine.verify import Verdict


def _number_in(value: int, text: str) -> bool:
    return re.search(rf"(?<![\d.]){value}(?![\d])", text) is not None


def _literals(task: TaskType, out: dict[str, Any]) -> dict[str, Any]:
    if task == "extract":
        return out
    inputs = out.get("inputs")
    return dict(inputs) if isinstance(inputs, dict) else {}


def check_grounding(task: TaskType, out: Any, ticket_text: str) -> Verdict:
    if not isinstance(out, dict):
        return Verdict(level="V1", passed=False, reasons=("output is not an object",))
    text = normalise(ticket_text)
    missing: list[str] = []
    for field, value in _literals(task, out).items():
        if value is None or isinstance(value, bool):
            continue
        if field in ("policy_number", "report_number", "accident_date"):
            if normalise(str(value)) not in text:
                missing.append(field)
        elif field in ("damage_amount_sar", "sum_insured_sar", "fault_share") and not _number_in(value, text):
            missing.append(field)
    return Verdict(level="V1", passed=not missing, reasons=tuple(f"{f} not found in ticket" for f in missing))
