"""Task prompts and output schemas (SPEC §3.1, §6.2)."""

from __future__ import annotations

import json
import re

import pytest

from engine.contracts import AdjudicateGold, ExtractGold, FaqGold, IntentGold
from engine.datagen.rules import load_version
from engine.tasks.prompts import MAX_TOKENS, TASKS, policy_document, system_prompt, user_prompt
from engine.tasks.schemas import schema_for

RULES = load_version("v1")


def test_system_prompt_is_static_and_deterministic():
    system_prompt.cache_clear()
    a = system_prompt()
    system_prompt.cache_clear()
    assert a == system_prompt()
    assert not re.search(r"\d{4}-\d{2}-\d{2}T|\{[a-z_]+\}", a)  # no timestamps, no unfilled placeholders


def test_system_prompt_holds_every_task_label_and_the_english_policy_only():
    s = system_prompt()
    for task in TASKS:
        assert f"## Task: {task}" in s
    for label, definition in RULES.intents.items():
        assert f"- {label}: {definition}" in s
    for code in RULES.reason_codes:
        assert f"- {code}:" in s
    assert s.rstrip().endswith(policy_document("v1").rstrip())
    assert "FICTIONAL INSURER" in s
    assert policy_document("v1") in s and "وثيقة تأمين المركبات" not in s  # Arabic policy not included


def test_extract_instructions_d1_12():
    s = system_prompt()
    assert "Every field the ticket does not state is null" in s
    assert "means accident_date is null" in s and "قبل أيام" in s


def test_user_prompt_is_task_and_ticket_only():
    assert user_prompt("faq", "hello") == "Task: faq\n\n<ticket>\nhello\n</ticket>"


@pytest.mark.parametrize(
    ("task", "gold"),
    [("faq", FaqGold), ("intent", IntentGold), ("extract", ExtractGold), ("adjudicate", AdjudicateGold)],
)
def test_schema_keys_match_gold_contract(task, gold):
    schema = schema_for(task, RULES)
    assert set(schema["properties"]) == set(gold.model_fields)
    _strict(schema)
    json.dumps(schema)  # serialisable


def _strict(node):
    """Structured outputs: every object has additionalProperties false and requires all its keys."""
    if isinstance(node, dict):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
        assert not {"minimum", "maximum", "minLength", "maxLength"} & node.keys()
        for v in node.values():
            _strict(v)
    elif isinstance(node, list):
        for v in node:
            _strict(v)


def test_enums_come_from_rules():
    assert schema_for("intent", RULES)["properties"]["intent"]["enum"] == list(RULES.intents)
    adj = schema_for("adjudicate", RULES)["properties"]
    assert adj["decision"]["enum"] == ["approve", "partial", "deny", "need_info"]
    assert adj["reasons"]["items"]["enum"] == list(RULES.reason_codes)


def test_max_tokens_cover_every_task():
    assert set(MAX_TOKENS) == set(TASKS)
    assert all(v >= 2048 for v in MAX_TOKENS.values())
