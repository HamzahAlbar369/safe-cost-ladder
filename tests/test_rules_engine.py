"""Rules engine: every rule + interactions, hand-computed fixtures (SPEC §4.4, §11.3; D1.8). FICTIONAL."""

from __future__ import annotations

from datetime import date, timedelta
from fractions import Fraction

import pytest

from engine.contracts import Case
from engine.datagen.rules import load_version
from engine.datagen.rules_engine import (
    UnsupportedCase,
    adjudicate,
    business_day_deadline,
    business_days_after,
    round_half_up,
)

V1, V2 = load_version("v1"), load_version("v2")
ACC = date(2026, 3, 10)  # a Tuesday
ALL_DOCS = ("accident_report", "registration", "licence_copy", "damage_photos", "damage_assessment")


def mk(**kw) -> Case:
    """Default: own damage under COMP, insured other party, 50% fault, repair 20,000, sum insured 80,000."""
    base = dict(
        claim_type="own_damage",
        cover="COMP",
        policy_number="OMI-1234567",
        policy_end_date=date(2026, 12, 31),
        accident_date=ACC,
        report_date=ACC + timedelta(days=5),
        report_source="najm",
        report_number="NJ-12345678",
        other_party="insured",
        fault_share=50,
        damage_amount_sar=20_000,
        sum_insured_sar=80_000,
        documents=ALL_DOCS,
    )
    base.update(kw)
    return Case(**base)


def tp(**kw) -> Case:
    kw.setdefault("claim_type", "third_party_claim")
    kw.setdefault("sum_insured_sar", None)
    return mk(**kw)


def run(case: Case, rules=V1):
    a = adjudicate(case, rules)
    return a.gold.decision, a.gold.payout_sar, a.gold.reasons


# --- helpers -------------------------------------------------------------------------------------------


def test_round_half_up():
    assert round_half_up(Fraction(5, 2)) == 3
    assert round_half_up(Fraction(749, 2)) == 375
    assert round_half_up(Fraction(1, 3)) == 0


def test_business_days_are_sunday_to_thursday():
    wk = ("sun", "mon", "tue", "wed", "thu")
    assert business_days_after(ACC, ACC + timedelta(days=70), wk) == 50  # ten full weeks
    assert business_days_after(ACC, date(2026, 3, 14), wk) == 2  # Wed, Thu (Fri/Sat off)
    assert business_days_after(ACC, ACC, wk) == 0


# --- R0, R1 --------------------------------------------------------------------------------------------


def test_r0_out_of_scope_peril_denied():
    assert run(mk(peril="theft")) == ("deny", 0, ("R0_OUT_OF_SCOPE",))


def test_r1_policy_not_in_force_and_end_date_is_inclusive():
    assert run(mk(policy_end_date=ACC - timedelta(days=1)))[0:2] == ("deny", 0)
    assert run(mk(policy_end_date=ACC - timedelta(days=1)))[2] == ("R1_POLICY_NOT_IN_FORCE",)
    assert run(mk(policy_end_date=ACC))[0] == "approve"


def test_r1_own_damage_under_tpl_denied():
    assert run(mk(cover="TPL")) == ("deny", 0, ("R1_TPL_NO_OWN_DAMAGE",))


# --- R2 / R3 own damage (CMIR 5.3, 5.4, 7.3) -----------------------------------------------------------


def test_r3_partial_repair_fault_scaled_deductible_and_subrogation():
    # base 20,000 (below 60% x 80,000 = 48,000); deductible 1,000 x 50% = 500
    assert run(mk()) == ("approve", 19_500, ("R3_OWN_DAMAGE", "SUBROGATION"))


@pytest.mark.parametrize(("fault", "deductible"), [(0, 0), (25, 250), (50, 500), (75, 750), (100, 1_000)])
def test_r3_deductible_proportional_to_fault(fault, deductible):
    decision, payout, _ = run(mk(fault_share=fault))
    assert (decision, payout) == ("approve", 20_000 - deductible)


def test_r3_no_subrogation_at_full_fault_or_uninsured_party():
    assert "SUBROGATION" not in run(mk(fault_share=100))[2]
    assert run(mk(other_party="uninsured", fault_share=75)) == ("approve", 19_250, ("R3_OWN_DAMAGE",))


