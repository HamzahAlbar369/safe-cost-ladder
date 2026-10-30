"""Risk-tiered verifiers V0-V2 (SPEC §6.3): pure code, no model calls, no access to gold.

V0 format · V1 grounding (extracted literals appear in the ticket) · V2 consistency (payout recomputed from
the model's own stated inputs, decision consistent with its reasons). V3 (second opinion) is a policy-level
check added in Phase 3.
"""

from __future__ import annotations

import json
from typing import Any

from engine.contracts import Frozen, TaskType
from engine.datagen.rules import RuleSet
from engine.tasks.schemas import schema_for


class Verdict(Frozen):
    level: str  # "V0" | "V1" | "V2"
    passed: bool
    reasons: tuple[str, ...] = ()  # why it failed (empty when passed)


def parse_output(text: str) -> Any:
    """The model's JSON object, or None if the text is not valid JSON."""
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def verify(
    task: TaskType, text: str, ticket_text: str, rules: RuleSet, *, stop_reason: str | None = "end_turn"
) -> list[Verdict]:
    """Run V0, then V1 and V2 where they apply to the task. Later levels run only if V0 passed."""
    from engine.verify.v0 import check_format
    from engine.verify.v1 import check_grounding
    from engine.verify.v2 import check_consistency

    v0 = check_format(task, text, rules, stop_reason=stop_reason)
    verdicts = [v0]
    if not v0.passed:
        return verdicts
    out = parse_output(text)
    if task in ("extract", "adjudicate"):
        verdicts.append(check_grounding(task, out, ticket_text))
    if task == "adjudicate":
        verdicts.append(check_consistency(out, rules))
    return verdicts


def accepted(verdicts: list[Verdict]) -> bool:
    return all(v.passed for v in verdicts)


__all__ = ["Verdict", "accepted", "parse_output", "schema_for", "verify"]
