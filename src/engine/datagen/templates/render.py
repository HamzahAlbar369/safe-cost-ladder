"""Template families and text rendering for the four tasks (SPEC §4.2 step 3, D1.2). FICTIONAL.

A family fixes the channel frame, layout (prose / chat lines / form fields / bullets), phrase-variant index,
date and amount formats and digit script. Families never depend on the label, so the label cannot be
predicted from the family (template-leak check). Rendering returns sentences (the variation layer may reorder
the movable middle ones) and the gold-relevant surface facts.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from engine.contracts import Case
from engine.datagen.normalize import AR_MONTHS, EN_MONTHS
from engine.datagen.templates import bank_ar as AR
from engine.datagen.templates import bank_en as EN

REQUIRED_DOCS = ("accident_report", "registration", "licence_copy", "damage_photos", "damage_assessment")
VAGUE_DATE = {"en": "a few days ago", "ar": "قبل أيام"}

Mode = Literal["prose", "chat", "form", "bullets"]


@dataclass(frozen=True)
class Family:
    id: str
    lang: Literal["en", "ar"]
    dialect: Literal["none", "msa", "saudi", "mixed"]
    register: Literal["en", "msa", "saudi"]
    frame: str
    mode: Mode
    variant: int  # preferred phrase variant (0/1 dev, 2 held back)
    labels: str | None
    date_fmt: str
    amount_fmt: str
    arabic_digits: bool = False
    held_back: bool = False
    weight: float = 1.0  # sampling weight within (language, held_back)


FAMILIES: tuple[Family, ...] = (
    Family("en_email", "en", "none", "en", "email", "prose", 0, None, "long", "SAR {n}"),
    Family("en_chat", "en", "none", "en", "chat", "chat", 1, None, "dmy", "{n} riyals"),
    Family("en_form", "en", "none", "en", "form", "form", 0, "C", "iso", "{n} SAR"),
    Family("en_agent", "en", "none", "en", "agent", "bullets", 1, "A", "dmy", "SAR {n}"),
    Family("en_story", "en", "none", "en", "story", "prose", 1, None, "long", "{n} SAR"),
    Family("en_sms", "en", "none", "en", "sms", "prose", 0, None, "iso", "SR {n}"),
    Family("en_voice", "en", "none", "en", "voice", "prose", 2, None, "long", "{n} riyals", held_back=True),
    Family(
        "en_broker", "en", "none", "en", "broker", "bullets", 2, "B", "dmy_dash", "SAR {n}.00", held_back=True
    ),
    Family(
        "ar_msa_letter", "ar", "msa", "msa", "letter", "prose", 0, None, "long_ar", "{n} ريال", weight=1.5
    ),
    Family("ar_msa_form", "ar", "msa", "msa", "form", "form", 0, "C", "iso", "{n} ريال", weight=1.5),
    Family(
        "ar_msa_agent",
        "ar",
        "msa",
        "msa",
        "agent",
        "bullets",
        1,
        "A",
        "ymd_slash",
        "{n} ريال سعودي",
        weight=1.5,
    ),
    Family(
        "ar_msa_story", "ar", "msa", "msa", "story", "prose", 1, None, "long_ar", "{n} ريال", True, weight=1.5
    ),
    Family("ar_sa_chat", "ar", "saudi", "saudi", "chat", "chat", 0, None, "dmy", "{n} ريال"),
    Family("ar_sa_voice", "ar", "saudi", "saudi", "voice", "prose", 1, None, "long_ar", "{n} ريال"),
    Family(
        "ar_sa_heavy",
        "ar",
        "saudi",
        "saudi",
        "chat",
        "chat",
        2,
        None,
        "dmy",
        "{n} ريال",
        True,
        held_back=True,
        weight=1.5,
    ),
    Family(
        "ar_mixed_agent",
        "ar",
        "mixed",
        "saudi",
        "mixed_agent",
        "bullets",
        2,
        "B",
        "iso",
        "SAR {n}",
        held_back=True,
    ),
)
BY_ID = {f.id: f for f in FAMILIES}


def families(lang: str, held_back: bool) -> list[Family]:
    return [f for f in FAMILIES if f.lang == lang and f.held_back == held_back]


# --- value formatting ----------------------------------------------------------------------------------

_AR_DIGITS = str.maketrans("0123456789,", "٠١٢٣٤٥٦٧٨٩٬")


def fmt_date(d: date, fam: Family) -> str:
    s = {
        "long": f"{d.day} {EN_MONTHS[d.month - 1].capitalize()} {d.year}",
        "long_ar": f"{d.day} {AR_MONTHS[d.month - 1]} {d.year}",
        "dmy": f"{d.day:02d}/{d.month:02d}/{d.year}",
        "dmy_dash": f"{d.day:02d}-{d.month:02d}-{d.year}",
        "iso": d.isoformat(),
        "ymd_slash": f"{d.year}/{d.month:02d}/{d.day:02d}",
    }[fam.date_fmt]
    return s.translate(_AR_DIGITS) if fam.arabic_digits else s


def fmt_amount(n: int, fam: Family) -> str:
    plain = fam.amount_fmt == "{n} riyals"  # chat/voice style: no thousands separator
    s = fam.amount_fmt.format(n=str(n) if plain else f"{n:,}")
    return s.translate(_AR_DIGITS) if fam.arabic_digits else s


def fmt_num(n: int, fam: Family) -> str:
    return str(n).translate(_AR_DIGITS) if fam.arabic_digits else str(n)


# --- shared helpers ------------------------------------------------------------------------------------


@dataclass
class Rendered:
    sentences: list[str]  # middle (movable) sentences
    head: list[str] = field(default_factory=list)
    tail: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    joiner: str = " "
    movable: bool = True


def _bank(fam: Family) -> dict[str, list[str]]:
    return {"en": EN.S, "msa": AR.MSA, "saudi": AR.SAUDI}[fam.register]


def _pick(options: list[str], fam: Family, rng: random.Random) -> str:
    if fam.held_back:
        return options[2]
    other = 1 - fam.variant
    return options[fam.variant if rng.random() < 0.7 else other]


class _Strict(dict):
    def __missing__(self, key: str) -> str:
        raise KeyError(f"template placeholder {{{key}}} not filled")


def _fill(template: str, slots: dict[str, Any]) -> str:
    return template.format_map(_Strict(slots))


def _frame(fam: Family, rng: random.Random, slots: dict[str, Any]) -> tuple[list[str], list[str]]:
    frames = EN.FRAMES if fam.lang == "en" else AR.FRAMES
    heads, tails = frames[fam.frame]
    head = _fill(rng.choice(heads), slots)
    tail = _fill(rng.choice(tails), slots)
    return [head] if head else [], [tail] if tail else []


def _labels(fam: Family) -> dict[str, str]:
    assert fam.labels
    return (EN.LABELS if fam.lang == "en" else AR.LABELS)[fam.labels]


def _join_mode(fam: Family) -> str:
    if fam.mode != "prose":
        return "\n"
    return (
        " ... " if fam.frame == "voice" and fam.held_back else " "
    )  # unpunctuated transcript: spoken pauses


def _lang_data(fam: Family):
    return EN if fam.lang == "en" else AR


def _cover(fam: Family, cover: str, rng: random.Random) -> str:
    opts = (EN.COVER if fam.lang == "en" else AR.COVER)[cover]
    return opts[2] if fam.held_back else rng.choice(opts[:2])


def _src(fam: Family, src: str) -> tuple[str, str]:
    s = (EN.SRC if fam.lang == "en" else AR.SRC)[src]
    return s, s[0].upper() + s[1:] if fam.lang == "en" else s


# --- people, places, cars (fictional) ------------------------------------------------------------------

NAMES_EN = [
    "Faisal",
    "Abdullah",
    "Noura",
    "Sara",
    "Khalid",
    "Mohammed",
    "Reem",
    "Turki",
    "Hessa",
    "Omar",
    "Lama",
    "Saad",
    "Abeer",
    "Yousef",
    "Maha",
    "Nasser",
    "Dana",
    "Majed",
    "Haya",
    "Bandar",
]
NAMES_AR = [
    "فيصل",
    "عبدالله",
    "نورة",
    "سارة",
    "خالد",
    "محمد",
    "ريم",
    "تركي",
    "حصة",
    "عمر",
    "لمى",
    "سعد",
    "عبير",
    "يوسف",
    "مها",
    "ناصر",
    "دانة",
    "ماجد",
    "هيا",
    "بندر",
]
CITIES_EN = ["Riyadh", "Jeddah", "Dammam", "Khobar", "Abha", "Taif", "Madinah", "Tabuk", "Buraidah", "Hail"]
CITIES_AR = ["الرياض", "جدة", "الدمام", "الخبر", "أبها", "الطائف", "المدينة المنورة", "تبوك", "بريدة", "حائل"]
CARS = [
    "Toyota Camry 2021",
    "Hyundai Accent 2019",
    "Nissan Patrol 2022",
    "Kia K5 2023",
    "GMC Yukon 2020",
    "Toyota Land Cruiser 2018",
    "Lexus ES 2022",
    "Chevrolet Tahoe 2021",
    "Hyundai Sonata 2020",
    "Mazda 6 2019",
]


def people(rng: random.Random) -> dict[str, Any]:
    """Language-neutral indices so EN/AR parallel pairs get matching people and places."""
    return {
        "name_i": rng.randrange(len(NAMES_EN)),
        "other_i": rng.randrange(len(NAMES_EN)),
        "city_i": rng.randrange(len(CITIES_EN)),
        "car_i": rng.randrange(len(CARS)),
        "phone": "05" + "".join(str(rng.randrange(10)) for _ in range(8)),
        "claim": f"CLM-{rng.randrange(10000, 99999)}",
        "years": rng.randrange(3, 11),
    }


def base_slots(fam: Family, p: dict[str, Any]) -> dict[str, Any]:
    ar = fam.lang == "ar"
    return {
        "name": (NAMES_AR if ar else NAMES_EN)[p["name_i"]],
        "city": (CITIES_AR if ar else CITIES_EN)[p["city_i"]],
        "car": CARS[p["car_i"]],
        "phone": p["phone"],
        "claim": p["claim"],
        "years": fmt_num(p["years"], fam),
    }


# --- adjudicate / extract ------------------------------------------------------------------------------


@dataclass
class ClaimView:
    """What the ticket shows. `show_*` flags let extract tickets omit fields; adjudicate shows all."""

    case: Case
    show_pn: bool = True
    show_acc: bool = True
    show_rn: bool = True
    show_amt: bool = True
    show_fault: bool = True
    show_policy_details: bool = True  # cover + end date sentence parts
    explicit_missing: bool = False
    distractors: tuple[int, ...] = ()
    injection: bool = False
    ramble: int = 0
    show_driver: bool = False


def _doc_list(fam: Family, docs: tuple[str, ...], src: str, rng: random.Random, third_party: bool) -> str:
    """Document names; third-party claims name the claimant's vehicle and the at-fault driver (D1.11)."""
    if third_party:
        table = EN.DOC_TP if fam.lang == "en" else AR.DOC_TP[fam.register]
    else:
        table = EN.DOC if fam.lang == "en" else AR.DOC[fam.register]
    idx = 2 if fam.held_back else rng.randrange(2)
    names = [_fill(table[d][idx], {"src": src, "srcn": src.removeprefix("the ")}) for d in docs]
    if fam.lang == "en":
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return "، ".join(names[:-1]) + " و" + names[-1] if len(names) > 1 else names[0]