def test_r3_economic_total_loss_pays_sum_insured_less_deductible():
    # repair 35,000 > 60% x 50,000 = 30,000 -> base 50,000 (>= repair, so approve)
    assert run(mk(sum_insured_sar=50_000, damage_amount_sar=35_000)) == (
        "approve",
        49_500,
        ("R3_OWN_DAMAGE", "R3_TOTAL_LOSS", "SUBROGATION"),
    )


def test_r3_etl_boundary_is_strictly_above():
    # repair exactly 60% of sum insured -> not a total loss
    assert run(mk(sum_insured_sar=50_000, damage_amount_sar=30_000))[1] == 29_500


def test_r3_repair_above_sum_insured_is_partial():
    assert run(mk(sum_insured_sar=50_000, damage_amount_sar=60_000)) == (
        "partial",
        49_500,
        ("R3_OWN_DAMAGE", "R3_TOTAL_LOSS", "R3_SUM_INSURED_CAP", "SUBROGATION"),
    )


def test_r3_technical_total_loss_flag():
    assert run(mk(technical_total_loss=True, damage_amount_sar=10_000))[1] == 80_000 - 500


def test_r3_no_other_party_full_deductible_even_without_fault_share():
    assert run(mk(other_party="none", fault_share=None)) == ("approve", 19_000, ("R3_OWN_DAMAGE",))


def test_r3_deductible_applies_to_total_loss_with_no_other_party():
    assert run(mk(other_party="none", fault_share=None, technical_total_loss=True))[1] == 79_000


def test_cmir_7_3_loss_at_or_below_full_deductible_denied_whatever_the_fault():
    assert run(mk(damage_amount_sar=1_000)) == ("deny", 0, ("R3_BELOW_DEDUCTIBLE",))
    assert run(mk(damage_amount_sar=1_000, fault_share=0))[0] == "deny"  # literal reading (D1.8)
    assert run(mk(damage_amount_sar=1_100, fault_share=0))[0:2] == ("approve", 1_100)


# --- R8 other party ------------------------------------------------------------------------------------


def test_r8_hit_and_run_under_comp_no_deductible_no_subrogation():
    assert run(mk(other_party="unknown", fault_share=None)) == (
        "approve",
        20_000,
        ("R3_OWN_DAMAGE", "R8_UNKNOWN_PARTY"),
    )


@pytest.mark.parametrize("party", ["unknown", "uninsured"])
def test_r8_tpl_with_unknown_or_uninsured_party_denied(party):
    assert run(mk(cover="TPL", other_party=party, fault_share=None)) == ("deny", 0, ("R8_NO_OWN_COVER",))


def test_r8_police_report_accepted_like_najm():
    assert run(mk(report_source="traffic_police", report_number="TP-87654321"))[0] == "approve"


# --- R4 third party (UP Art. 3, 4) ---------------------------------------------------------------------


def test_r4_full_fault_is_approve():
    assert run(tp(damage_amount_sar=30_000, fault_share=100)) == ("approve", 30_000, ("R4_THIRD_PARTY",))


@pytest.mark.parametrize(("fault", "payout"), [(25, 7_500), (50, 15_000), (75, 22_500)])
def test_r4_proportional_to_fault_is_partial(fault, payout):
    assert run(tp(damage_amount_sar=30_000, fault_share=fault)) == ("partial", payout, ("R4_THIRD_PARTY",))


def test_r4_zero_fault_denied():
    assert run(tp(fault_share=0)) == ("deny", 0, ("R4_NO_FAULT",))


def test_r4_cap_binds_per_event():
    assert run(tp(damage_amount_sar=30_000_000, fault_share=50)) == (
        "partial",
        10_000_000,
        ("R4_THIRD_PARTY", "R4_CAP"),
    )


def test_r4_same_rule_under_tpl_and_comp():
    assert run(tp(cover="TPL", fault_share=75)) == run(tp(cover="COMP", fault_share=75))


# --- R5 exclusions and recovery ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "v", ["fled_scene", "intoxication", "racing_or_drifting", "deliberate", "misrepresentation"]
)
def test_r5_up_art6_denies_third_party(v):
    assert run(tp(violations=(v,))) == ("deny", 0, (f"R5_TP_{v}",))


