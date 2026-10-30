"""Data generation: normaliser, variation layer, sampler designs, QA checks (SPEC §4.2, §4.4). FICTIONAL."""

from __future__ import annotations

import random

import pytest

from engine.contracts import IntentGold, Ticket, TicketMeta
from engine.datagen import gen as G
from engine.datagen import qa, sampler
from engine.datagen import variation as var
from engine.datagen.normalize import normalise
from engine.datagen.rules import load_version
from engine.datagen.rules_engine import adjudicate
from engine.datagen.templates import render as R

V1, V2 = load_version("v1"), load_version("v2")


# --- normaliser ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("On 10 March 2026", "on 2026-03-10"),
        ("10/03/2026", "2026-03-10"),
        ("10-03-2026", "2026-03-10"),
        ("2026/03/10", "2026-03-10"),
        ("في ١٠ مارس ٢٠٢٦", "في 2026-03-10"),
        ("SAR 20,000", "sar 20000"),
        ("٢٠٬٠٠٠ ريال", "20000 ريال"),
        ("cap 10,000,000", "cap 10000000"),
        ("٧٥٪", "75%"),
        ("  Policy   OMI-1234567 ", "policy omi-1234567"),
        ("31/02/2026", "31/02/2026"),  # invalid dates are left alone
    ],
)
def test_normalise(raw, expected):
    assert normalise(raw) == expected


# --- sampler: every design's expectation agrees with the rules engine ----------------------------------


@pytest.mark.parametrize("rules", [V1, V2], ids=["v1", "v2"])
@pytest.mark.parametrize("level", ["L3", "L4", "L5"])
def test_every_design_matches_the_engine_over_many_draws(rules, level):
    rng = random.Random(f"designs:{level}:{rules.version}")
    for builder, _ in sampler.DESIGNS[level]:
        for _ in range(40):
            d = builder(rng, rules)
            got = adjudicate(d.case, rules).gold.decision
            assert got == d.expected, f"{d.design}: expected {d.expected}, engine {got}"


def test_faq_answers_follow_the_rules_version():
    assert sampler.faq_answer("fixed_deductible", V1) == 1000
    assert sampler.faq_answer("fixed_deductible", V2) == 1500
    assert sampler.faq_answer("deductible_at_25", V2) == 375
    assert sampler.faq_answer("etl_pct", V2) == 50
    assert sampler.faq_answer("reporting_window_days", V2) == 10
    assert sampler.faq_answer("tpl_cap_sar", V1) == 10_000_000
    assert sampler.faq_answer("od_licence_grace_business_days", V1) == 50
    assert sampler.faq_answer("required_documents_count", V1) == 5
    for key in sampler.FAQ_KEYS:
        sampler.faq_answer(key, V1)  # every key resolves


@pytest.mark.parametrize("split", G.SPLITS)
def test_plan_hits_composition_exactly(split):
    slots = G.plan(split, random.Random(0))
    assert len(slots) == G.SIZES[split]
    for task, level, share in G.CELLS:
        cell = [s for s in slots if (s.task, s.level) == (task, level)]
        assert len(cell) == round(G.SIZES[split] * share)
        assert sum(s.language == "ar" for s in cell) == round(len(cell) * G.AR_SHARE)
    if split == "dev":
        assert len({s.pair_id for s in slots if s.pair_id}) == G.DEV_PAIRS
    if split == "shifted":
        assert sum(s.adversarial is not None for s in slots) == 20
        assert sum(s.rules_version == "v2" for s in slots) == 40


# --- rendering + variation -----------------------------------------------------------------------------


def _draft(seed: int):
    rng = random.Random(seed)
    return sampler.sample_adjudication(rng, V1, rng.choice(["L3", "L4", "L5"])), rng


@pytest.mark.parametrize("fam", R.FAMILIES, ids=lambda f: f.id)
def test_every_family_renders_and_variation_preserves_facts(fam):
    for seed in range(25):
        draft, rng = _draft(seed)
        p = R.people(rng)
        view = R.ClaimView(case=draft.case, distractors=(0, 3), injection=seed % 7 == 0)
        r = R.render_claim(view, fam, p, rng, "adjudicate")
        text = var.apply(r, fam, rng, var.HEAVY)
        norm = normalise(text)
        missing = [f for f in r.facts if normalise(f) not in norm]
        assert not missing, (fam.id, missing)
        assert "{" not in text and "}" not in text  # every placeholder filled


