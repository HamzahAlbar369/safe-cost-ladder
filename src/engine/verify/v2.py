"""V2 consistency (adjudicate only, SPEC §6.3): the model's decision, payout and reasons must agree with each
other and with the published formula applied to the model's OWN stated inputs.

It does not know the right answer: a wrong fact read from the ticket (V1 catches invented literals, not
misread ones) gives a self-consistent wrong answer that passes V2. That false-accept rate is measured on dev.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from engine.datagen.rules import RuleSet
from engine.datagen.rules_engine import round_half_up
from engine.tasks.graders import PAYOUT_TOLERANCE_SAR
from engine.verify import Verdict

PAY_REASONS = ("R3_OWN_DAMAGE", "R4_THIRD_PARTY")
DENY_REASONS = (
    "R0_",
    "R1_",
    "R5_",
    "R6_LATE_REPORT",
    "R8_NO_OWN_COVER",
    "R4_NO_FAULT",
    "R3_BELOW_DEDUCTIBLE",
)
INFO_REASONS = ("R7_",)


def _any(reasons: list[str], prefixes: tuple[str, ...]) -> bool:
    return any(r.startswith(p) for r in reasons for p in prefixes)


def check_consistency(out: Any, rules: RuleSet) -> Verdict:
    problems: list[str] = []
    decision, payout = out["decision"], out["payout_sar"]
    reasons, inputs = list(out["reasons"]), out["inputs"]
    paying = decision in ("approve", "partial")

    if paying != (payout > 0):
        problems.append(f"decision {decision} with payout {payout}")
    problems += _reasons_vs_decision(decision, reasons)
    if paying:
        problems += _recompute(decision, payout, inputs, rules)
    return Verdict(level="V2", passed=not problems, reasons=tuple(problems))


def _reasons_vs_decision(decision: str, reasons: list[str]) -> list[str]:
    deny, info, pay = _any(reasons, DENY_REASONS), _any(reasons, INFO_REASONS), _any(reasons, PAY_REASONS)
    if decision == "need_info":
        return [] if info else ["need_info without an R7 reason"]
    if decision == "deny":
        return [] if deny else ["deny without a denial reason"]
    problems = [] if pay else ["payable decision without a payout reason"]
    if deny or info:
        problems.append("payable decision with a denial / missing-document reason")
    return problems


def _recompute(decision: str, payout: int, inputs: dict[str, Any], rules: RuleSet) -> list[str]:
    v = rules.values()
    damage, fault = inputs["damage_amount_sar"], inputs["fault_share"]
    if inputs["claim_type"] == "third_party_claim":
        if damage is None or fault is None:
            return ["cannot recompute: damage amount or fault share missing"]
        raw = round_half_up(Fraction(damage * fault, 100))
        expected = min(raw, v.tpl_cap_sar)
        expected_decision = "approve" if fault == 100 and raw <= v.tpl_cap_sar else "partial"
    else:
        if inputs["cover"] != "COMP":
            return ["own-damage claim paid under TPL"]
        si = inputs["sum_insured_sar"]
        if damage is None or si is None:
            return ["cannot recompute: repair estimate or sum insured missing"]
        if damage > Fraction(v.etl_pct, 100) * si and not inputs["total_loss"]:
            return [f"repair above {v.etl_pct}% of the sum insured but total_loss is false"]
        base = si if inputs["total_loss"] else min(damage, si)
        party = inputs["other_party"]
        if party == "unknown":
            deductible = 0
        elif party == "none":
            deductible = v.fixed_deductible_sar
        elif fault is None:
            return ["cannot recompute: fault share missing"]
        else:
            deductible = round_half_up(Fraction(v.fixed_deductible_sar * fault, 100))
        expected = base - deductible
        expected_decision = "approve" if base >= damage else "partial"
    problems = []
    if abs(expected - payout) > PAYOUT_TOLERANCE_SAR:
        problems.append(f"payout {payout} but the formula on the stated inputs gives {expected}")
    if expected > 0 and decision != expected_decision:
        problems.append(f"decision {decision} but the stated inputs give {expected_decision}")
    return problems
