"""Render the FICTIONAL policy document (EN + AR markdown) from a rules file (SPEC §4.1).

Output: data/rules/policy_<version>.<lang>.md. Deterministic; tests check the committed files match a fresh
render, so the document the models read can never drift from the rules that produce the gold labels.
"""

from __future__ import annotations

import string
from pathlib import Path
from typing import Any, Literal

from engine.datagen.rules import RULES_DIR, RuleSet, load_version

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


def placeholders(rules: RuleSet, lang: Lang) -> dict[str, Any]:
    shares = [str(s) for s in rules.params.fault_shares]
    joiner = " أو " if lang == "ar" else " or "
    return {
        **rules.params.model_dump(),
        **rules.faq_only.model_dump(),
        "insurer_en": rules.fiction.insurer_en,
        "insurer_ar": rules.fiction.insurer_ar,
        "version": rules.version,
        "fault_shares_text": joiner.join(shares)
        if lang == "ar"
        else ", ".join(shares[:-1]) + joiner + shares[-1],
    }


def render(rules: RuleSet, lang: Lang) -> str:
    values = placeholders(rules, lang)
    label = rules.fiction.label_ar if lang == "ar" else rules.fiction.label_en
    title = rules.document.title_ar if lang == "ar" else rules.document.title_en
    lines = [f"# {_FMT.format(title, **values)}", "", f"> {label}"]
    if lang == "ar":
        lines.append(f"> {rules.fiction.label_en}")
    for section in rules.document.sections:
        lines += ["", f"## {getattr(section.title, lang)}", ""]
        for clause in section.clauses:
            lines.append(f"- {_FMT.format(getattr(clause, lang), **values)}")
            if clause.items:
                lines += [f"  - {getattr(lab, lang)}" for lab in rules.enumeration(clause.items).values()]
    lines += ["", "---", "", f"> {label}", ""]
    return "\n".join(lines)


def output_path(version: str, lang: Lang) -> Path:
    return RULES_DIR / f"policy_{version}.{lang}.md"


def render_all() -> dict[Path, str]:
    out: dict[Path, str] = {}
    for version in ("v1", "v2"):
        rules = load_version(version)
        for lang in ("en", "ar"):
            out[output_path(version, lang)] = render(rules, lang)
    return out


def write_all() -> list[Path]:
    written = []
    for path, text in render_all().items():
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)
    return written