def _driver_text(fam: Family, driver: str, slots: dict[str, Any], rng: random.Random) -> str:
    table = EN.DRIVER if fam.lang == "en" else AR.DRIVER[fam.register]
    return _fill(_pick(table[driver], fam, rng), slots)


def render_claim(view: ClaimView, fam: Family, p: dict[str, Any], rng: random.Random, task: str) -> Rendered:
    c = view.case
    bank = _bank(fam)
    src, src_cap = _src(fam, c.report_source)
    slots = base_slots(fam, p) | {
        "pn": c.policy_number,
        "cover": _cover(fam, c.cover, rng),
        "end": fmt_date(c.policy_end_date, fam),
        "acc": fmt_date(c.accident_date, fam) if view.show_acc else VAGUE_DATE[fam.lang],
        "rep": fmt_date(c.report_date, fam),
        "src": src,
        "Src": src_cap,
        "srcn": src.removeprefix("the "),
        "rn": c.report_number or "",
        "fault": fmt_num(c.fault_share, fam) if c.fault_share is not None else "",
        "amt": fmt_amount(c.damage_amount_sar, fam) if c.damage_amount_sar is not None else "",
        "conf": fmt_amount(c.conflict_damage_sar, fam) if c.conflict_damage_sar is not None else "",
        "si": fmt_amount(c.sum_insured_sar, fam) if c.sum_insured_sar is not None else "",
        "other_name": (NAMES_AR if fam.lang == "ar" else NAMES_EN)[p["other_i"]],
        "lexp": fmt_date(c.licence_expiry_date, fam) if c.licence_expiry_date else "",
        "renew": fmt_date(c.licence_renewal_date, fam) if c.licence_renewal_date else "",
    }
    slots["name_tp"] = slots["other_name"]
    facts: list[str] = []
    s: list[str] = []

    def say(key: str, **extra: Any) -> str:
        return _undangle(_fill(_pick(bank[key], fam, rng), slots | extra))

    od = c.claim_type == "own_damage"
    # policy
    if view.show_pn and view.show_policy_details:
        s.append(say("policy"))
    if view.show_pn:
        facts.append(c.policy_number)
    # event
    event_key = "event_tp" if not od else f"event_{c.other_party}"
    s.append(say(event_key, name=slots["other_name"]))
    if view.show_acc:
        facts.append(c.accident_date.isoformat())
    # report and fault
    show_fault = view.show_fault and c.fault_share is not None
    if view.show_rn and c.report_number:
        s.append(say("report_fault" if show_fault else "report_only"))
        facts.append(c.report_number)
    elif show_fault:
        s.append(say("fault_only"))
    if show_fault:
        facts.append(str(c.fault_share))
    # damage
    if view.show_amt and c.damage_amount_sar is not None:
        if c.damage_source == "garage_quote":
            s.append(say("garage_quote"))
            facts.append(str(c.damage_amount_sar))
        elif c.conflict_damage_sar is not None:
            s.append(say("conflict"))
            facts += [str(c.damage_amount_sar), str(c.conflict_damage_sar)]
        else:
            s.append(say("damage_od" if od else "damage_tp"))
            facts.append(str(c.damage_amount_sar))
    if task == "adjudicate":
        if od and c.cover == "COMP" and c.sum_insured_sar is not None:
            s.append(say("si"))
            facts.append(str(c.sum_insured_sar))
        if c.technical_total_loss:
            s.append(say("ttl"))
        if c.driver == "insured" and view.show_driver and not c.violations and c.licence_status == "valid":
            s.append(say("driver_self"))
        elif c.driver != "insured":
            s.append(say("driver", driver=_driver_text(fam, c.driver, slots, rng)))
        if c.licence_status == "expired":
            key = "licence_expired_renewed" if c.licence_renewal_date else "licence_expired_not_renewed"
            s.append(say(key))
            facts.append(c.licence_renewal_date.isoformat() if c.licence_renewal_date else "")
        elif c.licence_status != "valid":
            s.append(say(f"licence_{c.licence_status}"))
        for v in c.violations:
            if v in ("red_light", "wrong_direction") or (v == "racing_or_drifting" and od):
                key = f"v_{v}_{'caused' if c.violation_caused_accident else 'not_caused'}"
                if not od:
                    key = f"v_{v}_caused" if v != "racing_or_drifting" else "v_racing_or_drifting"
            else:
                key = f"v_{v}"
            s.append(say(key))
        if c.late_justification:
            s.append(say(f"late_{c.late_justification}"))
        renewed_later = c.licence_renewal_date is not None and c.licence_renewal_date > c.report_date
        s.append(say("reported_past" if renewed_later else "reported"))  # keep the timeline coherent
        facts.append(c.report_date.isoformat())
        if c.documents:
            s.append(say("docs", docs=_doc_list(fam, c.documents, src, rng, not od)))
        if view.explicit_missing:
            missing = [d for d in REQUIRED_DOCS if d not in c.documents]
            if missing:
                s.append(say("docs_missing", missing=_doc_list(fam, tuple(missing), src, rng, not od)))
    else:  # extract: dates of filing are a distractor date
        if rng.random() < 0.6:
            s.append(say("reported"))
    data = _lang_data(fam)
    dis = data.DISTRACT if fam.lang == "en" else data.DISTRACT[fam.register]
    for i in view.distractors:
        s.append(_fill(dis[i % len(dis)], slots))
    if view.ramble:
        ram = data.RAMBLE if fam.lang == "en" else data.RAMBLE[fam.register]
        s += ram[: view.ramble]
    if view.injection:
        s.insert(rng.randrange(1, len(s) + 1), say("injection"))
    facts = [f for f in facts if f]
    head, tail = _frame(fam, rng, slots)
    if fam.mode in ("form", "bullets"):
        return _as_fields(view, fam, slots, s, head, tail, facts, task)
    return Rendered(sentences=s, head=head, tail=tail, facts=facts, joiner=_join_mode(fam))


