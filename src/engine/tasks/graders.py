"""Graders (SPEC §3.1): pure code, no model calls.

Normalisation: Arabic-Indic digits -> ASCII, thousands separators stripped, dates -> ISO, case/whitespace
fold (`datagen.normalize.normalise`). A malformed or missing field is wrong, never an exception.
"""

from __future__ import annotations

from typing import Any

from engine.contracts import Frozen, TaskType
from engine.datagen.normalize import normalise

PAYOUT_TOLERANCE_SAR = 1  # SPEC §3.1: payout within ±1 SAR
EXTRACT_FIELDS = ("policy_number", "accident_date", "report_number", "damage_amount_sar", "fault_share")


class Grade(Frozen):
    correct: bool
    fields: dict[str, bool] = {}  # per-field correctness (extract: all five; adjudicate: decision, payout)


def norm_value(value: Any) -> str | None:
    """Canonical comparable form of a scalar; None stays None. Floats with no fraction compare as ints."""
    if value is None or isinstance(value, dict | list):
        return None
    if isinstance(value, bool):
        return str(value).casefold()
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return normalise(str(value))


def as_int(value: Any) -> int | None:
    text = norm_value(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _same(output: Any, gold: Any) -> bool:
    return norm_value(output) == norm_value(gold)


def grade_faq(gold: dict[str, Any], out: dict[str, Any]) -> Grade:
    return Grade(correct=_same(out.get("answer"), gold["answer"]))


def grade_intent(gold: dict[str, Any], out: dict[str, Any]) -> Grade:
    return Grade(correct=_same(out.get("intent"), gold["intent"]))


def grade_extract(gold: dict[str, Any], out: dict[str, Any]) -> Grade:
    fields = {f: _same(out.get(f), gold[f]) for f in EXTRACT_FIELDS}
    return Grade(correct=all(fields.values()), fields=fields)


def grade_adjudicate(gold: dict[str, Any], out: dict[str, Any]) -> Grade:
    payout = as_int(out.get("payout_sar"))
    fields = {
        "decision": _same(out.get("decision"), gold["decision"]),
        "payout": payout is not None and abs(payout - gold["payout_sar"]) <= PAYOUT_TOLERANCE_SAR,
    }
    return Grade(correct=all(fields.values()), fields=fields)


GRADERS = {
    "faq": grade_faq,
    "intent": grade_intent,
    "extract": grade_extract,
    "adjudicate": grade_adjudicate,
}


def grade(task: TaskType, gold: dict[str, Any], out: Any) -> Grade:
    """Grade a parsed model output against the gold dict (`Ticket.gold.model_dump(mode="json")`)."""
    if not isinstance(out, dict):
        return Grade(correct=False)
    return GRADERS[task](gold, out)
