"""V0-V2 verifiers (SPEC §6.3), plus: every gold answer must pass every verifier (a verifier that rejects
gold would reject correct model answers)."""

from __future__ import annotations

import json

import pytest

from engine.datagen.rules import load_version
from engine.eval.data import load_split
from engine.verify import Verdict, accepted, verify
from engine.verify.v1 import check_grounding
from engine.verify.v2 import check_consistency
from tests.test_graders import gold_as_output

RULES = load_version("v1")


def v(task, out, ticket="", stop="end_turn"):
    text = out if isinstance(out, str) else json.dumps(out)
    return verify(task, text, ticket, RULES, stop_reason=stop)


def failed(verdicts):
    return [x.level for x in verdicts if not x.passed]


# --- V0 ------------------------------------------------------------------------------------------


def test_v0_accepts_valid_and_rejects_bad_format():
    assert failed(v("intent", {"intent": "other"})) == []
    assert failed(v("intent", "not json")) == ["V0"]
    assert failed(v("intent", {"intent": "made_up"})) == ["V0"]
    assert failed(v("intent", {"intent": "other", "x": 1})) == ["V0"]
    assert failed(v("intent", {"intent": "other"}, stop="max_tokens")) == ["V0"]
    assert failed(v("intent", {"intent": "other"}, stop="refusal")) == ["V0"]


def test_v0_ranges():
    base = {"policy_number": None, "accident_date": None, "report_number": None, "damage_amount_sar": None}
    assert failed(v("extract", dict(base, fault_share=30))) == ["V0"]
    assert failed(v("extract", dict(base, fault_share=25), "25")) == []
    assert failed(v("extract", dict(base, fault_share=None, damage_amount_sar=-5))) == ["V0"]


def test_v0_failure_stops_later_levels():
    assert [x.level for x in v("extract", "oops")] == ["V0"]


# --- V1 ------------------------------------------------------------------------------------------

TICKET = "Policy OMI-1234567, accident 18 February 2026, report NJ-30258147. Repair ٢٢٬٥٠٠ SAR, fault 25%."


def ext(**kw):
    out = {
        "policy_number": "OMI-1234567",
        "accident_date": "2026-02-18",
        "report_number": "NJ-30258147",
        "damage_amount_sar": 22500,
        "fault_share": 25,
    }
    return out | kw


def test_v1_grounded_literals_pass_across_digit_and_date_formats():
    assert check_grounding("extract", ext(), TICKET).passed


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("policy_number", "OMI-7654321"),
        ("report_number", "NJ-99999999"),
        ("accident_date", "2026-02-19"),
        ("damage_amount_sar", 2250),
        ("fault_share", 50),
    ],
)
def test_v1_flags_ungrounded_literal(field, value):
    verdict = check_grounding("extract", ext(**{field: value}), TICKET)
    assert not verdict.passed and verdict.reasons == (f"{field} not found in ticket",)


def test_v1_null_passes_and_number_must_match_whole_number():
    assert check_grounding("extract", ext(report_number=None, fault_share=None), TICKET).passed
    assert not check_grounding("extract", ext(damage_amount_sar=225), TICKET).passed  # inside 22500


# --- V2 ------------------------------------------------------------------------------------------


def adj(decision, payout, reasons, **inputs):
    base = {
        "claim_type": "own_damage",
        "cover": "COMP",
        "accident_date": "2026-02-18",
        "other_party": "insured",
        "fault_share": 100,
        "damage_amount_sar": 10000,
        "sum_insured_sar": 80000,
        "total_loss": False,
    }
    return {"inputs": base | inputs, "reasons": reasons, "decision": decision, "payout_sar": payout}


def v2(out):
    return check_consistency(out, RULES)


def test_v2_own_damage_formula_and_decision():
    assert v2(adj("approve", 9000, ["R3_OWN_DAMAGE"])).passed  # 10000 - 1000 x 100%
    assert v2(adj("approve", 9000, ["R3_OWN_DAMAGE"], fault_share=100)).passed
    assert v2(adj("approve", 9750, ["R3_OWN_DAMAGE"], fault_share=25)).passed
    assert v2(adj("approve", 9000, ["R3_OWN_DAMAGE"], other_party="unknown")).passed is False
    assert v2(adj("approve", 10000, ["R3_OWN_DAMAGE"], other_party="unknown")).passed
    assert v2(adj("approve", 9000, ["R3_OWN_DAMAGE"], other_party="none")).passed
    wrong = v2(adj("approve", 8000, ["R3_OWN_DAMAGE"]))
    assert not wrong.passed and "formula" in wrong.reasons[0]
    assert v2(adj("approve", 9001, ["R3_OWN_DAMAGE"])).passed  # within ±1 SAR


