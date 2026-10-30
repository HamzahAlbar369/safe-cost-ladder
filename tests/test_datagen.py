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
    r = R.render_claim(
        R.ClaimView(case=d.case, lexp=d.view["lexp"]), R.BY_ID["en_email"], R.people(rng), rng, "adjudicate"
    )
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