@pytest.mark.parametrize("v", ["wrong_direction", "red_light", "use_outside_purpose"])
def test_r5_up_art5_pays_third_party_with_recovery_right(v):
    assert run(tp(violations=(v,), fault_share=100)) == (
        "approve",
        20_000,
        ("R4_THIRD_PARTY", "RECOVERY_RIGHT"),
    )


@pytest.mark.parametrize("status", ["none", "wrong_class", "forfeited"])
def test_r5_invalid_licence_third_party_recovery_but_own_damage_denied(status):
    assert run(tp(licence_status=status, fault_share=50))[2] == ("R4_THIRD_PARTY", "RECOVERY_RIGHT")
    assert run(mk(licence_status=status)) == ("deny", 0, ("R5_OD_invalid_licence",))


def test_r5_licence_grace_tp_calendar_vs_od_business_days():
    # renewed 51 calendar days after the accident = 37 business days
    late51 = dict(licence_status="expired", licence_renewal_date=ACC + timedelta(days=51))
    assert "RECOVERY_RIGHT" in run(tp(**late51))[2]  # UP: > 50 calendar days
    assert run(mk(**late51))[0] == "approve"  # CMIR: within 50 business days
    on50 = dict(licence_status="expired", licence_renewal_date=ACC + timedelta(days=50))
    assert "RECOVERY_RIGHT" not in run(tp(**on50))[2]


def test_r5_od_business_day_grace_boundary():
    ok = dict(licence_status="expired", licence_renewal_date=ACC + timedelta(days=70))  # exactly 50
    late = dict(licence_status="expired", licence_renewal_date=ACC + timedelta(days=71))  # 51
    assert run(mk(**ok))[0] == "approve"
    assert run(mk(**late)) == ("deny", 0, ("R5_OD_invalid_licence",))
    assert run(mk(licence_status="expired"))[0] == "deny"  # never renewed


@pytest.mark.parametrize("who", ["named_driver", "relative", "domestic_worker", "sponsored_driver"])
def test_r5_cmir_1_8_authorised_drivers(who):
    assert run(mk(driver=who))[0] == "approve"


def test_r5_cmir_7_4_unauthorised_driver_denied_own_damage_only():
    assert run(mk(driver="unauthorised_friend")) == ("deny", 0, ("R5_OD_unauthorised_driver",))
    assert run(tp(driver="unauthorised_friend"))[0] == "partial"


@pytest.mark.parametrize("v", ["red_light", "wrong_direction", "racing_or_drifting"])
def test_r5_cmir_7_16_only_when_proven_cause(v):
    assert run(mk(violations=(v,), violation_caused_accident=True)) == (
        "deny",
        0,
        ("R5_OD_traffic_violation_cause",),
    )
    assert run(mk(violations=(v,), violation_caused_accident=False))[0] == "approve"


def test_red_light_contrast_third_party_pays_own_damage_denied():
    assert run(tp(violations=("red_light",), violation_caused_accident=True))[0] == "partial"
    assert run(mk(violations=("red_light",), violation_caused_accident=True))[0] == "deny"


def test_multiple_own_damage_exclusions_all_reported():
    case = mk(licence_status="none", driver="unauthorised_friend")
    assert run(case)[2] == ("R5_OD_invalid_licence", "R5_OD_unauthorised_driver")


def test_own_damage_violation_outside_generated_set_raises():
    with pytest.raises(UnsupportedCase):
        adjudicate(mk(violations=("intoxication",)), V1)


# --- R6 reporting window -------------------------------------------------------------------------------


def test_r6_day_15_on_time_day_16_late():
    assert run(mk(report_date=ACC + timedelta(days=15)))[0] == "approve"
    assert run(mk(report_date=ACC + timedelta(days=16))) == ("deny", 0, ("R6_LATE_REPORT",))


@pytest.mark.parametrize("why", ["hospitalisation", "travel_outside_kingdom", "official_report_delay"])
def test_r6_accepted_justification_pays(why):
    decision, payout, reasons = run(mk(report_date=ACC + timedelta(days=30), late_justification=why))
    assert (decision, payout) == ("approve", 19_500) and reasons[-1] == "R6_JUSTIFIED"