def test_variation_is_deterministic():
    draft, _ = _draft(3)
    fam = R.BY_ID["en_voice"]
    outs = set()
    for _ in range(2):
        rng = random.Random(99)
        r = R.render_claim(R.ClaimView(case=draft.case), fam, R.people(rng), rng, "adjudicate")
        outs.add(var.apply(r, fam, rng, var.HEAVY))
    assert len(outs) == 1


def test_codeswitch_never_lands_inside_a_form_field():
    fam = R.BY_ID["en_form"]
    for seed in range(60):
        draft, rng = _draft(seed)
        r = R.render_claim(R.ClaimView(case=draft.case), fam, R.people(rng), rng, "adjudicate")
        text = var.apply(r, fam, rng, var.Intensity(typo=0, filler=0, reorder=0, codeswitch=1.0))
        fields = [ln for ln in text.splitlines() if ": " in ln and not ln.startswith("Description")]
        assert not any(w in ln for ln in fields for w in R.EN.CODESWITCH_APPEND), text


def test_held_back_families_are_only_used_by_shifted():
    assert all(not f.held_back for f in R.families("en", False) + R.families("ar", False))
    assert {f.id for f in R.FAMILIES if f.held_back} == {
        "en_voice",
        "en_broker",
        "ar_sa_heavy",
        "ar_mixed_agent",
    }
    for lang in ("en", "ar"):
        assert len(R.families(lang, False)) >= 6 and len(R.families(lang, True)) >= 2


def test_timeline_uses_past_tense_when_licence_renewed_after_filing():
    rng = random.Random(5)
    d = sampler.tp_licence_grace(rng, V1)
    while d.case.licence_renewal_date <= d.case.report_date:
        d = sampler.tp_licence_grace(rng, V1)
    r = R.render_claim(R.ClaimView(case=d.case), R.BY_ID["en_email"], R.people(rng), rng, "adjudicate")
    assert any(s in " ".join(r.sentences) for s in ("first reported", "was filed"))


# --- QA checks catch what they should ------------------------------------------------------------------


def _ticket(i: int, split: str, text: str, family: str = "en_email", label: str = "other") -> Ticket:
    return Ticket(
        id=f"{split}-{i}",
        split=split,
        task_type="intent",
        level="L2",
        language="en",
        dialect="none",
        template_family=family,
        rules_version="v1",
        text=text,
        gold=IntentGold(intent=label),
        meta=TicketMeta(),
    )


def test_qa_detects_cross_split_exact_and_near_duplicates():
    a = "Please find attached the damage photos for my existing claim CLM-12345, thanks a lot."
    b = "Please find attached the damage photos for my existing claim CLM-12346, thanks a lot."
    exact, near = qa.duplicates({"dev": [_ticket(1, "dev", a)], "heldout": [_ticket(1, "heldout", a)]})
    assert exact["value"] == 1 and not exact["pass"]
    exact, near = qa.duplicates({"dev": [_ticket(1, "dev", a)], "heldout": [_ticket(1, "heldout", b)]})
    assert exact["pass"] and near["value"] == 1 and not near["pass"]


