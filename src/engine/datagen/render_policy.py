"""Render the FICTIONAL policy document (EN + AR markdown) from a rules file (SPEC §4.1).

Output: data/rules/policy_<version>.<lang>.md. Deterministic; tests check the committed files match a fresh
render, so the document the models read can never drift from the rules that produce the gold labels.
"""

from __future__ import annotations

import string
from pathlib import Path
from typing import Any, Literal

from engine.datagen.rules import (
    CSI_SOURCE,
    INSURER_SPECIFIC,
    RULES_DIR,
    TOWING_SOURCE,
    RuleSet,
    load_version,
    source_kind,
)

Lang = Literal["en", "ar"]

# Arabic counted nouns: (1, 2, 3-10, 11-99, otherwise). Number agreement depends on the value, and v2 changes
# values, so the form is chosen at render time.
_AR_COUNTED: dict[str, tuple[str, str, str, str, str]] = {
    "ar_day": ("يوم واحد", "يومان", "{n} أيام", "{n} يومًا", "{n} يوم"),
    "ar_workday": ("يوم عمل واحد", "يوما عمل", "{n} أيام عمل", "{n} يوم عمل", "{n} يوم عمل"),
    "ar_hour": ("ساعة واحدة", "ساعتان", "{n} ساعات", "{n} ساعة", "{n} ساعة"),
}


def ar_count(n: int, noun: str) -> str:
    one, two, few, many, other = _AR_COUNTED[noun]
    if n == 1:
        return one
    if n == 2:
        return two
    if 3 <= n <= 10:
        return few.format(n=n)
    if 11 <= n <= 99:
        return many.format(n=n)
    return other.format(n=n)


class _PolicyFormatter(string.Formatter):
    def format_field(self, value: Any, format_spec: str) -> str:
        if format_spec in _AR_COUNTED:
            return ar_count(int(value), format_spec)
        return super().format_field(value, format_spec)


_FMT = _PolicyFormatter()
SOURCES_PATH = RULES_DIR / "SOURCES.md"


def _join(items: list[str], lang: Lang) -> str:
    if lang == "ar":
        return " أو ".join(items)
    return ", ".join(items[:-1]) + " or " + items[-1]


def placeholders(rules: RuleSet, lang: Lang) -> dict[str, Any]:
    values = {**rules.values().model_dump(), **rules.faq_values()}
    return {
        **values,
        "insurer_en": rules.fiction.insurer_en,
        "insurer_ar": rules.fiction.insurer_ar,
        "version": rules.version,
        "fault_shares_text": _join([str(s) for s in values["fault_shares"]], lang),
        "claim_statuses_text": ", ".join(values["claim_statuses"]),
        "reporting_window_days_plus_1": values["reporting_window_days"] + 1,
    }


_AR_CITE = (
    (CSI_SOURCE, "تعليمات تسوية مطالبات التأمين على المركبات، تعميم البنك المركزي السعودي 14 مايو 2023"),
    (TOWING_SOURCE, "جدول وثيقة التأمين الشامل، حد التغطية لكل مطالبة (يجوز للشركة الاتفاق على حد أعلى)"),
    (INSURER_SPECIFIC, "خاص بالشركة (توضيحي)"),
    ("reported, unverified", "منقول، غير متحقق منه"),
    ("interpretation of ", "تفسير "),
    ("(article TBC)", "(المادة لم تُحدَّد بعد)"),
    ("UP Art. ", "الوثيقة الموحدة، المادة "),
    ("UP ", "الوثيقة الموحدة "),
    ("CMIR Art. ", "قواعد التأمين الشامل، المادة "),
    ("CMIR ", "قواعد التأمين الشامل "),
)
LEGEND = {
    "en": " ".join(
        [
            "Citations in brackets give each rule's source:",
            "UP = SAMA Unified Compulsory Motor Insurance Policy;",
            "CMIR = SAMA Comprehensive Motor Insurance Rules; Art. = article;",
            '"interpretation of" = our reading of that article;',
            '"insurer-specific (illustrative)" = a term set by this fictional insurer;',
            '"reported, unverified" = from secondary sources.',
        ]
    ),
    "ar": " ".join(
        [
            "يبيّن ما بين المعقوفين مصدر كل قاعدة:",
            "الوثيقة الموحدة = الوثيقة الموحدة للتأمين الإلزامي على المركبات؛",
            "قواعد التأمين الشامل = قواعد التأمين الشامل على المركبات (البنك المركزي السعودي)؛",
            "«تفسير» = قراءتنا للمادة؛",
            "«خاص بالشركة (توضيحي)» = شرط وضعته هذه الشركة الوهمية؛",
            "«منقول، غير متحقق منه» = من مصادر ثانوية.",
        ]
    ),
}


def cite(source: str, lang: Lang) -> str:
    """Inline citation for a clause, from its `source:` field (so the disclaimer's "articles cited" holds)."""
    if lang == "en":
        return f"[{source}]"
    out = source
    for a, b in _AR_CITE:
        out = out.replace(a, b)
    return f"[{out}]"