@pytest.mark.parametrize("why", ["busy", "forgot", "unaware_of_deadline"])
def test_r6_rejected_justification_denies(why):
    assert run(mk(report_date=ACC + timedelta(days=30), late_justification=why))[0] == "deny"


# --- R7 documents and contradictions; precedence -------------------------------------------------------


@pytest.mark.parametrize("doc", ALL_DOCS)
def test_r7_any_missing_document_is_need_info(doc):
    docs = tuple(d for d in ALL_DOCS if d != doc)
    assert run(mk(documents=docs)) == ("need_info", 0, (f"R7_MISSING_{doc}",))


def test_r7_contradicting_amounts_need_info():
    assert run(mk(conflict_damage_sar=26_000)) == ("need_info", 0, ("R7_CONFLICT",))


def test_deny_beats_need_info_exclusion_with_missing_document():
    assert run(tp(violations=("intoxication",), documents=ALL_DOCS[:2]))[0] == "deny"
    assert run(mk(licence_status="none", documents=()))[0] == "deny"
    assert run(mk(report_date=ACC + timedelta(days=40), documents=()))[0] == "deny"


def test_cmir_7_3_beats_r7_when_assessment_present():
    docs = ("damage_assessment", "registration")
    assert run(mk(damage_amount_sar=800, documents=docs)) == ("deny", 0, ("R3_BELOW_DEDUCTIBLE",))


def test_missing_assessment_is_need_info_even_for_a_small_loss():
    docs = tuple(d for d in ALL_DOCS if d != "damage_assessment")
    assert run(mk(damage_amount_sar=800, documents=docs))[0] == "need_info"


def test_contradicting_amounts_do_not_trigger_7_3():
    assert run(mk(damage_amount_sar=900, conflict_damage_sar=4_000))[0] == "need_info"


# --- rules v2 (insurer-specific values only) -----------------------------------------------------------


def test_v2_fixed_deductible_etl_and_window():
    assert run(mk(fault_share=25), V2)[1] == 20_000 - 375  # 1,500 x 25%
    assert run(mk(damage_amount_sar=1_400), V2)[0] == "deny"  # 7.3 with 1,500
    assert run(mk(damage_amount_sar=1_400), V1)[0] == "approve"
    assert run(mk(report_date=ACC + timedelta(days=12)), V2)[0] == "deny"
    assert run(mk(report_date=ACC + timedelta(days=12)), V1)[0] == "approve"
    tl = mk(sum_insured_sar=50_000, damage_amount_sar=27_000)  # 54%: total loss in v2 only
    assert run(tl, V2)[1] == 50_000 - 750 and run(tl, V1)[1] == 27_000 - 500


# --- trace ---------------------------------------------------------------------------------------------


def test_trace_rules_are_precedence_steps_and_the_deciding_step_fired():
    steps = {s.step for s in V1.precedence}
    for case in (mk(), tp(), mk(cover="TPL"), mk(documents=()), tp(violations=("fled_scene",))):
        a = adjudicate(case, V1)
        assert {s.rule for s in a.trace} <= steps
        assert a.trace[-1].fired or a.gold.decision in ("approve", "partial")


def test_engine_is_deterministic():
    assert adjudicate(mk(), V1) == adjudicate(mk(), V1)


# --- D1.10: labels, day-0 boundaries, Saudi week, garage quote --------------------------------------------


def test_d110_explicit_labels():
    # deductible scaled by fault only -> approve
    assert run(mk(fault_share=50))[0] == "approve"
    # repair above the sum insured (cap binds) -> partial
    assert run(mk(sum_insured_sar=50_000, damage_amount_sar=60_000))[0] == "partial"
    # ETL total loss paying the sum insured (repair not above it) -> approve
    assert run(mk(sum_insured_sar=50_000, damage_amount_sar=40_000))[0:2] == ("approve", 49_500)
    # third-party claim at fault < 100% -> partial; at 100% -> approve
    for fault in (25, 50, 75):
        assert run(tp(fault_share=fault))[0] == "partial"
    assert run(tp(fault_share=100))[0] == "approve"


