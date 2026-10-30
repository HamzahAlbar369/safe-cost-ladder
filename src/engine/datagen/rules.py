"""Typed loader for data/rules/rules*.yaml (SPEC §4.1). Insurer FICTIONAL; rules sourced per item (D1.8)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from engine.llm.pricing import ROOT

RULES_DIR = ROOT / "data" / "rules"
RULES_V1 = RULES_DIR / "rules.yaml"
RULES_V2 = RULES_DIR / "rules_v2.yaml"

INSTRUMENTS = ("UP", "CMIR", "CSI")
INSURER_SPECIFIC = "insurer-specific (illustrative)"
_ART = r"(?:UP|CMIR|CSI) (?:Art\. \d+(?:\.\d+)*(?:, \d+(?:\.\d+)*)*|\(article TBC\))"
SOURCE_RE = re.compile(
    rf"^(?:{_ART}|interpretation of {_ART}|insurer-specific \(illustrative\)|reported, unverified)$"
)


def source_kind(source: str) -> str:
    """The D1.8 form a source string takes (for the sources table)."""
    if source.startswith("interpretation of"):
        return "interpretation"
    if source in (INSURER_SPECIFIC, "reported, unverified"):
        return source
    return "article TBC" if "(article TBC)" in source else "article"


class Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Sourced(Strict):
    source: str

    @model_validator(mode="after")
    def _source_form(self) -> Sourced:
        if not SOURCE_RE.match(self.source):
            raise ValueError(f"source {self.source!r} is not one of the D1.8 forms")
        return self


class Label(Sourced):
    en: str
    ar: str
    generated: bool = True  # False = listed for fidelity, never produced by the sampler


class Param(Sourced):
    value: Any
    note: str = ""


class Instrument(Strict):
    name: str
    issuer: str
    checked: str
    url: str = ""
    in_force: str = ""


class Fiction(Strict):
    insurer_en: str
    insurer_ar: str
    label_en: str
    label_ar: str


class Values(Strict):
    """Typed view of `params` values used by the rules engine."""

    currency: Literal["SAR"]
    rounding: Literal["half_up_whole_sar"]
    fault_shares: tuple[int, ...]
    tp_payout_proportional_to_fault: bool
    tpl_cap_sar: int
    tp_licence_grace_days: int
    od_licence_grace_business_days: int
    business_days: tuple[Literal["sun", "mon", "tue", "wed", "thu", "fri", "sat"], ...]
    fixed_deductible_sar: int
    etl_pct: int
    reporting_window_days: int


class Exclusions(Strict):
    third_party_deny: dict[str, Label]
    third_party_recovery: dict[str, Label]
    own_damage_deny: dict[str, Label]


class Justifications(Strict):
    accepted: dict[str, Label]
    not_accepted: dict[str, Label]


class Decision(Sourced):
    text: str


class Step(Sourced):
    step: str
    applies: str
    decision: Literal["deny", "need_info", "from_payout"]
    reason: str


class Clause(Sourced):
    en: str
    ar: str
    items: str | None = None  # dotted path to an enumeration rendered as a list


class Section(Strict):
    id: str
    title: dict[Literal["en", "ar"], str]
    clauses: tuple[Clause, ...]


class Document(Strict):
    title_en: str
    title_ar: str
    sections: tuple[Section, ...]


class RuleSet(Strict):
    version: str
    instruments: dict[Literal["UP", "CMIR", "CSI"], Instrument]
    fiction: Fiction
    params: dict[str, Param]
    faq_only: dict[str, Param]
    cover_types: dict[Literal["TPL", "COMP"], Label]
    claim_types: dict[Literal["own_damage", "third_party_claim"], Label]
    other_party: dict[Literal["insured", "uninsured", "unknown", "none"], Label]
    report_sources: dict[Literal["najm", "traffic_police"], Label]
    out_of_scope_perils: dict[str, Label]
    licence_status: dict[Literal["valid", "none", "expired", "wrong_class", "forfeited"], Label]
    authorised_drivers: dict[str, Label]
    exclusions: Exclusions
    late_report_justifications: Justifications
    required_documents: dict[str, Label]
    decisions: dict[Literal["approve", "partial", "deny", "need_info"], Decision]
    precedence: tuple[Step, ...]
    reason_codes: dict[str, str]
    intents_source: str
    intents: dict[str, str]
    adversarial: dict[str, dict[str, Any]]
    formats: dict[str, Any]
    document: Document

    @model_validator(mode="after")
    def _consistent(self) -> RuleSet:
        v = self.values()  # validates every engine parameter's type
        if v.fault_shares != (0, 25, 50, 75, 100):
            raise ValueError("fault_shares must be 0/25/50/75/100 (SPEC §4.1 R2)")
        if not 0 < v.etl_pct <= 100:
            raise ValueError("etl_pct must be in (0, 100]")
        if len(self.intents) != 9:
            raise ValueError("SPEC §3.1 defines 9 intent labels")
        if not SOURCE_RE.match(self.intents_source) or not SOURCE_RE.match(self.formats.get("source", "")):
            raise ValueError("intents_source and formats.source must use a D1.8 source form")
        expected = (
            [f"R5_TP_{k}" for k in self.exclusions.third_party_deny]
            + [f"R5_OD_{k}" for k, lab in self.exclusions.own_damage_deny.items() if lab.generated]
            + [f"R7_MISSING_{k}" for k in self.required_documents]
        )
        missing = [c for c in expected if c not in self.reason_codes and c != "R5_OD_below_deductible"]
        if missing:
            raise ValueError(f"missing reason codes: {missing}")
        return self

    def values(self) -> Values:
        return Values.model_validate({k: p.value for k, p in self.params.items()})

    def faq_values(self) -> dict[str, Any]:
        return {k: p.value for k, p in self.faq_only.items()}

    def enumeration(self, dotted: str) -> dict[str, Label]:
        """Resolve a document `items:` path (e.g. `exclusions.third_party_deny`) to {key: Label}."""
        head, _, tail = dotted.partition(".")
        value = getattr(getattr(self, head), tail) if tail else getattr(self, head)
        if not isinstance(value, dict):
            raise ValueError(f"not an enumeration: {dotted}")
        return value


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _check_override_keys(name: str, base: dict[str, Any], over: dict[str, Any], path: str = "") -> None:
    for key, value in over.items():
        if key not in base:
            raise ValueError(f"{name}: override of unknown key {path + key!r}")
        if isinstance(value, dict) and isinstance(base[key], dict):
            _check_override_keys(name, base[key], value, f"{path}{key}.")


def load_raw(path: Path) -> dict[str, Any]:
    """A rules file, with `base:` + `overrides:` files merged onto their base (rules_v2.yaml)."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if "base" not in data:
        return data
    base = load_raw(path.parent / data["base"])
    over = data.get("overrides", {})
    _check_override_keys(path.name, base, over)
    merged = _deep_merge(base, over)
    merged["version"] = data["version"]
    return merged


def load_rules(path: Path = RULES_V1) -> RuleSet:
    return RuleSet.model_validate(load_raw(path))


def load_version(version: str) -> RuleSet:
    return load_rules({"v1": RULES_V1, "v2": RULES_V2}[version])