def render(rules: RuleSet, lang: Lang) -> str:
    values = placeholders(rules, lang)
    label = rules.fiction.label_ar if lang == "ar" else rules.fiction.label_en
    title = rules.document.title_ar if lang == "ar" else rules.document.title_en
    lines = [f"# {_FMT.format(title, **values)}", "", f"> {label}"]
    if lang == "ar":
        lines.append(f"> {rules.fiction.label_en}")
    lines += ["", f"_{LEGEND[lang]}_"]
    for section in rules.document.sections:
        lines += ["", f"## {section.title[lang]}", ""]
        for clause in section.clauses:
            lines.append(f"- {_FMT.format(getattr(clause, lang), **values)} {cite(clause.source, lang)}")
            if clause.items:
                lines += [f"  - {getattr(lab, lang)}" for lab in rules.enumeration(clause.items).values()]
    lines += ["", "---", "", f"> {label}", ""]
    return "\n".join(lines)


def _cell(value: Any) -> str:
    if isinstance(value, list | tuple):
        return ", ".join(str(v) for v in value)
    return f"{value:,}" if isinstance(value, int) and not isinstance(value, bool) else str(value)


def render_sources(v1: RuleSet, v2: RuleSet) -> str:
    """The rule -> source table (D1.8), generated from the YAML so it cannot drift."""
    lines = [
        "# Rule → source table (generated by `engine policy`; do not edit)",
        "",
        f"> {v1.fiction.label_en}",
        "",
        "Source forms (D1.8): `<instrument> Art. N` · `interpretation of <instrument> Art. N` · "
        "`<instrument> (article TBC)` · `insurer-specific (illustrative)` · `reported, unverified`.",
        "",
        "## Instruments",
        "",
        "| Code | Instrument | Issuer | What we checked |",
        "|---|---|---|---|",
    ]
    lines += [f"| {k} | {i.name} | {i.issuer} | {i.checked} |" for k, i in v1.instruments.items()]
    lines += [
        "",
        "## Order of application (adjudication rules)",
        "",
        "| # | Rule | Applies when | Decision | Reason code | Source | Kind |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {n} | {s.step} | {s.applies} | {s.decision} | `{s.reason}` | {s.source} "
        f"| {source_kind(s.source)} |"
        for n, s in enumerate(v1.precedence, 1)
    ]
    for title, params, other in (
        ("Engine parameters", v1.params, v2.params),
        ("FAQ-only facts", v1.faq_only, v2.faq_only),
    ):
        lines += [
            "",
            f"## {title}",
            "",
            "| Name | v1 | v2 | Source | Kind | Note |",
            "|---|---|---|---|---|---|",
        ]
        for k, p in params.items():
            v2_value = _cell(other[k].value) if other[k].value != p.value else "="
            lines.append(
                f"| `{k}` | {_cell(p.value)} | {v2_value} | {p.source} | {source_kind(p.source)} | {p.note} |"
            )
    groups = {
        "Decision definitions": {k: (d.text, d.source, True) for k, d in v1.decisions.items()},
        "Cover types": v1.cover_types,
        "Claim types": v1.claim_types,
        "Other party": v1.other_party,
        "Report sources": v1.report_sources,
        "Out of scope (R0)": v1.out_of_scope_perils,
        "Licence status": v1.licence_status,
        "Authorised drivers": v1.authorised_drivers,
        "Third-party claim: deny": v1.exclusions.third_party_deny,
        "Third-party claim: pay + RECOVERY_RIGHT": v1.exclusions.third_party_recovery,
        "Own damage: deny (CMIR Art. 7)": v1.exclusions.own_damage_deny,
        "Late-report reasons: accepted": v1.late_report_justifications.accepted,
        "Late-report reasons: not accepted": v1.late_report_justifications.not_accepted,
        "Required documents (R7)": v1.required_documents,
    }
    for title, items in groups.items():
        lines += [
            "",
            f"## {title}",
            "",
            "| Key | Meaning | Source | Kind | Sampler generates |",
            "|---|---|---|---|---|",
        ]
        for k, item in items.items():
            text, src, gen = item if isinstance(item, tuple) else (item.en, item.source, item.generated)
            lines.append(f"| `{k}` | {text} | {src} | {source_kind(src)} | {'yes' if gen else 'no'} |")
    lines += [
        "",
        "## Other",
        "",
        "| Item | Source |",
        "|---|---|",
        f"| Intent labels (9) and overlap definitions | {v1.intents_source} |",
        f"| ID formats (policy / report numbers) | {v1.formats['source']} |",
        "| Adversarial items | evaluation design (D1.3), not an insurer rule |",
        "",
    ]
    return "\n".join(lines)


def output_path(version: str, lang: Lang) -> Path:
    return RULES_DIR / f"policy_{version}.{lang}.md"


def render_all() -> dict[Path, str]:
    out: dict[Path, str] = {}
    for version in ("v1", "v2"):
        rules = load_version(version)
        for lang in ("en", "ar"):
            out[output_path(version, lang)] = render(rules, lang)
    out[SOURCES_PATH] = render_sources(load_version("v1"), load_version("v2"))
    return out


def write_all() -> list[Path]:
    written = []
    for path, text in render_all().items():
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)
    return written
