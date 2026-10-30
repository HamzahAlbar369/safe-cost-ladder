"""SPEC §4.4 QA checks. Automated only: held-out is scanned for schema/duplicates/composition, never read by a
person or an LLM, and nothing here prints its items (CLAUDE.md held-out rule).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from engine.contracts import AdjudicateGold, ExtractGold, FaqGold, IntentGold, Ticket
from engine.datagen import gen as G
from engine.datagen.normalize import fact_present, normalise
from engine.datagen.rules import load_version
from engine.datagen.rules_engine import adjudicate
from engine.datagen.sampler import faq_answer
from engine.datagen.templates.render import BY_ID

COMPOSITION_TOL = 0.03
LEAK_TOL = 0.05
LABEL_FLOOR = 0.10
# D1.10: no ticket may have the customer say they will claim from the other party's insurer
OTHER_INSURER_PATTERNS = (
    re.compile(
        r"(claim|recover|go|apply)\w*\s+(it\s+)?(from|with|to|through)\s+(the\s+)?"
        r"(other (party|driver|car)'?s?|their|his|her)\s+insur",
        re.I,
    ),
    re.compile(r"(other (party|driver)'s|their|his|her) insurer (will|should|can) pay", re.I),
    re.compile(r"شركة تأمين(ه|ها| الطرف)"),
    re.compile(r"تأمين الطرف (الآخر|الثاني)"),
)
# D1.10: code-switching may only produce whole English words or "ال" + English word; nothing mangled
_MIXED = re.compile(r"[A-Za-z]")
_ARABIC = re.compile(r"[؀-ۿ]")
_OK_MIXED = re.compile(r"ال[A-Za-z]+")


def mangled_tokens(text: str) -> list[str]:
    cores = (w.strip(".,;:!?()،؟[]/-") for w in text.split())
    return [w for w in cores if _MIXED.search(w) and _ARABIC.search(w) and not _OK_MIXED.fullmatch(w)]


def _check(passed: bool, value: Any, threshold: str, detail: Any = None) -> dict[str, Any]:
    out = {"pass": bool(passed), "value": value, "threshold": threshold}
    if detail is not None:
        out["detail"] = detail
    return out


def schema(splits: dict[str, list[Ticket]]) -> dict[str, Any]:
    bad = 0
    for tickets in splits.values():
        for t in tickets:
            try:
                Ticket.model_validate_json(t.model_dump_json())
            except ValueError:
                bad += 1
    n = sum(len(v) for v in splits.values())
    return _check(bad == 0, f"{n - bad}/{n} valid", "100%")


def gold_rederived(splits: dict[str, list[Ticket]]) -> dict[str, Any]:
    """Gold comes only from the rules engine / rules file: recompute it from the stored facts."""
    rules = {"v1": load_version("v1"), "v2": load_version("v2")}
    bad: list[str] = []
    for tickets in splits.values():
        for t in tickets:
            rs = rules[t.rules_version]
            m = t.meta
            if isinstance(t.gold, AdjudicateGold):
                if m.case is None or adjudicate(m.case, rs).gold != t.gold:
                    bad.append(t.id)
            elif isinstance(t.gold, FaqGold) and m.faq_key is not None:
                if faq_answer(m.faq_key, rs) != t.gold.answer:
                    bad.append(t.id)
            elif isinstance(t.gold, ExtractGold) and m.case is not None:
                c, g = m.case, t.gold
                pairs = [
                    (g.policy_number, c.policy_number),
                    (g.accident_date, c.accident_date),
                    (g.report_number, c.report_number),
                    (g.damage_amount_sar, c.damage_amount_sar),
                    (g.fault_share, c.fault_share),
                ]
                if any(gv is not None and gv != cv for gv, cv in pairs):
                    bad.append(t.id)
    return _check(not bad, len(bad), "0 mismatches", bad[:10] or None)


def duplicates(splits: dict[str, list[Ticket]]) -> tuple[dict[str, Any], dict[str, Any]]:
    seen: dict[str, str] = {}
    exact = 0
    for split, tickets in splits.items():
        for t in tickets:
            key = normalise(t.text)
            if key in seen and seen[key] != split:
                exact += 1
            seen.setdefault(key, split)
    near, worst = 0, 0.0
    shing = {s: [(t.task_type, G.shingles(t.text)) for t in ts] for s, ts in splits.items()}
    names = list(splits)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            for task_a, sa in shing[a]:
                for task_b, sb in shing[b]:
                    if task_a != task_b or min(len(sa), len(sb)) < G.NEAR_DUP * max(len(sa), len(sb)):
                        continue
                    j = G.jaccard(sa, sb)
                    worst = max(worst, j)
                    near += j >= G.NEAR_DUP
    return (
        _check(exact == 0, exact, "0"),
        _check(
            near == 0,
            near,
            f"0 pairs with char-5-gram Jaccard >= {G.NEAR_DUP}",
            {"max_cross_split_jaccard_among_comparable": round(worst, 3)},
        ),
    )


def targets(split: str) -> dict[tuple[str, str, str], float]:
    out: dict[tuple[str, str, str], float] = {}
    for task, level, share in G.CELLS:
        out[(task, level, "ar")] = share * G.AR_SHARE
        out[(task, level, "en")] = share * (1 - G.AR_SHARE)
    return out


def composition(splits: dict[str, list[Ticket]]) -> tuple[dict[str, Any], dict[str, Any]]:
    worst, table = 0.0, {}
    for split, tickets in splits.items():
        n = len(tickets)
        counts = Counter((t.task_type, t.level, t.language) for t in tickets)
        rows = {}
        for cell, target in targets(split).items():
            actual = counts.get(cell, 0) / n
            worst = max(worst, abs(actual - target))
            rows["/".join(cell)] = {
                "n": counts.get(cell, 0),
                "share": round(actual, 4),
                "target": round(target, 4),
            }
        ar = sum(t.language == "ar" for t in tickets) / n
        worst = max(worst, abs(ar - G.AR_SHARE))
        dialect = Counter(t.dialect for t in tickets if t.language == "ar")
        table[split] = {"n": n, "arabic_share": round(ar, 4), "cells": rows, "arabic_dialects": dict(dialect)}
    return (_check(worst <= COMPOSITION_TOL, round(worst * 100, 2), "max deviation <= 3 pts"), table)


def fact_preservation(splits: dict[str, list[Ticket]]) -> dict[str, Any]:
    total = bad = 0
    for tickets in splits.values():
        for t in tickets:
            norm = normalise(t.text)
            for f in t.meta.facts:
                total += 1
                bad += not fact_present(f, norm)
    return _check(bad == 0, f"{total - bad}/{total} facts present", "100%")


def _label(t: Ticket) -> str | None:
    g = t.gold
    if isinstance(g, IntentGold):
        return g.intent
    if isinstance(g, AdjudicateGold):
        return g.decision
    if isinstance(g, FaqGold):
        return str(g.answer)
    return None


def _loo_hits(items: list[tuple[str, str]]) -> tuple[int, int]:
    """(family leave-one-out hits, majority-class hits) for one split's items of one task."""
    overall = Counter(lab for _, lab in items)
    fam_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for fam, lab in items:
        fam_counts[fam][lab] += 1
    hits = 0
    for fam, lab in items:
        c = fam_counts[fam].copy()
        c[lab] -= 1
        best = max(c.values()) if c else 0
        preds = [k for k, v in c.items() if v == best and v > 0]
        pred = max(preds, key=lambda k: overall[k]) if preds else overall.most_common(1)[0][0]
        hits += pred == lab
    return hits, overall.most_common(1)[0][1]


