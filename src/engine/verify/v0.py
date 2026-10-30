"""V0 format: finished normally, parses, matches the task schema, values in range (SPEC §6.3)."""

from __future__ import annotations

from engine.contracts import TaskType
from engine.datagen.rules import RuleSet
from engine.tasks.schemas import schema_errors, schema_for
from engine.verify import Verdict, parse_output


def check_format(task: TaskType, text: str, rules: RuleSet, *, stop_reason: str | None) -> Verdict:
    problems: list[str] = []
    if stop_reason != "end_turn":
        problems.append(f"stop_reason {stop_reason}")  # max_tokens = truncation, refusal, or no response
    out = parse_output(text)
    if out is None:
        problems.append("not valid JSON")
    else:
        problems += schema_errors(schema_for(task, rules), out)
        problems += _ranges(task, out, rules)
    return Verdict(level="V0", passed=not problems, reasons=tuple(problems))


def _ranges(task: TaskType, out: object, rules: RuleSet) -> list[str]:
    """Numeric ranges the schema cannot express (structured outputs allow no bounds)."""
    if not isinstance(out, dict):
        return []
    shares = rules.values().fault_shares
    problems: list[str] = []

    def share(path: str, value: object) -> None:
        if value is not None and value not in shares:
            problems.append(f"{path} {value} not one of {list(shares)}")

    if task == "extract":
        share("fault_share", out.get("fault_share"))
        problems += _non_negative("damage_amount_sar", out.get("damage_amount_sar"))
    if task == "adjudicate":
        inputs = out.get("inputs")
        if isinstance(inputs, dict):
            share("inputs.fault_share", inputs.get("fault_share"))
        problems += _non_negative("payout_sar", out.get("payout_sar"))
    return problems


def _non_negative(name: str, value: object) -> list[str]:
    return [f"{name} {value} is negative"] if isinstance(value, int) and value < 0 else []
