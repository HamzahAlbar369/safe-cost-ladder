"""`engine gen`: generate all splits, run QA, write MANIFEST + review file (SPEC §4). No paid calls (D1.2).

Held-out is written once and only ever scanned by automated QA; nothing here prints its items.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from engine.contracts import (
    Case,
    ExtractGold,
    FaqGold,
    IntentGold,
    Ticket,
    TicketMeta,
)
from engine.datagen import sampler
from engine.datagen import variation as var
from engine.datagen.normalize import fact_present, normalise
from engine.datagen.rules import RuleSet, load_version
from engine.datagen.rules_engine import adjudicate
from engine.datagen.templates import bank_ar as AR
from engine.datagen.templates import bank_en as EN
from engine.datagen.templates import render as R
from engine.llm.pricing import ROOT

SEED = 20261030
OUT = ROOT / "data" / "generated"
SPLITS = ("dev", "heldout", "shifted")
SIZES = {"dev": 400, "heldout": 400, "shifted": 200}
AR_SHARE = 0.30
CELLS = (
    ("faq", "L1", 0.25),
    ("intent", "L2", 0.15),
    ("extract", "L2", 0.15),
    ("adjudicate", "L3", 0.20),
    ("adjudicate", "L4", 0.15),
    ("adjudicate", "L5", 0.10),
)
DEV_PAIRS = 40  # ~20% of dev items are members of an EN/AR pair (SPEC §4.3)
# shifted: adversarial kinds per (task, level) and policy-change (rules v2) counts (D1.3, SPEC §8)
ADVERSARIAL = {
    ("faq", "L1"): ["non_insurance"] * 4 + ["long_rambling"],
    ("intent", "L2"): ["non_insurance"] * 3 + ["garbled_or_empty"] * 3,
    ("extract", "L2"): ["long_rambling"],
    ("adjudicate", "L3"): ["prompt_injection"] * 2 + ["long_rambling"],
    ("adjudicate", "L4"): ["prompt_injection"] * 3,
    ("adjudicate", "L5"): ["garbled_or_empty"] * 2,
}
POLICY_CHANGE = {
    ("faq", "L1"): 10,
    ("adjudicate", "L3"): 12,
    ("adjudicate", "L4"): 12,
    ("adjudicate", "L5"): 6,
}
MAX_TRIES = 60


@dataclass
class Slot:
    split: str
    task: str
    level: str
    language: str
    rules_version: str = "v1"
    adversarial: str | None = None
    pair_id: str | None = None
    pair_role: str | None = None  # "en" (generated first) or "ar" (reuses the EN content)


@dataclass
class Content:
    """Language-neutral content of one ticket; EN/AR pairs share it."""

    people: dict[str, Any]
    task: str
    payload: dict[str, Any] = field(default_factory=dict)


def plan(split: str, rng: random.Random) -> list[Slot]:
    n = SIZES[split]
    slots: list[Slot] = []
    pairs_left = DEV_PAIRS if split == "dev" else 0
    total_ar = round(n * AR_SHARE)
    for task, level, share in CELLS:
        k = round(n * share)
        k_ar = round(k * AR_SHARE)
        cell = [Slot(split, task, level, "ar") for _ in range(k_ar)] + [
            Slot(split, task, level, "en") for _ in range(k - k_ar)
        ]
        if pairs_left:
            n_pairs = round(DEV_PAIRS * k_ar / total_ar)
            ars = [s for s in cell if s.language == "ar"][:n_pairs]
            ens = [s for s in cell if s.language == "en"][:n_pairs]
            for i, (a, e) in enumerate(zip(ars, ens, strict=True)):
                pid = f"pair-{task}-{level}-{i:02d}"
                a.pair_id = e.pair_id = pid
                a.pair_role, e.pair_role = "ar", "en"
        if split == "shifted":
            rng.shuffle(cell)
            kinds = ADVERSARIAL.get((task, level), [])
            for s, kind in zip(cell, kinds, strict=False):
                s.adversarial = kind
            normal = [s for s in cell if s.adversarial is None]
            for s in normal[: POLICY_CHANGE.get((task, level), 0)]:
                s.rules_version = "v2"
        slots += cell
    # EN pair members first so the AR member can reuse their content
    slots.sort(key=lambda s: 0 if s.pair_role == "en" else 1 if s.pair_role is None else 2)
    return slots


def _family(slot: Slot, rng: random.Random) -> R.Family:
    fams = R.families(slot.language, held_back=slot.split == "shifted")
    return rng.choices(fams, weights=[f.weight for f in fams])[0]


# --- content -------------------------------------------------------------------------------------------


def make_content(slot: Slot, rng: random.Random, rules: RuleSet) -> Content:
    p = R.people(rng)
    pn = f"OMI-{''.join(str(rng.randrange(10)) for _ in range(7))}"
    if slot.task == "faq":
        keys = sampler.FAQ_V2_SENSITIVE if slot.rules_version == "v2" else sampler.FAQ_KEYS
        return Content(
            p,
            "faq",
            {
                "key": rng.choice(keys),
                "variant": rng.randrange(2),
                "pn": pn,
                "n_context": rng.choice([1, 1, 2, 2, 3]),
                "nonins_i": rng.randrange(5),
            },
        )
    if slot.task == "intent":
        label = rng.choice(list(sampler.INTENT_KEYS))
        return Content(
            p,
            "intent",
            {
                "label": label,
                "bank_key": rng.choice(sampler.INTENT_KEYS[label]),
                "variant": rng.randrange(2),
                "pn": pn,
                "rn": f"NJ-{''.join(str(rng.randrange(10)) for _ in range(8))}",
                "acc": sampler._date(rng),
                "n_context": rng.choice([1, 2, 2, 3]),
                "nonins_i": rng.randrange(5),
                "garbled_i": rng.randrange(5),
            },
        )
    if slot.task == "extract":
        case, show = sampler.sample_extract_case(rng, rules)
        return Content(
            p,
            "extract",
            {"case": case, "show": show, "distractors": tuple(rng.sample(range(8), rng.choice([1, 2, 3])))},
        )
    if slot.adversarial == "garbled_or_empty":
        acc = sampler._date(rng)
        case = Case(
            claim_type="own_damage",
            cover="COMP",
            policy_number=pn,
            policy_end_date=acc + timedelta(days=200),
            accident_date=acc,
            report_date=acc,
            report_source="najm",
            other_party="unknown",
            documents=(),
        )
        return Content(
            p,
            "adjudicate",
            {
                "draft": sampler.Draft(case, "need_info", "garbled_or_empty", ("R7",)),
                "garbled_i": rng.randrange(5),
            },
        )
    draft = sampler.sample_adjudication(rng, rules, slot.level)
    lo, hi = sampler.DISTRACTORS_PER_LEVEL[slot.level]
    return Content(
        p,
        "adjudicate",
        {
            "draft": draft,
            "distractors": tuple(rng.sample(range(8), rng.randint(lo, hi))),
            "show_driver": rng.random() < 0.2,
        },
    )


# --- rendering -----------------------------------------------------------------------------------------


def _ramble(fam: R.Family, k: int) -> list[str]:
    return (EN.RAMBLE if fam.lang == "en" else AR.RAMBLE[fam.register])[:k]


def render_ticket(
    slot: Slot,
    content: Content,
    fam: R.Family,
    rng: random.Random,
    rules: RuleSet,
) -> tuple[str, Any, TicketMeta]:
    inten = var.HEAVY if slot.split == "shifted" else var.LIGHT
    pl, p = content.payload, content.people
    kind = slot.adversarial
    scenario = "adversarial" if kind else ("policy_change" if slot.rules_version == "v2" else "normal")
    reg_en = fam.lang == "en"
    if content.task == "faq":
        if kind == "non_insurance":
            pool = EN.NON_INSURANCE if reg_en else AR.NON_INSURANCE[fam.register]
            r = R.render_plain(pool[pl["nonins_i"] % len(pool)], fam, rng, p, framed=True)
            gold, meta_key = FaqGold(answer="out_of_scope"), None
        else:
            r = R.render_faq(pl["key"], pl["variant"], fam, p, rng, pl["pn"], pl["n_context"])
            if kind == "long_rambling":
                r.sentences = _ramble(fam, 4) + r.sentences
            gold, meta_key = FaqGold(answer=sampler.faq_answer(pl["key"], rules)), pl["key"]
        meta = TicketMeta(
            scenario=scenario, adversarial_kind=kind, faq_key=meta_key, design=f"faq:{meta_key}"
        )
        return var.apply(r, fam, rng, inten), gold, meta
    if content.task == "intent":
        if kind in ("non_insurance", "garbled_or_empty"):
            if kind == "non_insurance":
                pool = EN.NON_INSURANCE if reg_en else AR.NON_INSURANCE[fam.register]
                text = pool[pl["nonins_i"] % len(pool)]
            else:
                pool = EN.GARBLED if reg_en else AR.GARBLED[fam.register]
                text = pool[pl["garbled_i"] % len(pool)]
            r = R.render_plain(text, fam, rng, p, framed=kind == "non_insurance")
            gold = IntentGold(intent="other")
        else:
            r = R.render_intent(
                pl["bank_key"], pl["variant"], fam, p, rng, pl["pn"], pl["rn"], pl["acc"], pl["n_context"]
            )
            gold = IntentGold(intent=pl["label"])
        meta = TicketMeta(scenario=scenario, adversarial_kind=kind, design=f"intent:{pl.get('bank_key')}")
        text = var.apply(r, fam, rng, inten) if kind != "garbled_or_empty" else r.sentences[0]
        return text, gold, meta
    if content.task == "extract":
        c, show = pl["case"], pl["show"]
        view = R.ClaimView(
            case=c,
            show_pn=show["pn"],
            show_acc=show["acc"],
            show_rn=show["rn"],
            show_amt=show["amt"],
            show_fault=show["fault"],
            show_policy_details=rng.random() < 0.7,
            distractors=pl["distractors"],
            ramble=3 if kind == "long_rambling" else 0,
        )
        r = R.render_claim(view, fam, p, rng, "extract")
        gold = ExtractGold(
            policy_number=c.policy_number if show["pn"] else None,
            accident_date=c.accident_date if show["acc"] else None,
            report_number=c.report_number if show["rn"] else None,
            damage_amount_sar=c.damage_amount_sar if show["amt"] else None,
            fault_share=c.fault_share if show["fault"] else None,
        )
        meta = TicketMeta(
            scenario=scenario,
            adversarial_kind=kind,
            facts=tuple(r.facts),
            case=c,
            design="extract",
            distractors=tuple(f"distract_{i}" for i in pl["distractors"]),
        )
        return var.apply(r, fam, rng, inten), gold, meta
    # adjudicate
    draft: sampler.Draft = pl["draft"]
    adj = adjudicate(draft.case, rules)
    if adj.gold.decision != draft.expected:
        raise AssertionError(
            f"generator bug: design {draft.design} expected {draft.expected}, "
            f"engine says {adj.gold.decision} ({adj.gold.reasons})"
        )
    if kind == "garbled_or_empty":
        pool = EN.GARBLED if reg_en else AR.GARBLED[fam.register]
        claimish = "claim pls" if reg_en else "مطالبة"
        text = f"{claimish} {pool[pl['garbled_i'] % len(pool)]}"
        meta = TicketMeta(
            rule_ids=draft.rule_ids,
            scenario=scenario,
            adversarial_kind=kind,
            case=draft.case,
            trace=adj.trace,
            design=draft.design,
        )
        return text, adj.gold, meta
    view = R.ClaimView(
        case=draft.case,
        explicit_missing=bool(draft.view.get("explicit_missing")),
        distractors=pl["distractors"],
        lexp=draft.view.get("lexp"),
        injection=kind == "prompt_injection",
        ramble=4 if kind == "long_rambling" else 0,
        show_driver=pl["show_driver"],
    )
    r = R.render_claim(view, fam, p, rng, "adjudicate")
    meta = TicketMeta(
        rule_ids=draft.rule_ids,
        scenario=scenario,
        adversarial_kind=kind,
        facts=tuple(r.facts),
        case=draft.case,
        trace=adj.trace,
        design=draft.design,
        distractors=tuple(f"distract_{i}" for i in pl["distractors"]),
    )
    return var.apply(r, fam, rng, inten), adj.gold, meta


# --- duplicate control ---------------------------------------------------------------------------------


def shingles(text: str, n: int = 5) -> frozenset[str]:
    t = normalise(text)
    return frozenset(t[i : i + n] for i in range(max(1, len(t) - n + 1)))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


NEAR_DUP = 0.8


class DupIndex:
    """Exact duplicates across everything; near-duplicates vs other splits of the same task (SPEC §4.4)."""

    def __init__(self) -> None:
        self.exact: set[str] = set()
        self.by_task: dict[str, list[tuple[str, frozenset[str]]]] = {}

    def ok(self, split: str, task: str, text: str) -> bool:
        norm = normalise(text)
        if norm in self.exact:
            return False
        sh = shingles(text)
        for other_split, other in self.by_task.get(task, []):
            if other_split == split:
                continue
            if min(len(sh), len(other)) < NEAR_DUP * max(len(sh), len(other)):
                continue
            if jaccard(sh, other) >= NEAR_DUP:
                return False
        return True

    def add(self, split: str, task: str, text: str) -> None:
        self.exact.add(normalise(text))
        self.by_task.setdefault(task, []).append((split, shingles(text)))


# --- main ----------------------------------------------------------------------------------------------


def generate(seed: int = SEED) -> dict[str, list[Ticket]]:
    rules = {"v1": load_version("v1"), "v2": load_version("v2")}
    index = DupIndex()
    out: dict[str, list[Ticket]] = {}
    for split in SPLITS:
        rng = random.Random(f"{seed}:{split}")
        pair_content: dict[str, Content] = {}
        tickets: list[Ticket] = []
        for slot in plan(split, rng):
            rs = rules[slot.rules_version]
            content = pair_content.get(slot.pair_id) if slot.pair_role == "ar" else None
            for attempt in range(MAX_TRIES):
                if content is None or (attempt and attempt % 6 == 0 and slot.pair_role != "ar"):
                    content = make_content(slot, rng, rs)
                fam = _family(slot, rng)
                text, gold, meta = render_ticket(slot, content, fam, rng, rs)
                norm = normalise(text)
                if not all(fact_present(f, norm) for f in meta.facts):
                    continue
                if index.ok(split, slot.task, text):
                    break
            else:
                raise RuntimeError(f"could not generate a unique {split}/{slot.task}/{slot.level} item")
            index.add(split, slot.task, text)
            if slot.pair_role == "en":
                pair_content[slot.pair_id] = content
            tickets.append(
                Ticket(
                    id="",
                    split=split,
                    task_type=slot.task,
                    level=slot.level,
                    language=slot.language,
                    dialect=fam.dialect,
                    template_family=fam.id,
                    rules_version=slot.rules_version,
                    parallel_pair_id=slot.pair_id,
                    text=text,
                    gold=gold,
                    meta=meta,
                )
            )
        rng.shuffle(tickets)
        out[split] = [t.model_copy(update={"id": f"{split}-{i:04d}"}) for i, t in enumerate(tickets, 1)]
    return out
