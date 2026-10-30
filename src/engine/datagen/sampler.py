"""Seeded case sampling per task × level (SPEC §3.2, §4.2 step 1). FICTIONAL facts.

Each adjudication design names the rule(s) it exercises and the decision it expects. The rules engine computes
the gold; if it disagrees with the design's expectation the generator raises (a generator bug, not a label).
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from fractions import Fraction
from typing import Any

from engine.contracts import Case
from engine.datagen.rules import RuleSet
from engine.datagen.rules_engine import business_day_deadline, round_half_up

ALL_DOCS = ("accident_report", "registration", "licence_copy", "damage_photos", "damage_assessment")
START, END = date(2026, 1, 4), date(2026, 9, 30)
AUTHORISED = ("named_driver", "relative", "domestic_worker", "sponsored_driver")
UNAUTHORISED = ("unauthorised_friend", "unauthorised_colleague")
ART6 = ("fled_scene", "intoxication", "racing_or_drifting", "deliberate", "misrepresentation")
ART5 = ("wrong_direction", "red_light", "use_outside_purpose")
CMIR_716 = ("red_light", "wrong_direction", "racing_or_drifting")


@dataclass
class Draft:
    """A sampled case plus how the text should present it."""

    case: Case
    expected: str
    design: str
    rule_ids: tuple[str, ...]
    view: dict[str, Any] = field(default_factory=dict)
    distractors: tuple[str, ...] = ()


def _digits(rng: random.Random, n: int) -> str:
    return "".join(str(rng.randrange(10)) for _ in range(n))


def _date(rng: random.Random) -> date:
    return START + timedelta(days=rng.randrange((END - START).days))


def base(
    rng: random.Random,
    rules: RuleSet,
    claim_type: str,
    cover: str = "COMP",
    other: str = "insured",
    **over: Any,
) -> dict[str, Any]:
    v = rules.values()
    acc = _date(rng)
    src = (
        "traffic_police"
        if (other in ("unknown", "none") and rng.random() < 0.5) or rng.random() < 0.15
        else "najm"
    )
    fault: int | None
    if claim_type == "third_party_claim":
        fault = rng.choice([25, 50, 75, 100])
    elif other in ("insured", "uninsured"):
        fault = rng.choice([0, 25, 50, 75, 100])
    else:
        fault = None
    od = claim_type == "own_damage"
    damage = rng.randrange(25, 450) * 100 if od else rng.randrange(20, 600) * 100
    si = None
    if od and cover == "COMP":  # sum insured high enough that the repair is not a total loss
        floor = int(damage * 100 / v.etl_pct) // 1000 + 2
        si = rng.randrange(max(floor, 40), max(floor, 40) + 160) * 1000
    case = dict(
        claim_type=claim_type,
        cover=cover,
        policy_number=f"OMI-{_digits(rng, 7)}",
        policy_end_date=acc + timedelta(days=rng.randrange(20, 300)),
        accident_date=acc,
        report_date=acc + timedelta(days=rng.randrange(0, v.reporting_window_days + 1)),
        report_source=src,
        report_number=("NJ-" if src == "najm" else "TP-") + _digits(rng, 8),
        other_party=other,
        fault_share=fault,
        damage_amount_sar=damage,
        sum_insured_sar=si,
        documents=ALL_DOCS,
    )
    case.update(over)
    return case


Builder = Callable[[random.Random, RuleSet], Draft]


def _d(name: str, rules_ids: tuple[str, ...], expected: str, case: dict[str, Any], **view: Any) -> Draft:
    return Draft(case=Case(**case), expected=expected, design=name, rule_ids=rules_ids, view=view)


# --- L3: one rule decides ------------------------------------------------------------------------------


def od_comp_repair(rng, rules):
    other = rng.choice(["insured", "insured", "uninsured"])
    return _d("od_comp_repair", ("R3",), "approve", base(rng, rules, "own_damage", other=other))


def od_comp_hit_and_run(rng, rules):
    return _d("od_comp_hit_and_run", ("R3", "R8"), "approve", base(rng, rules, "own_damage", other="unknown"))


def od_comp_single_vehicle(rng, rules):
    return _d("od_comp_single_vehicle", ("R3",), "approve", base(rng, rules, "own_damage", other="none"))


def tp_full_fault(rng, rules):
    c = base(rng, rules, "third_party_claim", cover=rng.choice(["TPL", "COMP"]), fault_share=100)
    return _d("tp_full_fault", ("R4",), "approve", c)


def tp_partial_fault(rng, rules):
    c = base(
        rng,
        rules,
        "third_party_claim",
        cover=rng.choice(["TPL", "COMP"]),
        fault_share=rng.choice([25, 50, 75]),
    )
    return _d("tp_partial_fault", ("R4", "R2"), "partial", c)


def tp_no_fault(rng, rules):
    c = base(rng, rules, "third_party_claim", cover=rng.choice(["TPL", "COMP"]), fault_share=0)
    return _d("tp_no_fault", ("R4", "R2"), "deny", c)


def od_under_tpl(rng, rules):
    return _d("od_under_tpl", ("R1",), "deny", base(rng, rules, "own_damage", cover="TPL"))


def late_no_reason(rng, rules):
    c = base(rng, rules, rng.choice(["own_damage", "third_party_claim"]))
    w = rules.values().reporting_window_days
    c["report_date"] = c["accident_date"] + timedelta(days=w + rng.randrange(1, 40))
    return _d("late_no_reason", ("R6",), "deny", c)


def od_below_deductible(rng, rules):
    fixed = rules.values().fixed_deductible_sar
    c = base(rng, rules, "own_damage", damage_amount_sar=rng.randrange(3, fixed // 100 + 1) * 100)
    return _d("od_below_deductible", ("R3",), "deny", c)


def policy_expired(rng, rules):
    c = base(rng, rules, rng.choice(["own_damage", "third_party_claim"]))
    c["policy_end_date"] = c["accident_date"] - timedelta(days=rng.randrange(1, 60))
    return _d("policy_expired", ("R1",), "deny", c)


# --- L4: 2-3 interacting rules + distractors -----------------------------------------------------------


def od_total_loss_etl(rng, rules):
    v = rules.values()
    c = base(rng, rules, "own_damage")
    si = rng.randrange(30, 120) * 1000
    lo = si * v.etl_pct // 100 // 100 + 1
    c.update(sum_insured_sar=si, damage_amount_sar=rng.randrange(lo, si // 100 + 1) * 100)
    return _d("od_total_loss_etl", ("R3",), "approve", c)


def od_over_sum_insured(rng, rules):
    c = base(rng, rules, "own_damage", other=rng.choice(["insured", "unknown", "none"]))
    si = rng.randrange(25, 90) * 1000
    c.update(sum_insured_sar=si, damage_amount_sar=si + rng.randrange(1, 150) * 100)
    return _d("od_over_sum_insured", ("R3", "R8"), "partial", c)


def od_technical_total_loss(rng, rules):
    """Assessor declares a technical total loss though repair is below the ETL threshold (35%..ETL% of SI)."""
    v = rules.values()
    si = rng.randrange(40, 150) * 1000
    lo, hi = si * 35 // 100 // 100, si * v.etl_pct // 100 // 100
    c = base(
        rng,
        rules,
        "own_damage",
        technical_total_loss=True,
        sum_insured_sar=si,
        damage_amount_sar=rng.randrange(lo, hi + 1) * 100,
    )
    return _d("od_technical_total_loss", ("R3",), "approve", c)


def tp_recovery_violation(rng, rules):
    fault = rng.choice([50, 75, 100])
    c = base(
        rng,
        rules,
        "third_party_claim",
        cover=rng.choice(["TPL", "COMP"]),
        fault_share=fault,
        violations=(rng.choice(ART5),),
        violation_caused_accident=True,
    )
    return _d("tp_recovery_violation", ("R5", "R4"), "approve" if fault == 100 else "partial", c)


def tp_licence_grace(rng, rules):
    g = rules.values().tp_licence_grace_days
    fault = rng.choice([50, 75, 100])
    c = base(rng, rules, "third_party_claim", fault_share=fault, licence_status="expired")
    gap = rng.choice([rng.randrange(1, g + 1), rng.randrange(g + 1, g + 25)])
    c["licence_renewal_date"] = c["accident_date"] + timedelta(days=gap)
    c["licence_expiry_date"] = c["accident_date"] - timedelta(days=rng.randrange(3, 60))
    return _d("tp_licence_grace", ("R5", "R4"), "approve" if fault == 100 else "partial", c)


def od_licence_grace_business(rng, rules):
    v = rules.values()
    c = base(rng, rules, "own_damage", licence_status="expired")
    gap = rng.choice([rng.randrange(20, 70), rng.randrange(72, 100)])
    renew = c["accident_date"] + timedelta(days=gap)
    c["licence_renewal_date"] = renew
    ok = renew <= business_day_deadline(c["accident_date"], v.od_licence_grace_business_days, v.business_days)
    c["licence_expiry_date"] = c["accident_date"] - timedelta(days=rng.randrange(3, 60))
    return _d("od_licence_grace_business", ("R5", "R3"), "approve" if ok else "deny", c)


def od_invalid_licence(rng, rules):
    c = base(rng, rules, "own_damage", licence_status=rng.choice(["none", "wrong_class", "forfeited"]))
    return _d("od_invalid_licence", ("R5",), "deny", c)


def od_driver_authorised(rng, rules):
    return _d(
        "od_driver_authorised",
        ("R5", "R3"),
        "approve",
        base(rng, rules, "own_damage", driver=rng.choice(AUTHORISED)),
    )


def od_driver_unauthorised(rng, rules):
    return _d(
        "od_driver_unauthorised",
        ("R5",),
        "deny",
        base(rng, rules, "own_damage", driver=rng.choice(UNAUTHORISED)),
    )


def od_violation_not_cause(rng, rules):
    c = base(rng, rules, "own_damage", violations=(rng.choice(CMIR_716),), violation_caused_accident=False)
    return _d("od_violation_not_cause", ("R5", "R3"), "approve", c)


def od_violation_cause(rng, rules):
    c = base(rng, rules, "own_damage", violations=(rng.choice(CMIR_716),), violation_caused_accident=True)
    return _d("od_violation_cause", ("R5",), "deny", c)


def late_accepted_reason(rng, rules):
    ctype = rng.choice(["own_damage", "third_party_claim"])
    c = base(rng, rules, ctype)
    w = rules.values().reporting_window_days
    c["report_date"] = c["accident_date"] + timedelta(days=w + rng.randrange(1, 40))
    c["late_justification"] = rng.choice(
        ["hospitalisation", "travel_outside_kingdom", "official_report_delay"]
    )
    exp = "approve" if ctype == "own_damage" or c["fault_share"] == 100 else "partial"
    return _d("late_accepted_reason", ("R6", "R3" if ctype == "own_damage" else "R4"), exp, c)


def late_rejected_reason(rng, rules):
    c = base(rng, rules, rng.choice(["own_damage", "third_party_claim"]))
    w = rules.values().reporting_window_days
    c["report_date"] = c["accident_date"] + timedelta(days=w + rng.randrange(1, 40))
    c["late_justification"] = rng.choice(["busy", "forgot", "unaware_of_deadline"])
    return _d("late_rejected_reason", ("R6",), "deny", c)


def tpl_hit_and_run(rng, rules):
    other = rng.choice(["unknown", "uninsured"])
    return _d(
        "tpl_hit_and_run", ("R8", "R1"), "deny", base(rng, rules, "own_damage", cover="TPL", other=other)
    )


def tp_art6_deny(rng, rules):
    c = base(rng, rules, "third_party_claim", violations=(rng.choice(ART6),), violation_caused_accident=True)
    return _d("tp_art6_deny", ("R5",), "deny", c)


def policy_end_boundary(rng, rules):
    c = base(rng, rules, "own_damage")
    c["policy_end_date"] = c["accident_date"]
    return _d("policy_end_boundary", ("R1", "R3"), "approve", c)


def od_zero_fault(rng, rules):
    return _d("od_zero_fault", ("R3", "R2"), "approve", base(rng, rules, "own_damage", fault_share=0))


def tp_drifting_vs_od(rng, rules):
    """Drifting on a third-party claim is UP Art. 6 (deny) even when the report doesn't call it the cause."""
    c = base(
        rng, rules, "third_party_claim", violations=("racing_or_drifting",), violation_caused_accident=False
    )
    return _d("tp_drifting_vs_od", ("R5",), "deny", c)