def test_d110_licence_grace_day_zero_calendar_and_business():
    # accident day is day 0: renewal on day 50 is within grace, day 51 is not
    assert (
        "RECOVERY_RIGHT"
        not in run(tp(licence_status="expired", licence_renewal_date=ACC + timedelta(days=50)))[2]
    )
    assert (
        "RECOVERY_RIGHT"
        in run(tp(licence_status="expired", licence_renewal_date=ACC + timedelta(days=51)))[2]
    )
    assert business_days_after(ACC, ACC, ("sun", "mon", "tue", "wed", "thu")) == 0  # renewal on day 0


SAUDI = ("sun", "mon", "tue", "wed", "thu")
MON_FRI = ("mon", "tue", "wed", "thu", "fri")


def test_business_days_saudi_week_vs_mon_fri():
    thu = date(2026, 3, 12)  # Thursday
    assert business_days_after(thu, thu + timedelta(days=1), SAUDI) == 0  # Friday is weekend
    assert business_days_after(thu, thu + timedelta(days=2), SAUDI) == 0  # Saturday is weekend
    assert business_days_after(thu, thu + timedelta(days=3), SAUDI) == 1  # Sunday is a working day
    assert business_days_after(thu, thu + timedelta(days=1), MON_FRI) == 1  # Friday counts on Mon-Fri
    assert business_days_after(thu, thu + timedelta(days=3), MON_FRI) == 1  # Sunday does not


def _mon_fri_rules():
    from engine.datagen.rules import RULES_V1, RuleSet, load_raw

    raw = load_raw(RULES_V1)
    raw["params"]["business_days"]["value"] = list(MON_FRI)
    return RuleSet.model_validate(raw)


def test_engine_uses_the_saudi_week_from_rules_yaml_not_mon_fri():
    assert V1.values().business_days == SAUDI
    fri = date(2026, 3, 13)  # accident on a Friday
    # business day 50: Saudi week -> Thursday fri+69; Mon-Fri -> Friday fri+70
    assert business_day_deadline(fri, 50, SAUDI) == fri + timedelta(days=69)
    assert business_day_deadline(fri, 50, MON_FRI) == fri + timedelta(days=70)
    case = mk(
        accident_date=fri,
        report_date=fri + timedelta(days=3),
        licence_status="expired",
        licence_renewal_date=fri + timedelta(days=70),
    )
    assert adjudicate(case, V1).gold.decision == "deny"  # Saudi deadline already passed
    assert adjudicate(case, _mon_fri_rules()).gold.decision == "approve"


def test_d111_comp_grace_is_a_calendar_date_deadline():
    thu = date(2026, 3, 12)  # accident on a Thursday; business day 50 (Saudi week) is Thursday thu+70
    deadline = business_day_deadline(thu, 50, SAUDI)
    assert deadline == thu + timedelta(days=70) and deadline.weekday() == 3

    def decide(renew):
        return run(
            mk(
                accident_date=thu,
                report_date=thu + timedelta(days=3),
                licence_status="expired",
                licence_renewal_date=renew,
            )
        )[0]

    assert decide(deadline) == "approve"  # on the deadline date
    assert decide(deadline - timedelta(days=5)) == "approve"  # a Saturday before it: weekend day, in grace
    assert (deadline - timedelta(days=5)).weekday() == 5
    assert decide(deadline + timedelta(days=1)) == "deny"  # the Friday after: weekend, but past the date
    assert decide(deadline + timedelta(days=2)) == "deny"  # the Saturday after
    assert decide(thu) == "approve"  # renewed on day 0


def test_garage_quote_only_is_need_info_even_when_small():
    docs = tuple(d for d in ALL_DOCS if d != "damage_assessment")
    for amount in (800, 20_000):
        case = mk(documents=docs, damage_source="garage_quote", damage_amount_sar=amount)
        assert run(case) == ("need_info", 0, ("R7_MISSING_damage_assessment",))


def test_garage_quote_with_an_assessment_is_rejected():
    with pytest.raises(UnsupportedCase):
        adjudicate(mk(damage_source="garage_quote"), V1)


def test_contradicting_assessments_are_need_info_not_7_3():
    assert run(mk(damage_amount_sar=700, conflict_damage_sar=900))[0] == "need_info"
