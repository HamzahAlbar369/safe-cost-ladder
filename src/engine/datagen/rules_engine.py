"""Adjudication gold: a pure function of (Case, RuleSet) with a rule-by-rule trace (SPEC §4.1, D1.8).

The order of checks is the YAML `precedence` list; every threshold comes from the RuleSet. FICTIONAL insurer.
Combinations the sampler never generates (e.g. CMIR 7.14 on an own-damage claim) raise instead of guessing.
"""

from __future__ import annotations

from datetime import date, timedelta
from fractions import Fraction

from engine.contracts import AdjudicateGold, Adjudication, Case, TraceStep
from engine.datagen.rules import RuleSet

_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
TP_RECOVERY_VIOLATIONS = ("wrong_direction", "red_light", "use_outside_purpose")  # + invalid licence
OD_7_16_VIOLATIONS = ("red_light", "wrong_direction", "racing_or_drifting")
OD_NOT_GENERATED = ("fled_scene", "intoxication", "deliberate", "misrepresentation", "use_outside_purpose")


class UnsupportedCase(ValueError):
    """A fact combination outside what the rules file (and sampler) define."""


def round_half_up(x: Fraction) -> int:
    return int((x + Fraction(1, 2)).__floor__())


def business_days_after(start: date, end: date, working: tuple[str, ...]) -> int:
    """Working days in (start, end]; public holidays ignored (D1.8, interpretation of CMIR 7.2)."""
    days, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if _WEEKDAYS[d.weekday()] in working:
            days += 1
    return days


def business_day_deadline(start: date, n: int, working: tuple[str, ...]) -> date:
    """Calendar date of business day n after `start` (day 0). A renewal on any calendar date on or before it,
    weekend days included, is within grace (D1.11)."""
    d, counted = start, 0
    while counted < n:
        d += timedelta(days=1)
        if _WEEKDAYS[d.weekday()] in working:
            counted += 1
    return d


def licence_valid_tp(case: Case, rules: RuleSet) -> bool:
    """UP Art. 5: an expired licence renewed within N calendar days after the accident counts as valid."""
    if case.licence_status == "valid":
        return True
    if case.licence_status != "expired":
        return False
    if case.licence_renewal_date is None:
        return False
    gap = (case.licence_renewal_date - case.accident_date).days
    if gap < 0:
        raise UnsupportedCase("licence renewed before the accident is not 'expired'")
    return gap <= rules.values().tp_licence_grace_days


def licence_valid_od(case: Case, rules: RuleSet) -> bool:
    """CMIR 7.2: only an expired licence gets the grace (N business days); wrong class/forfeited never."""
    v = rules.values()
    if case.licence_status == "valid":
        return True
    if case.licence_status != "expired" or case.licence_renewal_date is None:
        return False
    if case.licence_renewal_date < case.accident_date:
        raise UnsupportedCase("licence renewed before the accident is not 'expired'")
    deadline = business_day_deadline(case.accident_date, v.od_licence_grace_business_days, v.business_days)
    return case.licence_renewal_date <= deadline


class _Trace:
    def __init__(self) -> None:
        self.steps: list[TraceStep] = []

    def add(self, rule: str, check: str, fired: bool, detail: str = "") -> bool:
        self.steps.append(TraceStep(rule=rule, check=check, fired=fired, detail=detail))
        return fired


