"""Typed loader for data/rules/rules*.yaml (SPEC §4.1). FICTIONAL rules; single source of truth."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from engine.llm.pricing import ROOT

RULES_DIR = ROOT / "data" / "rules"
RULES_V1 = RULES_DIR / "rules.yaml"
RULES_V2 = RULES_DIR / "rules_v2.yaml"


class Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Label(Strict):
    en: str
    ar: str


class Fiction(Strict):
    insurer_en: str
    insurer_ar: str
    label_en: str
    label_ar: str


class Params(Strict):
    currency: Literal["SAR"]
    fault_shares: tuple[int, ...]
    deductible_floor_sar: int
    deductible_pct: int
    tpl_cap_sar: int
    reporting_window_days: int
    licence_renewal_grace_days: int
    rounding: Literal["half_up_whole_sar"]


class FaqOnly(Strict):
    replacement_car_days: int
    towing_limit_sar: int
    acknowledge_working_days: int
    decision_working_days: int
    settlement_working_days: int
    report_within_hours: int
    fault_objection_days: int


class Exclusions(Strict):
    absolute: tuple[str, ...]
    own_damage: tuple[str, ...]
    third_party_recovery: tuple[str, ...]


class Justifications(Strict):
    accepted: dict[str, Label]
    not_accepted: dict[str, Label]


class Clause(Strict):
    en: str
    ar: str
    items: str | None = None  # dotted path to an enumeration rendered as a list


class Section(Strict):
    id: str
    title: Label
    clauses: tuple[Clause, ...]


class Document(Strict):
    title_en: str
    title_ar: str
    sections: tuple[Section, ...]


class RuleSet(Strict):
    version: str
    fiction: Fiction
    params: Params
    faq_only: FaqOnly
    cover_types: dict[Literal["TPL", "COMP"], Label]
    claim_types: dict[Literal["own_damage", "third_party"], Label]
    other_party_status: dict[Literal["identified_insured", "identified_uninsured", "unknown"], Label]
    report_sources: dict[Literal["najm", "traffic_police"], Label]
    out_of_scope_perils: dict[str, Label]
    violations: dict[str, Label]
    exclusions: Exclusions
    late_report_justifications: Justifications
    required_documents: dict[Literal["report_number", "damage_estimate"], Label]
    decisions: dict[Literal["approve", "partial", "deny", "need_info"], str]
    precedence: tuple[dict[str, str], ...]
    reason_codes: dict[str, str]
    intents: dict[str, str]
    adversarial: dict[str, dict[str, Any]]
    formats: dict[str, Any]
    document: Document

    @model_validator(mode="after")
    def _consistent(self) -> RuleSet:
        p = self.params
        if p.fault_shares != (0, 25, 50, 75, 100):
            raise ValueError("fault_shares must be 0/25/50/75/100 (SPEC §4.1 R2)")
        for group in (
            self.exclusions.absolute,
            self.exclusions.own_damage,
            self.exclusions.third_party_recovery,
        ):
            unknown = set(group) - set(self.violations)
            if unknown:
                raise ValueError(f"exclusion without a violation label: {sorted(unknown)}")
        if len(self.intents) != 9:
            raise ValueError("SPEC §3.1 defines 9 intent labels")
        for code in [*self.exclusions.absolute]:
            if f"R5_{code}" not in self.reason_codes:
                raise ValueError(f"missing reason code R5_{code}")
        for code in self.exclusions.own_damage:
            if f"R5_od_{code}" not in self.reason_codes:
                raise ValueError(f"missing reason code R5_od_{code}")
        return self

    def enumeration(self, dotted: str) -> dict[str, Label]:
        """Resolve a document `items:` path (e.g. `exclusions.absolute`) to {key: Label}."""
        if dotted.startswith("exclusions."):
            keys = getattr(self.exclusions, dotted.split(".", 1)[1])
            return {k: self.violations[k] for k in keys}
        if dotted.startswith("late_report_justifications."):
            return getattr(self.late_report_justifications, dotted.split(".", 1)[1])
        value = getattr(self, dotted)
        if not isinstance(value, dict):
            raise ValueError(f"not an enumeration: {dotted}")
        return value


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _read(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_raw(path: Path) -> dict[str, Any]:
    """A rules file, with `base:` + `overrides:` files merged onto their base (rules_v2.yaml)."""
    data = _read(path)
    if "base" not in data:
        return data
    base = load_raw(path.parent / data["base"])
    over = data.get("overrides", {})
    for key in over:
        if key not in base:
            raise ValueError(f"{path.name}: override of unknown section {key!r}")
        if isinstance(over[key], dict):
            unknown = set(over[key]) - set(base[key])
            if unknown:
                raise ValueError(f"{path.name}: override of unknown key(s) {sorted(unknown)} in {key}")
    merged = _deep_merge(base, over)
    merged["version"] = data["version"]
    return merged


def load_rules(path: Path = RULES_V1) -> RuleSet:
    return RuleSet.model_validate(load_raw(path))


def load_version(version: str) -> RuleSet:
    return load_rules({"v1": RULES_V1, "v2": RULES_V2}[version])