# --- L5: missing / contradictory information, or a specific deny that beats need_info ------------------


def _drop(rng: random.Random, k: int, keep: tuple[str, ...] = ()) -> tuple[str, ...]:
    droppable = [d for d in ALL_DOCS if d not in keep]
    gone = set(rng.sample(droppable, k))
    return tuple(d for d in ALL_DOCS if d not in gone)


def _no_report(c: dict[str, Any]) -> dict[str, Any]:
    """Keep stated facts consistent with the documents: no report -> no report number; no damage assessment ->
    the amount the customer states can only be a garage quote (D1.10)."""
    if "accident_report" not in c["documents"]:
        c["report_number"] = None
    if "damage_assessment" not in c["documents"]:
        c["damage_source"] = "garage_quote"
    return c


def missing_doc(rng, rules):
    c = base(rng, rules, rng.choice(["own_damage", "third_party_claim"]), documents=_drop(rng, 1))
    return _d("missing_doc", ("R7",), "need_info", _no_report(c), explicit_missing=rng.random() < 0.5)


def missing_two_docs(rng, rules):
    c = base(rng, rules, rng.choice(["own_damage", "third_party_claim"]), documents=_drop(rng, 2))
    return _d("missing_two_docs", ("R7",), "need_info", _no_report(c), explicit_missing=rng.random() < 0.5)