def adjudicate(case: Case, rules: RuleSet) -> Adjudication:
    v = rules.values()
    t = _Trace()
    od = case.claim_type == "own_damage"
    base_inputs = {
        "claim_type": case.claim_type,
        "cover": case.cover,
        "accident_date": case.accident_date.isoformat(),
        "other_party": case.other_party,
        "fault_share": case.fault_share,
        "damage_amount_sar": case.damage_amount_sar,
    }

    def stop(decision: str, reasons: list[str], **extra) -> Adjudication:
        gold = AdjudicateGold(
            decision=decision, payout_sar=0, reasons=tuple(reasons), inputs={**base_inputs, **extra}
        )
        return Adjudication(gold=gold, trace=tuple(t.steps))

    # R0 desk scope
    if t.add("R0", "peril in scope (collision)", case.peril != "collision", f"peril={case.peril}"):
        return stop("deny", ["R0_OUT_OF_SCOPE"])
    # R1 policy in force
    expired = case.accident_date > case.policy_end_date
    detail = f"accident {case.accident_date} vs policy end {case.policy_end_date}"
    if t.add("R1", "accident after policy end date", expired, detail):
        return stop("deny", ["R1_POLICY_NOT_IN_FORCE"])
    # R5 third-party denials (UP Art. 6)
    if not od:
        hits = [k for k in rules.exclusions.third_party_deny if k in case.violations]
        if t.add("R5", "third-party exclusion (UP Art. 6)", bool(hits), ", ".join(hits) or "none"):
            return stop("deny", [f"R5_TP_{k}" for k in hits])
    # R8 / R1: own damage under TPL (UP Art. 6.1)
    if od and case.cover == "TPL":
        if case.other_party in ("unknown", "uninsured"):
            t.add("R8", "own damage under TPL, other party unknown/uninsured", True, case.other_party)
            return stop("deny", ["R8_NO_OWN_COVER"])
        t.add("R1", "own damage under TPL", True)
        return stop("deny", ["R1_TPL_NO_OWN_DAMAGE"])
    # R5 own-damage exclusions (CMIR Art. 7; generated subset)
    if od:
        unsupported = [k for k in case.violations if k in OD_NOT_GENERATED]
        if unsupported:
            raise UnsupportedCase(f"own-damage violation(s) not generated by design: {unsupported}")
        hits = []
        lic_ok = licence_valid_od(case, rules)
        if not lic_ok:
            hits.append("invalid_licence")
        detail = f"status={case.licence_status}, renewed={case.licence_renewal_date}"
        if case.licence_status == "expired":
            n = v.od_licence_grace_business_days
            detail += f", deadline={business_day_deadline(case.accident_date, n, v.business_days)}"
        t.add(
            "R5",
            "CMIR 7.2 licence valid (expired only: renewed on or before the business-day-50 date)",
            not lic_ok,
            detail,
        )
        authorised = case.driver in rules.authorised_drivers
        if not authorised:
            hits.append("unauthorised_driver")
        t.add("R5", "CMIR 7.4 driver authorised (CMIR 1.8)", not authorised, f"driver={case.driver}")
        caused = case.violation_caused_accident and any(k in OD_7_16_VIOLATIONS for k in case.violations)
        if caused:
            hits.append("traffic_violation_cause")
        t.add(
            "R5",
            "CMIR 7.16 violation proven to cause the accident",
            caused,
            f"violations={list(case.violations)}, caused={case.violation_caused_accident}",
        )
        if hits:
            return stop("deny", [f"R5_OD_{k}" for k in hits])
    # R6 reporting window
    days = (case.report_date - case.accident_date).days
    late = days > v.reporting_window_days
    justified = late and case.late_justification in rules.late_report_justifications.accepted
    reasons_info: list[str] = []
    detail = f"{days} days vs {v.reporting_window_days}; justification={case.late_justification}"
    if t.add("R6", "reported late without an accepted reason", late and not justified, detail):
        return stop("deny", ["R6_LATE_REPORT"])
    if justified:
        reasons_info.append("R6_JUSTIFIED")
    # R3 / CMIR 7.3 before R7 when the assessment is present and unambiguous (D1.8)
    if od and "damage_assessment" in case.documents and case.conflict_damage_sar is None:
        if case.damage_amount_sar is None:
            raise UnsupportedCase("damage assessment provided without a damage amount")
        below = case.damage_amount_sar <= v.fixed_deductible_sar
        detail = f"repair {case.damage_amount_sar} vs full deductible {v.fixed_deductible_sar}"
        if t.add("R3", "CMIR 7.3 loss at or below the full deductible", below, detail):
            return stop("deny", ["R3_BELOW_DEDUCTIBLE"])
    if case.damage_source == "garage_quote" and "damage_assessment" in case.documents:
        raise UnsupportedCase("a garage-quote amount cannot come with a damage assessment report")
    # R7 required documents, then contradictions (a garage quote never replaces the assessment)
    missing = [k for k in rules.required_documents if k not in case.documents]
    if t.add("R7", "all required documents present", bool(missing), f"missing={missing}"):
        return stop("need_info", [f"R7_MISSING_{k}" for k in missing])
    if "accident_report" in case.documents and case.report_number is None:
        raise UnsupportedCase("accident report provided without a report number")
    conflict = case.conflict_damage_sar is not None
    detail = f"{case.damage_amount_sar} vs {case.conflict_damage_sar}" if conflict else ""
    if t.add("R7", "two stated damage amounts contradict", conflict, detail):
        return stop("need_info", ["R7_CONFLICT"])
    if case.damage_amount_sar is None:
        raise UnsupportedCase("documents complete but no damage amount")
    payout = _own_damage(case, rules, t) if od else _third_party(case, rules, t)
    decision, amount, reasons, extra = payout
    gold = AdjudicateGold(
        decision=decision,
        payout_sar=amount,
        reasons=tuple(reasons + reasons_info),
        inputs={**base_inputs, **extra},
    )
    return Adjudication(gold=gold, trace=tuple(t.steps))