def _undangle(text: str) -> str:
    """Drop the date preposition when the accident date is deliberately vague (extract tickets)."""
    for a, b in (
        ("On a few days ago", "A few days ago"),
        ("on a few days ago", "a few days ago"),
        ("بتاريخ قبل أيام", "قبل أيام"),
        ("في قبل أيام", "قبل أيام"),
        ("يوم قبل أيام", "قبل أيام"),
    ):
        text = text.replace(a, b)
    return text


def _as_fields(
    view: ClaimView,
    fam: Family,
    slots: dict[str, Any],
    prose: list[str],
    head: list[str],
    tail: list[str],
    facts: list[str],
    task: str,
) -> Rendered:
    """Form/bullet layout: core values as labelled fields, everything else as a notes line."""
    c, lab = view.case, _labels(fam)
    bullet = "- " if fam.mode == "bullets" else ""
    fields: list[str] = []

    def add(key: str, value: str) -> None:
        fields.append(f"{bullet}{lab[key]}: {value}")

    party = (EN.PARTY if fam.lang == "en" else AR.PARTY)[c.other_party]
    ctype = (EN.CLAIM_TYPE if fam.lang == "en" else AR.CLAIM_TYPE)[c.claim_type]
    if view.show_pn:
        add("pn", c.policy_number)
        if view.show_policy_details:
            add("cover", slots["cover"])
            add("end", slots["end"])
    if task == "adjudicate":
        add("claim_type", ctype)
        add("party", party)
    if view.show_acc:
        add("acc", slots["acc"])
    if view.show_rn and c.report_number:
        add("src", slots["src"])
        add("rn", c.report_number)
    if view.show_fault and c.fault_share is not None:
        add("fault", f"{slots['fault']}%")
    assessed = c.conflict_damage_sar is None and c.damage_source == "assessment"
    if view.show_amt and c.damage_amount_sar is not None and assessed:
        add("amt" if c.claim_type == "own_damage" else "amt_tp", slots["amt"])
    if task == "adjudicate":
        if c.claim_type == "own_damage" and c.cover == "COMP" and c.sum_insured_sar is not None:
            add("si", slots["si"])
        add("rep", slots["rep"])
    # notes: the narrative sentences not already shown as fields
    shown_keys = {
        "policy",
        "report_fault",
        "report_only",
        "fault_only",
        "damage_od",
        "damage_tp",
        "si",
        "reported",
        "reported_past",
    }
    bank = _bank(fam)
    shown_texts = {_fill(v, slots | {"name": slots["other_name"]}) for k in shown_keys for v in bank[k]}
    notes = [x for x in prose if x not in shown_texts]
    if task == "extract" and any(x for x in prose if x in shown_texts and slots["rep"] in x):
        add("rep", slots["rep"])
    body = fields + ([f"{bullet}{lab['notes']}: " + " ".join(notes)] if notes else [])
    return Rendered(sentences=body, head=head, tail=tail, facts=facts, joiner="\n", movable=False)


