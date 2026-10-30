"""Strict JSON schemas for the four task outputs (SPEC §3.1), sent as `output_config.format` (D0.8).

Built from rules.yaml so labels and reason codes have one source. Structured outputs require
`additionalProperties: false` on every object and do not support numeric bounds, so ranges (e.g. fault share
0/25/50/75/100) are checked by the V0 verifier, not the schema.

Property order is generation order. The adjudicate schema puts `inputs` (the facts read from the ticket) and
`reasons` before `decision` and `payout_sar`, so the model states the facts before it decides; the output keys
are exactly SPEC §3.1's.
"""

from __future__ import annotations

import re
from typing import Any

from engine.contracts import TaskType
from engine.datagen.rules import RuleSet
from engine.datagen.sampler import FAQ_KEYS, faq_answer

NULLABLE_INT: dict[str, Any] = {"anyOf": [{"type": "integer"}, {"type": "null"}]}
NULLABLE_STR: dict[str, Any] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
NULLABLE_DATE: dict[str, Any] = {"anyOf": [{"type": "string", "format": "date"}, {"type": "null"}]}


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


OUT_OF_SCOPE = "out_of_scope"


def faq_string_answers(rules: RuleSet) -> list[str]:
    """Every canonical string FAQ answer: those the generator can produce, plus out_of_scope (D1.3)."""
    found = {a for key in FAQ_KEYS if isinstance(a := faq_answer(key, rules), str)}
    return sorted(found | {OUT_OF_SCOPE})


def faq_schema(rules: RuleSet) -> dict[str, Any]:
    strings = {"type": "string", "enum": faq_string_answers(rules)}
    return _obj({"answer": {"anyOf": [{"type": "integer"}, strings]}})


def intent_schema(rules: RuleSet) -> dict[str, Any]:
    return _obj({"intent": {"type": "string", "enum": list(rules.intents)}})


def extract_schema() -> dict[str, Any]:
    return _obj(
        {
            "policy_number": NULLABLE_STR,
            "accident_date": NULLABLE_DATE,
            "report_number": NULLABLE_STR,
            "damage_amount_sar": NULLABLE_INT,
            "fault_share": NULLABLE_INT,
        }
    )


def adjudicate_schema(rules: RuleSet) -> dict[str, Any]:
    inputs = _obj(
        {
            "claim_type": {"type": "string", "enum": list(rules.claim_types)},
            "cover": {"type": "string", "enum": list(rules.cover_types)},
            "accident_date": NULLABLE_DATE,
            "other_party": {"type": "string", "enum": list(rules.other_party)},
            "fault_share": NULLABLE_INT,
            "damage_amount_sar": NULLABLE_INT,
            "sum_insured_sar": NULLABLE_INT,
            "total_loss": {"type": "boolean"},
        }
    )
    return _obj(
        {
            "inputs": inputs,
            "reasons": {"type": "array", "items": {"type": "string", "enum": list(rules.reason_codes)}},
            "decision": {"type": "string", "enum": list(rules.decisions)},
            "payout_sar": {"type": "integer"},
        }
    )


def schema_for(task: TaskType, rules: RuleSet) -> dict[str, Any]:
    return {
        "faq": lambda: faq_schema(rules),
        "intent": lambda: intent_schema(rules),
        "extract": extract_schema,
        "adjudicate": lambda: adjudicate_schema(rules),
    }[task]()


_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def schema_errors(schema: dict[str, Any], value: Any, path: str = "$") -> list[str]:
    """Validate `value` against the subset of JSON Schema the task schemas use (type, enum, anyOf, date
    format, object properties/required/additionalProperties, array items). Empty list = valid."""
    if "anyOf" in schema:
        branches = [schema_errors(b, value, path) for b in schema["anyOf"]]
        return [] if any(not b for b in branches) else [f"{path}: matches no anyOf branch"]
    kind = schema["type"]
    checks = {
        "null": value is None,
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
    }
    if not checks[kind]:
        return [f"{path}: expected {kind}, got {type(value).__name__}"]
    errors: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in enum")
    if schema.get("format") == "date" and not _DATE.fullmatch(value):
        errors.append(f"{path}: {value!r} is not YYYY-MM-DD")
    if kind == "object":
        props = schema["properties"]
        errors += [f"{path}.{k}: required" for k in schema["required"] if k not in value]
        errors += [f"{path}.{k}: unexpected key" for k in value if k not in props]
        for k, sub in props.items():
            if k in value:
                errors += schema_errors(sub, value[k], f"{path}.{k}")
    if kind == "array":
        for i, item in enumerate(value):
            errors += schema_errors(schema["items"], item, f"{path}[{i}]")
    return errors