def _own_damage(case: Case, rules: RuleSet, t: _Trace) -> tuple[str, int, list[str], dict]:
    v = rules.values()
    repair, si = case.damage_amount_sar, case.sum_insured_sar
    if si is None or repair is None:
        raise UnsupportedCase("own damage under COMP needs sum insured and repair estimate")
    reasons = ["R3_OWN_DAMAGE"]
    etl = Fraction(v.etl_pct, 100) * si
    total_loss = case.technical_total_loss or repair > etl
    base = si if total_loss else min(repair, si)
    t.add(
        "R3",
        "total loss (technical, or repair > ETL% x sum insured)",
        total_loss,
        f"repair {repair} vs {v.etl_pct}% x {si} = {float(etl):g}; technical={case.technical_total_loss}",
    )
    if total_loss:
        reasons.append("R3_TOTAL_LOSS")
    if base < repair:
        reasons.append("R3_SUM_INSURED_CAP")
    fixed = v.fixed_deductible_sar
    if case.other_party == "unknown":
        ded, why = Fraction(0), "hit-and-run: no deductible (CMIR 5.4.4)"
        reasons.append("R8_UNKNOWN_PARTY")
    elif case.other_party == "none":
        ded, why = Fraction(fixed), "no other party: full deductible (CMIR 5.4.5, interpretation)"
    else:
        if case.fault_share is None:
            raise UnsupportedCase("identified other party needs a fault share")
        ded = Fraction(fixed * case.fault_share, 100)
        why = f"{fixed} x {case.fault_share}% (CMIR 5.4.3/5.4.4)"
        if case.other_party == "insured" and case.fault_share < 100:
            reasons.append("SUBROGATION")
    applied = round_half_up(ded)
    payout = base - applied
    t.add("R3", "deductible applied", applied > 0, f"{why} = {applied}")
    t.add("R3", "payout = base - deductible", True, f"{base} - {applied} = {payout}")
    extra = {
        "sum_insured_sar": si,
        "base_sar": base,
        "deductible_applied_sar": applied,
        "total_loss": total_loss,
    }
    if payout <= 0:
        return "deny", 0, ["R3_BELOW_DEDUCTIBLE"], extra
    decision = "approve" if base >= repair else "partial"
    return decision, payout, reasons, extra


def _third_party(case: Case, rules: RuleSet, t: _Trace) -> tuple[str, int, list[str], dict]:
    v = rules.values()
    if case.fault_share is None:
        raise UnsupportedCase("third-party claim needs a fault share")
    damage, fault = case.damage_amount_sar, case.fault_share
    assert damage is not None
    recovery = [k for k in TP_RECOVERY_VIOLATIONS if k in case.violations]
    if not licence_valid_tp(case, rules):
        recovery.insert(0, "invalid_licence")
    t.add(
        "R5",
        "UP Art. 5 recovery case (paid; recovery right kept, Art. 9(7))",
        bool(recovery),
        f"{recovery or 'none'}; licence={case.licence_status}, renewed={case.licence_renewal_date}",
    )
    if t.add("R4", "policyholder 0% at fault", fault == 0, f"fault={fault}%"):
        return "deny", 0, ["R4_NO_FAULT"], {}
    raw = round_half_up(Fraction(damage * fault, 100))
    payout = min(raw, v.tpl_cap_sar)
    capped = raw > v.tpl_cap_sar
    t.add(
        "R4",
        "payout = damage x fault share, capped",
        capped,
        f"{damage} x {fault}% = {raw}; cap {v.tpl_cap_sar}",
    )
    reasons = ["R4_THIRD_PARTY"] + (["R4_CAP"] if capped else []) + (["RECOVERY_RIGHT"] if recovery else [])
    decision = "approve" if fault == 100 and not capped else "partial"
    return decision, payout, reasons, {"recovery_cases": recovery}