def conflict_amount(rng, rules):
    c = base(rng, rules, rng.choice(["own_damage", "third_party_claim"]))
    delta = rng.randrange(5, 40) * 100
    sign = -1 if c["damage_amount_sar"] - delta > 2_000 and rng.random() < 0.5 else 1
    c["conflict_damage_sar"] = c["damage_amount_sar"] + sign * delta
    return _d("conflict_amount", ("R7",), "need_info", c)


def garage_quote_only(rng, rules):
    """Only a garage/workshop quote, no damage assessment report: need_info (R7), even for a small amount."""
    docs = tuple(d for d in ALL_DOCS if d != "damage_assessment")
    c = base(
        rng,
        rules,
        rng.choice(["own_damage", "third_party_claim"]),
        documents=docs,
        damage_source="garage_quote",
    )
    return _d("garage_quote_only", ("R7",), "need_info", c)


def missing_assessment_small_loss(rng, rules):
    fixed = rules.values().fixed_deductible_sar
    docs = tuple(d for d in ALL_DOCS if d != "damage_assessment")
    c = base(
        rng, rules, "own_damage", documents=docs, damage_amount_sar=rng.randrange(3, fixed // 100 + 1) * 100
    )
    return _d(
        "missing_assessment_small_loss", ("R7", "R3"), "need_info", _no_report(c), explicit_missing=True
    )


def excluded_and_missing(rng, rules):
    if rng.random() < 0.5:
        c = base(
            rng,
            rules,
            "own_damage",
            licence_status=rng.choice(["none", "forfeited"]),
            documents=_drop(rng, 1),
        )
        rid = ("R5", "R7")
    else:
        c = base(
            rng,
            rules,
            "third_party_claim",
            violations=(rng.choice(ART6),),
            violation_caused_accident=True,
            documents=_drop(rng, 1),
        )
        rid = ("R5", "R7")
    return _d("excluded_and_missing", rid, "deny", _no_report(c), explicit_missing=True)


def below_deductible_missing_other(rng, rules):
    fixed = rules.values().fixed_deductible_sar
    c = base(
        rng,
        rules,
        "own_damage",
        documents=_drop(rng, 1, keep=("damage_assessment",)),
        damage_amount_sar=rng.randrange(3, fixed // 100 + 1) * 100,
    )
    return _d("below_deductible_missing_other", ("R3", "R7"), "deny", _no_report(c), explicit_missing=True)


def late_and_missing(rng, rules):
    c = base(rng, rules, rng.choice(["own_damage", "third_party_claim"]), documents=_drop(rng, 1))
    w = rules.values().reporting_window_days
    c["report_date"] = c["accident_date"] + timedelta(days=w + rng.randrange(1, 40))
    return _d("late_and_missing", ("R6", "R7"), "deny", _no_report(c), explicit_missing=True)


# weights balance the decision labels (D1.8: none under 10% of adjudication items)
DESIGNS: dict[str, list[tuple[Builder, float]]] = {
    "L3": [
        (od_comp_repair, 2.0),
        (od_comp_hit_and_run, 1.0),
        (od_comp_single_vehicle, 1.0),
        (tp_full_fault, 1.5),
        (tp_partial_fault, 3.5),
        (tp_no_fault, 1.0),
        (od_under_tpl, 1.0),
        (late_no_reason, 1.0),
        (od_below_deductible, 1.0),
        (policy_expired, 1.0),
    ],
    "L4": [
        (od_total_loss_etl, 1.0),
        (od_over_sum_insured, 1.8),
        (od_technical_total_loss, 0.7),
        (tp_recovery_violation, 1.5),
        (tp_licence_grace, 1.2),
        (od_licence_grace_business, 1.0),
        (od_invalid_licence, 0.7),
        (od_driver_authorised, 0.8),
        (od_driver_unauthorised, 0.7),
        (od_violation_not_cause, 0.8),
        (od_violation_cause, 0.7),
        (late_accepted_reason, 1.0),
        (late_rejected_reason, 0.6),
        (tpl_hit_and_run, 0.7),
        (tp_art6_deny, 0.8),
        (policy_end_boundary, 0.5),
        (od_zero_fault, 0.6),
        (tp_drifting_vs_od, 0.4),
    ],
    "L5": [
        (missing_doc, 2.0),
        (missing_two_docs, 1.0),
        (conflict_amount, 1.5),
        (garage_quote_only, 1.0),
        (missing_assessment_small_loss, 0.8),
        (excluded_and_missing, 1.0),
        (below_deductible_missing_other, 0.8),
        (late_and_missing, 0.8),
    ],
}

DISTRACTORS_PER_LEVEL = {"L3": (0, 1), "L4": (1, 2), "L5": (0, 1)}


def sample_adjudication(rng: random.Random, rules: RuleSet, level: str) -> Draft:
    builders, weights = zip(*DESIGNS[level], strict=True)
    return rng.choices(builders, weights=weights)[0](rng, rules)


def sample_extract_case(rng: random.Random, rules: RuleSet) -> tuple[Case, dict[str, bool]]:
    """Own-damage case for extraction; each field is shown or withheld (gold null when withheld)."""
    other = rng.choice(["insured", "insured", "uninsured", "unknown", "none"])
    case = Case(**base(rng, rules, "own_damage", other=other))
    show = {k: rng.random() > 0.25 for k in ("pn", "acc", "rn", "amt", "fault")}
    if sum(show.values()) < 2:
        show["pn"] = show["amt"] = True
    return case, show


def faq_answer(key: str, rules: RuleSet) -> int | str:
    v, f = rules.values(), rules.faq_values()
    return {
        "fixed_deductible": v.fixed_deductible_sar,
        "deductible_at_25": round_half_up(Fraction(v.fixed_deductible_sar * 25, 100)),
        "etl_pct": v.etl_pct,
        "reporting_window_days": v.reporting_window_days,
        "tp_licence_grace_days": v.tp_licence_grace_days,
        "od_licence_grace_business_days": v.od_licence_grace_business_days,
        "tpl_cap_sar": v.tpl_cap_sar,
        "deductible_when_not_liable": f["deductible_when_not_liable_sar"],
        "deduction_for_prior_use": f["deduction_for_prior_use"],
        "towing_city_sar": f["towing_city_sar"],
        "towing_outside_city_sar": f["towing_outside_city_sar"],
        "small_claim_threshold_sar": f["small_claim_threshold_sar"],
        "small_claim_settle_working_days": f["small_claim_settle_working_days"],
        "other_claim_settle_days": f["other_claim_settle_days"],
        "missing_docs_notice_working_days": f["missing_docs_notice_working_days"],
        "total_loss_report_working_days": f["total_loss_report_working_days"],
        "replacement_car_in_base_policy": f["replacement_car_in_base_policy"],
        "tpl_covers_own_car": "no",
        "hit_and_run_deductible": 0,
        "deductible_on_total_loss": "yes",
        "required_documents_count": len(rules.required_documents),
        "police_report_accepted": "yes",
        "relative_driver_covered": "yes" if "relative" in rules.authorised_drivers else "no",
    }[key]


FAQ_KEYS = (
    "fixed_deductible",
    "deductible_at_25",
    "etl_pct",
    "reporting_window_days",
    "tp_licence_grace_days",
    "od_licence_grace_business_days",
    "tpl_cap_sar",
    "deductible_when_not_liable",
    "deduction_for_prior_use",
    "towing_city_sar",
    "towing_outside_city_sar",
    "small_claim_threshold_sar",
    "small_claim_settle_working_days",
    "other_claim_settle_days",
    "missing_docs_notice_working_days",
    "total_loss_report_working_days",
    "replacement_car_in_base_policy",
    "tpl_covers_own_car",
    "hit_and_run_deductible",
    "deductible_on_total_loss",
    "required_documents_count",
    "police_report_accepted",
    "relative_driver_covered",
)
FAQ_V2_SENSITIVE = ("fixed_deductible", "deductible_at_25", "etl_pct", "reporting_window_days")
INTENT_KEYS = {  # label -> bank keys
    "new_claim": ("new_claim",),
    "claim_status": ("claim_status",),
    "coverage_question": ("coverage_question",),
    "document_submission": ("document_submission",),
    "complaint": ("complaint",),
    "policy_change": ("policy_change",),
    "payment_issue": ("payment_issue",),
    "fault_dispute": ("fault_dispute",),
    "other": ("other", "other_injury", "other_fire"),
}