def template_leak(splits: dict[str, list[Ticket]]) -> dict[str, Any]:
    """Leave-one-out within each split: predict the label from the family's other items, versus the split's
    majority-class rate; hits pooled over splits. Within-split because families are assigned at random inside
    a split, while the split itself (held-back families, rules v2 answers) legitimately shifts the label mix
    (DECISIONS D1.9)."""
    by_task: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for split, tickets in splits.items():
        for t in tickets:
            lab = _label(t)
            if lab is not None:
                by_task[t.task_type][split].append((t.template_family, lab))
    detail, worst = {}, -1.0
    for task, per_split in by_task.items():
        n = sum(len(v) for v in per_split.values())
        hits = maj = 0
        for items in per_split.values():
            h, m = _loo_hits(items)
            hits, maj = hits + h, maj + m
        acc, majority = hits / n, maj / n
        worst = max(worst, acc - majority)
        detail[task] = {
            "family_loo_acc": round(acc, 4),
            "majority_rate": round(majority, 4),
            "gap_pts": round((acc - majority) * 100, 2),
        }
    return _check(worst <= LEAK_TOL, round(worst * 100, 2), "<= majority-class rate + 5 pts", detail)


def decision_distribution(splits: dict[str, list[Ticket]]) -> dict[str, Any]:
    out, flags = {}, []
    for split, tickets in splits.items():
        adj = [t.gold.decision for t in tickets if isinstance(t.gold, AdjudicateGold)]
        c = Counter(adj)
        shares = {k: round(c.get(k, 0) / len(adj), 4) for k in ("approve", "partial", "deny", "need_info")}
        out[split] = {"n_adjudicate": len(adj), "counts": dict(c), "shares": shares}
        flags += [f"{split}:{k}={v:.1%}" for k, v in shares.items() if v < LABEL_FLOOR]
    return {
        "pass": not flags,
        "flags": flags,
        "threshold": "flag any label < 10% of adjudication items",
        "per_split": out,
    }


