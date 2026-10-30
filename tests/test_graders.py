"""Graders (SPEC §3.1) and the gold <-> schema <-> grader round trip over all three splits.

The held-out file is read here by this automated test only (schema/grade counts); no item is printed.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from engine.contracts import Ticket
from engine.datagen.rules import load_version
from engine.llm.pricing import ROOT
from engine.tasks.graders import grade
from engine.tasks.schemas import schema_errors, schema_for

SPLITS = ("dev", "heldout", "shifted")
SCHEMA_INPUT_KEYS = (
    "claim_type",
    "cover",
    "accident_date",
    "other_party",
    "fault_share",
    "damage_amount_sar",
    "sum_insured_sar",
    "total_loss",
)


def load(split: str) -> list[Ticket]:
    """Parse a split. Failures report counts only: pydantic errors quote the offending item, and the
    held-out items must never be shown."""
    path = ROOT / "data" / "generated" / f"{split}.jsonl"
    tickets, failed = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            tickets.append(Ticket.model_validate_json(line))
        except ValidationError:
            failed += 1
    if failed:
        raise AssertionError(f"{split}: {failed} of {failed + len(tickets)} items fail the Ticket contract")
    return tickets


def gold_as_output(t: Ticket) -> dict:
    """Gold in the shape a model must return. Only adjudicate `inputs` is adapted: the engine's trace
    inputs hold different keys (e.g. recovery_cases); `inputs` is reported, never graded."""
    gold = t.gold.model_dump(mode="json")
    if t.task_type == "adjudicate":
        inputs = gold["inputs"]
        gold["inputs"] = {k: inputs.get(k, False if k == "total_loss" else None) for k in SCHEMA_INPUT_KEYS}
    return gold


@pytest.mark.parametrize("split", SPLITS)
def test_every_gold_validates_against_its_schema_and_grades_100_percent(split):
    """Assertions compare counts only, so a failure prints neither ids nor values (held-out stays unseen)."""
    tickets = load(split)
    n_bad_schema = n_bad_grade = 0
    for t in tickets:
        schema = schema_for(t.task_type, load_version(t.rules_version))
        out = gold_as_output(t)
        n_bad_schema += bool(schema_errors(schema, out))
        n_bad_grade += not grade(t.task_type, t.gold.model_dump(mode="json"), out).correct
    n = len(tickets)
    print(f"{split}: n={n} schema_ok={n - n_bad_schema} graded_ok={n - n_bad_grade}")
    assert len(tickets) > 0
    assert n_bad_schema == 0, f"{split}: {n_bad_schema} gold outputs violate their schema"
    assert n_bad_grade == 0, f"{split}: {n_bad_grade} gold outputs do not grade correct vs themselves"


@pytest.mark.parametrize("split", SPLITS)
def test_faq_string_gold_is_within_the_enum(split):
    allowed = {"yes", "no", "out_of_scope"}
    strings = [t.gold.answer for t in load(split) if t.task_type == "faq" and isinstance(t.gold.answer, str)]
    n_outside = sum(a not in allowed for a in strings)
    assert n_outside == 0, f"{split}: {n_outside} FAQ string answers outside the enum"


# --- grader behaviour -----------------------------------------------------------------------------


def g(task, gold, out):
    return grade(task, gold, out).correct


def test_faq_normalises_numbers_and_case():
    assert g("faq", {"answer": 1000}, {"answer": 1000})
    assert g("faq", {"answer": 1000}, {"answer": "1,000"})
    assert g("faq", {"answer": 1000}, {"answer": "١٠٠٠"})
    assert g("faq", {"answer": "yes"}, {"answer": " Yes "})
    assert not g("faq", {"answer": 1000}, {"answer": 2000})
    assert not g("faq", {"answer": "no"}, {"answer": "yes"})


def test_intent_exact_label():
    assert g("intent", {"intent": "new_claim"}, {"intent": "new_claim"})
    assert not g("intent", {"intent": "new_claim"}, {"intent": "claim_status"})


EXTRACT_GOLD = {
    "policy_number": "OMI-1234567",
    "accident_date": "2026-02-18",
    "report_number": None,
    "damage_amount_sar": 22500,
    "fault_share": 25,
}


def test_extract_all_fields_exact_and_per_field_scores():
    assert g("extract", EXTRACT_GOLD, dict(EXTRACT_GOLD))
    ar = dict(
        EXTRACT_GOLD, damage_amount_sar="٢٢٬٥٠٠", accident_date="2026/02/18", policy_number="omi-1234567"
    )
    assert g("extract", EXTRACT_GOLD, ar)
    wrong = dict(EXTRACT_GOLD, report_number="NJ-12345678", fault_share=50)
    result = grade("extract", EXTRACT_GOLD, wrong)
    assert not result.correct
    assert result.fields == {
        "policy_number": True,
        "accident_date": True,
        "report_number": False,
        "damage_amount_sar": True,
        "fault_share": False,
    }


def test_extract_null_is_not_zero_or_empty():
    assert not g("extract", EXTRACT_GOLD, dict(EXTRACT_GOLD, report_number=""))
    assert not g("extract", dict(EXTRACT_GOLD, fault_share=0), dict(EXTRACT_GOLD, fault_share=None))
    assert not g("extract", EXTRACT_GOLD, dict(EXTRACT_GOLD, accident_date=None))


ADJ_GOLD = {"decision": "partial", "payout_sar": 8100, "reasons": ["R4_THIRD_PARTY"], "inputs": {}}


def test_adjudicate_decision_exact_and_payout_within_one_riyal():
    assert g("adjudicate", ADJ_GOLD, {"decision": "partial", "payout_sar": 8100})
    assert g("adjudicate", ADJ_GOLD, {"decision": "partial", "payout_sar": 8101})
    assert g("adjudicate", ADJ_GOLD, {"decision": "partial", "payout_sar": 8099})
    assert g("adjudicate", ADJ_GOLD, {"decision": "partial", "payout_sar": "٨١٠٠"})
    assert not g("adjudicate", ADJ_GOLD, {"decision": "partial", "payout_sar": 8102})
    assert not g("adjudicate", ADJ_GOLD, {"decision": "approve", "payout_sar": 8100})
    assert not g("adjudicate", ADJ_GOLD, {"decision": "partial", "payout_sar": None})


def test_malformed_output_is_wrong_not_an_error():
    for out in (None, [], "approve", json.loads("{}")):
        assert not g("adjudicate", ADJ_GOLD, out)
        assert not g("extract", EXTRACT_GOLD, out)
        assert not g("intent", {"intent": "other"}, out)
        assert not g("faq", {"answer": 1}, out)