# --- intent --------------------------------------------------------------------------------------------


def render_intent(
    label_key: str,
    variant: int | None,
    fam: Family,
    p: dict[str, Any],
    rng: random.Random,
    pn: str,
    rn: str,
    acc: date,
    n_context: int,
) -> Rendered:
    data = _lang_data(fam)
    bank = data.INTENT if fam.lang == "en" else data.INTENT[fam.register]
    ctx = data.INTENT_CONTEXT if fam.lang == "en" else data.INTENT_CONTEXT[fam.register]
    slots = base_slots(fam, p) | {"pn": pn, "rn": rn, "acc": fmt_date(acc, fam)}
    options = bank[label_key]
    need = options[2] if fam.held_back else options[variant if variant is not None else rng.randrange(2)]
    context = [_fill(x, slots) for x in rng.sample(ctx, k=n_context) if x]
    head, tail = _frame(fam, rng, slots)
    body = context + [_fill(need, slots)]
    if fam.mode == "form":
        label = "Message" if fam.lang == "en" else "نص الطلب"
        body = [f"{label}: " + " ".join(body)]
    return Rendered(sentences=body, head=head, tail=tail, facts=[], joiner=_join_mode(fam))


# --- faq -----------------------------------------------------------------------------------------------


def render_faq(
    key: str, variant: int | None, fam: Family, p: dict[str, Any], rng: random.Random, pn: str, n_context: int
) -> Rendered:
    data = _lang_data(fam)
    bank = data.FAQ if fam.lang == "en" else data.FAQ[fam.register]
    ctx = data.FAQ_CONTEXT if fam.lang == "en" else data.FAQ_CONTEXT[fam.register]
    slots = base_slots(fam, p) | {"pn": pn}
    options = bank[key]
    q = options[2] if fam.held_back else options[variant if variant is not None else rng.randrange(2)]
    context = [_fill(x, slots) for x in rng.sample(ctx, k=n_context) if x]
    head, tail = _frame(fam, rng, slots)
    body = context + [q]
    if fam.mode == "form":
        label = "Question" if fam.lang == "en" else "السؤال"
        body = [f"{label}: " + " ".join(body)]
    return Rendered(sentences=body, head=head, tail=tail, facts=[], joiner=_join_mode(fam), movable=False)


def render_plain(text: str, fam: Family, rng: random.Random, p: dict[str, Any], framed: bool) -> Rendered:
    """Adversarial non-insurance / garbled messages."""
    head, tail = _frame(fam, rng, base_slots(fam, p)) if framed else ([], [])
    return Rendered(sentences=[text], head=head, tail=tail, joiner=_join_mode(fam), movable=False)