def test_qa_template_leak_flags_a_family_that_predicts_the_label():
    labels = ["new_claim", "complaint", "other"]
    tickets = [_ticket(i, "dev", f"t{i}", family=f"fam{i % 3}", label=labels[i % 3]) for i in range(60)]
    assert not qa.template_leak({"dev": tickets})["pass"]
    mixed = [_ticket(i, "dev", f"t{i}", family=f"fam{i % 3}", label=labels[(i // 3) % 3]) for i in range(60)]
    assert qa.template_leak({"dev": mixed})["pass"]


def test_blocking_failures_ignore_label_flags():
    report = {"a": {"pass": True}, "decision_distribution": {"pass": False}, "_table": {}}
    assert qa.blocking_failures(report) == []
    report["b"] = {"pass": False}
    assert qa.blocking_failures(report) == ["b"]


# --- D1.10 template rules ------------------------------------------------------------------------------


def _banks():
    from engine.datagen.templates import bank_ar, bank_en

    return {"en": bank_en.FAQ, "msa": bank_ar.FAQ["msa"], "saudi": bank_ar.FAQ["saudi"]}


@pytest.mark.parametrize("register", ["en", "msa", "saudi"])
def test_every_licence_grace_faq_names_the_cover_type(register):
    faq = _banks()[register]
    tpl_words, comp_words = ("TPL", "third-party", "ضد الغير"), ("comprehensive", "الشامل", "بالشامل")
    for q in faq["tp_licence_grace_days"]:
        assert any(w.lower() in q.lower() for w in tpl_words), q
    for q in faq["od_licence_grace_business_days"]:
        assert any(w.lower() in q.lower() for w in comp_words), q


def test_no_template_has_the_customer_claiming_from_the_other_partys_insurer():
    import inspect

    from engine.datagen.templates import bank_ar, bank_en

    text = inspect.getsource(bank_en) + inspect.getsource(bank_ar)
    for pat in qa.OTHER_INSURER_PATTERNS:
        assert not pat.search(text), pat.pattern


def test_damage_amounts_are_attributed_to_the_assessment_or_a_garage_quote():
    from engine.datagen.templates import bank_ar, bank_en

    for bank in (bank_en.S, bank_ar.MSA, bank_ar.SAUDI):
        for key in ("damage_od", "damage_tp", "conflict"):
            assert all(
                any(w in v.lower() for w in ("assess", "taqdeer", "تقييم", "تقدير")) for v in bank[key]
            ), key
        assert all(any(w in v.lower() for w in ("garage", "workshop", "ورشة")) for v in bank["garage_quote"])


def test_designs_without_an_assessment_state_a_garage_quote():
    rng = random.Random(7)
    for builder, _ in sampler.DESIGNS["L5"]:
        for _ in range(30):
            d = builder(rng, V1)
            if "damage_assessment" not in d.case.documents:
                assert d.case.damage_source == "garage_quote", d.design


def test_arabic_codeswitch_swaps_whole_words_only():
    rng = random.Random(0)
    s = "أنا مؤمَّن لديكم بالوثيقة رقم 1، ووصلني تقريرا تقييم، وهذه الوثيقة معي."
    for _ in range(50):
        out = var._swap_whole_words(s, rng)
        assert "بالوثيقة" in out and "تقريرا" in out
        assert all(
            not (any(c.isascii() and c.isalpha() for c in w) and any(not c.isascii() for c in w))
            or w.strip(".,،").startswith("ال")
            for w in out.split(" ")
        )


# --- D1.11 --------------------------------------------------------------------------------------------


def test_fact_consistency_flags_two_fault_shares_or_a_foreign_amount():
    draft, rng = _draft(11)
    while draft.case.conflict_damage_sar is not None or draft.case.damage_amount_sar is None:
        draft, rng = _draft(rng.randrange(10_000))
    meta = TicketMeta(case=draft.case)
    base = dict(
        id="dev-1",
        split="dev",
        task_type="adjudicate",
        level="L3",
        language="en",
        dialect="none",
        template_family="en_email",
        rules_version="v1",
        meta=meta,
        gold=adjudicate(draft.case, V1).gold,
    )
    acc = draft.case.accident_date.isoformat()
    ok = Ticket(**base, text=f"On {acc} it happened. SAR {draft.case.damage_amount_sar:,}. Fault 50%.")
    assert qa.fact_conflicts(ok) == []
    two_faults = Ticket(**base, text=f"On {acc}. Najm gave me 50% but later 75%.")
    assert any("fault shares" in p for p in qa.fact_conflicts(two_faults))
    foreign = Ticket(
        **base, text=f"On {acc}. The repairs are SAR 123,400 and SAR {draft.case.damage_amount_sar}."
    )
    assert any("amounts" in p for p in qa.fact_conflicts(foreign))
    two_policies = Ticket(**base, text=f"On {acc}. Policy OMI-1234567, or maybe OMI-7654321.")
    assert any("policy numbers" in p for p in qa.fact_conflicts(two_policies))


def test_third_party_tickets_name_the_claimants_documents():
    rng = random.Random(3)
    d = sampler.tp_partial_fault(rng, V1)
    r = R.render_claim(R.ClaimView(case=d.case), R.BY_ID["en_email"], R.people(rng), rng, "adjudicate")
    text = " ".join(r.sentences)
    assert "at-fault driver" in text and ("claimant" in text or "other car" in text)
    d = sampler.od_comp_repair(rng, V1)
    r = R.render_claim(R.ClaimView(case=d.case), R.BY_ID["en_email"], R.people(rng), rng, "adjudicate")
    assert "at-fault driver" not in " ".join(r.sentences)


def test_policy_documents_have_no_unresolved_placeholders():
    assert qa.policy_documents()["pass"]


@pytest.mark.slow
def test_wording_change_stays_local_to_the_items_that_use_it(monkeypatch):
    """Per-slot RNG streams (D1.11): swapping the third-party document wording changes only third-party claim
    texts; no gold label, id or other item moves."""
    from engine.datagen.templates import bank_ar, bank_en

    a = G.generate()
    monkeypatch.setattr(bank_en, "DOC_TP", bank_en.DOC)
    monkeypatch.setattr(bank_ar, "DOC_TP", {"msa": bank_ar.DOC["msa"], "saudi": bank_ar.DOC["saudi"]})
    b = G.generate()
    for split in G.SPLITS:
        assert [t.id for t in a[split]] == [t.id for t in b[split]]
        assert all(x.gold == y.gold for x, y in zip(a[split], b[split], strict=True))
        changed = [x for x, y in zip(a[split], b[split], strict=True) if x.text != y.text]
        assert changed and all(x.meta.case and x.meta.case.claim_type == "third_party_claim" for x in changed)


# --- D1.12 text-defect scans -------------------------------------------------------------------------


def test_numeric_dates_never_ambiguous():
    from datetime import date

    for fam in R.FAMILIES:
        early, late = R.fmt_date(date(2026, 3, 5), fam), R.fmt_date(date(2026, 3, 15), fam)
        assert not qa.ambiguous_dates(early) and not qa.ambiguous_dates(late), fam.id
        assert normalise(early) == "2026-03-05" and normalise(late) == "2026-03-15", fam.id
    assert qa.ambiguous_dates("on 05/03/2026") == ["05/03/2026"]
    assert qa.ambiguous_dates("on 2026-03-05") == ["2026-03-05"]
    assert not qa.ambiguous_dates("on 15/03/2026 and 2026-03-15")


def test_ticket_dates_never_after_the_ticket_date():
    rng = random.Random(4)
    for _ in range(200):
        d = sampler.tp_licence_grace(rng, V1)
        c = d.case
        if c.licence_renewal_date > c.report_date:
            assert c.submitted_on is not None and c.submitted_on >= c.licence_renewal_date
        else:
            assert c.submitted_on is None


def test_hit_and_run_tickets_never_describe_the_other_driver():
    rng = random.Random(9)
    for fam in R.FAMILIES:
        d = sampler.od_comp_hit_and_run(rng, V1)
        r = R.render_claim(
            R.ClaimView(case=d.case, distractors=tuple(range(8))), fam, R.people(rng), rng, "adjudicate"
        )
        assert not any(line in s for s in r.sentences for line in R.OTHER_DRIVER_LINES), fam.id


def test_signer_gender_scan_and_closing():
    def t(text):
        return Ticket(
            id="dev-1",
            split="dev",
            task_type="intent",
            level="L2",
            language="ar",
            dialect="msa",
            template_family="ar_msa_letter",
            rules_version="v1",
            text=text,
            gold=IntentGold(intent="other"),
            meta=TicketMeta(),
        )

    assert qa.signer_gender_mismatch(t("نص\nشاكرًا لكم،\nنورة"))
    assert not qa.signer_gender_mismatch(t("نص\nشاكرةً لكم،\nنورة"))
    assert not qa.signer_gender_mismatch(t("نص\nشاكرًا لكم،\nفيصل"))
    assert qa.signer_gender_mismatch(t("نص\nشاكرةً لكم،\nفيصل"))


def test_arabic_english_spacing_scan():
    assert qa.mangled_tokens("رفعت الclaim اليوم") and qa.mangled_tokens("وصلني reportا")
    assert not qa.mangled_tokens("رفعت claim اليوم (Taqdeer) و OMI-1234567")


def test_english_prose_has_no_wallah_yalla_or_you_know():
    from engine.datagen.templates import bank_en

    words = " ".join(bank_en.FILLER + bank_en.CODESWITCH_APPEND).lower()
    assert not any(w in words for w in ("wallah", "yalla", "you know"))


def test_parallel_pairs_spanning_splits_are_detected():
    a = _ticket(1, "dev", "x").model_copy(update={"parallel_pair_id": "pair-x"})
    b = _ticket(2, "heldout", "y").model_copy(update={"parallel_pair_id": "pair-x"})
    assert qa.text_defects({"dev": [a], "heldout": [b]})["value"]["parallel_pairs_spanning_splits"] == 1
