"""Audit-and-recalibrate (D4.6): replay only; frozen floors; the controller selection rules on the sample."""

from __future__ import annotations

import random
from collections import Counter

import pytest

from engine.eval import recalibrate as R
from engine.eval.baselines import index_cells
from engine.eval.data import load_split
from engine.policy.cascade import O1Options
from engine.policy.frozen import FrozenChoices
from tests.test_o1 import cell, floors


def test_binomial_drift_matches_hand_computed_tails():
    # P(X <= 23 | n=25, p=0.98) = 1 - P(24) - P(25) = 0.0886 -> not significant at 0.05
    assert not R.binomial_drift(23, 25, 0.98)
    # P(X <= 22 | 25, 0.98) = 0.0132 -> fires
    assert R.binomial_drift(22, 25, 0.98)
    assert not R.binomial_drift(25, 25, 0.98) and not R.binomial_drift(0, 0, 0.98)


def test_folds_are_a_stratified_partition():
    shifted = load_split("shifted")
    a, b = R.stratified_folds(shifted)
    assert {t.id for t in a}.isdisjoint({t.id for t in b}) and len(a) + len(b) == len(shifted)
    ca, cb = Counter((t.task_type, t.language) for t in a), Counter((t.task_type, t.language) for t in b)
    assert all(abs(ca[k] - cb[k]) <= 1 for k in ca | cb)
    assert R.stratified_folds(shifted) == [a, b]  # fixed seed


def test_stratified_sample_keeps_task_shares():
    shifted = load_split("shifted")
    s = R.stratified_sample(shifted, 40, random.Random(1))
    assert len(s) == 40 and Counter(t.task_type for t in s) == {
        "adjudicate": 18,
        "faq": 10,
        "intent": 6,
        "extract": 6,
    }


def _fc():
    return FrozenChoices(
        dev_run="x", floors=floors(), b1="opus-low", b4=None, o1=O1Options(),
        static={"faq": "haiku-low", "intent": "haiku-low", "extract": "haiku-low", "adjudicate": "opus-low"},
    )  # fmt: skip


def test_unreachable_floor_falls_back_to_most_accurate_and_drops_a_failing_cascade():
    t = next(x for x in load_split("dev") if x.task_type == "adjudicate")
    idx = index_cells(
        [
            cell(t, "haiku-low", latency_s=1, correct=False),
            cell(t, "haiku-medium", latency_s=1, correct=False),
            cell(t, "opus-low", latency_s=2, correct=False),
        ]
    )
    r = R.recalibrate(_fc(), [t], idx)
    assert r.drift["adjudicate"] and r.unreachable["adjudicate"]
    assert r.picks["adjudicate"] == "haiku-low"  # all tied at 0: the cheapest of the most accurate
    assert not r.cascade_kept and r.adapted.o1 is None


@pytest.mark.slow
def test_committed_recalibration_report_reproduces():
    from engine.llm.pricing import ROOT

    text = (ROOT / "reports" / "phase4" / "recalibration.txt").read_text(encoding="utf-8")
    assert R.report() in text and R.LABEL in text


def test_failsafe_reverts_only_alarmed_tasks_to_b1_and_selects_nothing_else():
    t = next(x for x in load_split("dev") if x.task_type == "adjudicate")
    idx = index_cells(
        [cell(t, c, latency_s=1, correct=False) for c in ("haiku-low", "haiku-medium", "opus-low")]
    )
    fc = _fc()
    r = R.recalibrate(fc, [t], idx).model_copy(
        update={"drift_binomial": {"faq": False, "intent": True, "extract": False, "adjudicate": True}}
    )
    a = R.failsafe(fc, r)
    assert a.static == {**fc.static, "intent": fc.b1, "adjudicate": fc.b1} and a.o1 is None
    calm = r.model_copy(update={"drift_binomial": dict.fromkeys(fc.static, False)})
    assert R.failsafe(fc, calm).static == fc.static and R.failsafe(fc, calm).o1 == fc.o1