def test_v2_total_loss_and_cap():
    assert v2(
        adj("approve", 79000, ["R3_OWN_DAMAGE", "R3_TOTAL_LOSS"], damage_amount_sar=50000, total_loss=True)
    ).passed
    missed = v2(adj("approve", 49000, ["R3_OWN_DAMAGE"], damage_amount_sar=50000))  # > 60% of 80000
    assert not missed.passed and "total_loss is false" in missed.reasons[0]
    cap = adj(
        "partial", 79000, ["R3_OWN_DAMAGE", "R3_TOTAL_LOSS", "R3_SUM_INSURED_CAP"], damage_amount_sar=90000
    )
    assert v2(cap | {"inputs": cap["inputs"] | {"total_loss": True}}).passed
    mislabelled = adj("approve", 79000, ["R3_OWN_DAMAGE"], damage_amount_sar=90000, total_loss=True)
    assert not v2(mislabelled).passed  # base 80000 < repair 90000 means partial


def test_v2_third_party():
    tp = {
        "claim_type": "third_party_claim",
        "damage_amount_sar": 32400,
        "fault_share": 25,
        "sum_insured_sar": None,
    }
    assert v2(adj("partial", 8100, ["R4_THIRD_PARTY"], **tp)).passed
    assert not v2(adj("approve", 8100, ["R4_THIRD_PARTY"], **tp)).passed
    full = tp | {"fault_share": 100}
    assert v2(adj("approve", 32400, ["R4_THIRD_PARTY"], **full)).passed
    capped = tp | {"fault_share": 100, "damage_amount_sar": 20_000_000}
    assert v2(adj("partial", 10_000_000, ["R4_THIRD_PARTY", "R4_CAP"], **capped)).passed


def test_v2_decision_vs_payout_and_reasons():
    assert not v2(adj("deny", 500, ["R6_LATE_REPORT"])).passed
    assert not v2(adj("approve", 0, ["R3_OWN_DAMAGE"])).passed
    assert v2(adj("deny", 0, ["R6_LATE_REPORT"])).passed
    assert not v2(adj("deny", 0, ["R3_OWN_DAMAGE"])).passed  # deny without a denial reason
    assert v2(adj("need_info", 0, ["R7_MISSING_registration"])).passed
    assert not v2(adj("need_info", 0, ["R6_LATE_REPORT"])).passed
    assert not v2(adj("approve", 9000, ["R3_OWN_DAMAGE", "R6_LATE_REPORT"])).passed


def test_v2_cannot_recompute_with_missing_inputs_fails_payable():
    assert not v2(adj("approve", 9000, ["R3_OWN_DAMAGE"], damage_amount_sar=None)).passed
    assert not v2(adj("approve", 9000, ["R3_OWN_DAMAGE"], fault_share=None)).passed
    assert not v2(adj("approve", 9000, ["R3_OWN_DAMAGE"], cover="TPL")).passed


# --- gold must pass its own verifiers -------------------------------------------------------------


@pytest.mark.parametrize("split", ["dev", "shifted"])
def test_gold_passes_v0_and_v1(split):
    """V0 must accept every gold. V1 must accept every gold whose `inputs` the ticket actually states: a
    garbled / empty ticket (adversarial) states nothing, so its engine-derived gold `inputs` are not a model
    answer to ground (a model would return null there). Counts only are asserted."""
    n_v0 = n_v1 = 0
    for t in load_split(split):
        verdicts = verify(t.task_type, json.dumps(gold_as_output(t)), t.text, RULES, stop_reason="end_turn")
        n_v0 += not verdicts[0].passed
        if t.meta.adversarial_kind != "garbled_or_empty":
            n_v1 += any(not x.passed for x in verdicts if x.level == "V1")
    assert n_v0 == 0, f"{split}: {n_v0} gold outputs fail V0"
    assert n_v1 == 0, f"{split}: {n_v1} gold outputs fail V1"


def test_accepted_helper():
    assert accepted([]) and not accepted([Verdict(level="V0", passed=False)])