def structure(splits: dict[str, list[Ticket]]) -> dict[str, Any]:
    """Pairs, held-back families, adversarial and policy-change counts, dialect lean."""
    problems: list[str] = []
    dev = splits.get("dev", [])
    pairs: dict[str, list[Ticket]] = defaultdict(list)
    for t in dev:
        if t.parallel_pair_id:
            pairs[t.parallel_pair_id].append(t)
    for pid, ts in pairs.items():
        langs = sorted(t.language for t in ts)
        same = len({(t.meta.case, t.meta.faq_key, _label(t)) for t in ts}) == 1
        if langs != ["ar", "en"] or not same:
            problems.append(f"pair {pid} malformed")
    for split, tickets in splits.items():
        held = {BY_ID[t.template_family].held_back for t in tickets}
        if held != ({True} if split == "shifted" else {False}):
            problems.append(f"{split}: wrong family pool")
    shifted = splits.get("shifted", [])
    adv = sum(t.meta.scenario == "adversarial" for t in shifted)
    v2 = sum(t.rules_version == "v2" for t in shifted)
    ar_shift = [t for t in shifted if t.language == "ar"]
    dialectal = sum(t.dialect in ("saudi", "mixed") for t in ar_shift) / max(1, len(ar_shift))
    ar_dev = [t for t in dev if t.language == "ar"]
    msa_dev = sum(t.dialect == "msa" for t in ar_dev) / max(1, len(ar_dev))
    if not 15 <= adv <= 25:
        problems.append(f"shifted adversarial count {adv}")
    if v2 != 40:
        problems.append(f"shifted rules_v2 count {v2}")
    if dialectal <= 0.5 or msa_dev <= 0.5:
        problems.append("dialect lean wrong")
    other_insurer = [
        t.id for ts in splits.values() for t in ts if any(p.search(t.text) for p in OTHER_INSURER_PATTERNS)
    ]
    mangled = sum(bool(mangled_tokens(t.text)) for ts in splits.values() for t in ts)
    if mangled:
        problems.append(f"{mangled} ticket(s) with mangled mixed-script tokens")
    if other_insurer:
        problems.append(f"{len(other_insurer)} ticket(s) claim from the other party's insurer")
    value = {
        "dev_pairs": len(pairs),
        "dev_pair_items_share": round(2 * len(pairs) / max(1, len(dev)), 4),
        "shifted_adversarial": adv,
        "shifted_rules_v2": v2,
        "shifted_arabic_dialectal_share": round(dialectal, 4),
        "dev_arabic_msa_share": round(msa_dev, 4),
        "tickets_claiming_from_other_insurer": len(other_insurer),
        "tickets_with_mangled_tokens": mangled,
    }
    return _check(
        not problems,
        value,
        "pairs well-formed; held-back families only in shifted; ~20 adversarial; "
        "40 rules_v2; shifted AR dialect-leaning; dev AR mostly MSA",
        problems or None,
    )


# --- D1.11: one value per fact, and clean policy documents ----------------------------------------------

_PCT = re.compile(r"(?<![\d.])(\d{1,3})\s*%")
_POLICY = re.compile(r"omi-\d{7}")
_AMOUNT = re.compile(r"(?:sar|sr)\s*(\d+)(?:\.00)?(?![\d.])|(?<![\d.])(\d+)(?:\.00)?\s*(?:sar|riyals?|ريال)")
_ISO = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)")
_PLACEHOLDER = re.compile(r"\{[^{}\n]*\}")


def fact_conflicts(t: Ticket) -> list[str]:
    """Problems if a ticket states two different fault shares or policy numbers, or (claim tickets) an amount
    or date that is not one of the case's own values; a second amount is allowed only in the
    assessment-contradiction case."""
    norm = normalise(t.text)
    problems = []
    pcts = set(_PCT.findall(norm))
    if len(pcts) > 1:
        problems.append(f"fault shares {sorted(pcts)}")
    pols = set(_POLICY.findall(norm))
    if len(pols) > 1:
        problems.append(f"policy numbers {sorted(pols)}")
    c = t.meta.case
    if c is not None and t.meta.adversarial_kind != "garbled_or_empty":
        amounts = {int(a or b) for a, b in _AMOUNT.findall(norm)}
        allowed = {c.damage_amount_sar, c.sum_insured_sar, c.conflict_damage_sar} - {None}
        if amounts - allowed:
            problems.append(f"amounts not in the case {sorted(amounts - allowed)}")
        dates = set(_ISO.findall(norm))
        known = {
            c.policy_end_date,
            c.accident_date,
            c.report_date,
            c.licence_expiry_date,
            c.licence_renewal_date,
        }
        known_iso = {d.isoformat() for d in known if d is not None}
        if dates - known_iso:
            problems.append(f"dates not in the case {sorted(dates - known_iso)}")
        if t.task_type == "adjudicate" and c.accident_date.isoformat() not in dates:
            problems.append("accident date missing")
    return problems


def fact_consistency(splits: dict[str, list[Ticket]]) -> dict[str, Any]:
    bad = {t.id: p for ts in splits.values() for t in ts if (p := fact_conflicts(t))}
    n = sum(len(v) for v in splits.values())
    return _check(
        not bad,
        f"{n - len(bad)}/{n} tickets consistent",
        "0 tickets with two fault shares, two policy numbers, or an amount/date outside the case",
        dict(list(bad.items())[:5]) or None,
    )


def policy_documents() -> dict[str, Any]:
    from engine.datagen.render_policy import render_all

    left = {p.name: _PLACEHOLDER.findall(text) for p, text in render_all().items()}
    left = {k: v for k, v in left.items() if v}
    return _check(
        not left,
        f"{len(render_all())} documents, {sum(map(len, left.values()))} placeholders left",
        "0 unresolved {...} in policy v1/v2 EN/AR and SOURCES.md",
        left or None,
    )


def run_all(splits: dict[str, list[Ticket]]) -> dict[str, Any]:
    exact, near = duplicates(splits)
    comp, table = composition(splits)
    return {
        "schema_validity": schema(splits),
        "gold_rederived_from_rules": gold_rederived(splits),
        "exact_duplicates_across_splits": exact,
        "near_duplicates_across_splits": near,
        "composition": comp,
        "fact_preservation": fact_preservation(splits),
        "template_leak": template_leak(splits),
        "structure": structure(splits),
        "fact_consistency": fact_consistency(splits),
        "policy_documents_no_placeholders": policy_documents(),
        "decision_distribution": decision_distribution(splits),
        "_composition_table": table,
    }


def blocking_failures(report: dict[str, Any]) -> list[str]:
    return [
        k
        for k, v in report.items()
        if not k.startswith("_") and k != "decision_distribution" and not v["pass"]
    ]
