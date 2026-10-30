"""O1 cascade (D3.2): hand-computable synthetic cases, plus the committed dev result pinned (slow)."""

from __future__ import annotations

import pytest

from engine.eval.baselines import index_cells
from engine.eval.cells import Cell
from engine.eval.data import load_split
from engine.eval.floors import Floors, TaskFloor
from engine.llm.pricing import ROOT
from engine.policy.cascade import O1Options, adjudicate, agree

COST = {"haiku-low": 0.001, "haiku-medium": 0.002, "opus-low": 0.04}
BUDGET_S = 8.5


def ticket():
    return next(t for t in load_split("dev") if t.task_type == "adjudicate")


def floors() -> Floors:
    return Floors(
        per_task={
            t: TaskFloor(
                task=t,
                n=1,
                best_config="opus-low",
                best_accuracy=1.0,
                tolerance=0.01,
                floor=0.99,
                budget_config="opus-low",
                p95_s=BUDGET_S,
                budget_s=BUDGET_S,
                tied_best=(),
            )
            for t in ("faq", "intent", "extract", "adjudicate")
        }
    )


def cell(t, cfg, *, latency_s, correct=True, failed=(), decision="partial", payout=1000.0) -> Cell:
    return Cell(
        ticket_id=t.id, task=t.task_type, level=t.level, language=t.language, config_id=cfg,
        model=cfg.split("-")[0], effort=cfg.split("-")[1], correct=correct, fields={},
        parsed_ok="V0" not in failed, verified=not failed, failed_checks=tuple(failed), truncated=False,
        cost_usd=COST[cfg] / 4, cost_usd_nocache=COST[cfg], latency_ms=latency_s * 1000, queue_wait_ms=0.0,
        input_tokens=1, cache_creation_tokens=0, cache_read_tokens=0, output_tokens=1, thinking_tokens=None,
        stop_reason="end_turn", replayed=True, decision=decision, payout_sar=payout,
    )  # fmt: skip


def run(a, b, top, o: O1Options | None = None):
    t = ticket()
    return adjudicate(t, index_cells([a, b, top]), floors(), o or O1Options())


def test_agreement_accepts_first_and_charges_both_parallel_calls():
    t = ticket()
    out, tr = run(
        cell(t, "haiku-low", latency_s=4),
        cell(t, "haiku-medium", latency_s=5),
        cell(t, "opus-low", latency_s=2),
    )
    assert not tr.escalated and out.path == ("haiku-low", "haiku-medium")
    assert out.latency_ms == 5000  # the slower of the two parallel calls
    assert out.cost_nocache == pytest.approx(0.003)


def test_disagreement_escalates_after_the_slower_call():
    t = ticket()
    b = cell(t, "haiku-medium", latency_s=5, payout=1002.0)  # payout differs by more than 1 SAR
    out, tr = run(cell(t, "haiku-low", latency_s=4), b, cell(t, "opus-low", latency_s=2, correct=False))
    assert tr.escalated and tr.reason == "disagree"
    assert (
        out.latency_ms == 7000 and out.path[-1] == "opus-low" and not out.correct
    )  # the top answer is final
    assert out.cost_nocache == pytest.approx(0.043)


def test_payout_within_one_sar_agrees():
    t = ticket()
    assert agree(cell(t, "haiku-low", latency_s=1), cell(t, "haiku-medium", latency_s=1, payout=1001.0))
    assert not agree(
        cell(t, "haiku-low", latency_s=1), cell(t, "haiku-medium", latency_s=1, decision="approve")
    )


def test_late_second_opinion_falls_back_to_v0_v2_and_is_still_charged():
    t = ticket()
    a, b = cell(t, "haiku-low", latency_s=3), cell(t, "haiku-medium", latency_s=9, decision="deny")
    out, tr = run(a, b, cell(t, "opus-low", latency_s=2))
    assert tr.second_late and not tr.escalated
    assert out.latency_ms == 6000  # decided at the 6.0 s deadline
    assert out.cost_nocache == pytest.approx(0.003)  # the late call is charged in full
    out, tr = run(cell(t, "haiku-low", latency_s=3, failed=("V2",)), b, cell(t, "opus-low", latency_s=2))
    assert tr.escalated and tr.reason == "first failed (second late)" and out.latency_ms == 8000


def test_deadline_never_cuts_the_first_answer_short():
    """haiku-medium after the deadline but before haiku-low finishes: it is in hand, so it is used."""
    t = ticket()
    a, b = cell(t, "haiku-low", latency_s=7.5), cell(t, "haiku-medium", latency_s=7, decision="deny")
    out, tr = run(a, b, cell(t, "opus-low", latency_s=1))
    assert not tr.second_late and tr.escalated and tr.reason == "disagree"
    assert out.latency_ms == 8500


def test_no_deadline_waits_for_the_second_opinion():
    t = ticket()
    a, b = cell(t, "haiku-low", latency_s=3), cell(t, "haiku-medium", latency_s=9)
    out, tr = run(a, b, cell(t, "opus-low", latency_s=1), O1Options(deadline_s=None))
    assert not tr.second_late and out.latency_ms == 9000 and not out.success  # over the 8.5 s budget


def test_ablations_drop_v3_and_drop_v2():
    t = ticket()
    a = cell(t, "haiku-low", latency_s=3, failed=("V2",))
    b, top = cell(t, "haiku-medium", latency_s=4), cell(t, "opus-low", latency_s=2)
    out, tr = run(a, b, top, O1Options(second=None))
    assert tr.escalated and out.path == ("haiku-low", "opus-low") and out.latency_ms == 5000
    out, tr = run(a, b, top, O1Options(checks=("V0", "V1")))  # V2 failure ignored; the two agree
    assert not tr.escalated


@pytest.mark.slow
@pytest.mark.skipif(not (ROOT / "runs" / "matrix-dev-full-1").exists(), reason="dev matrix not recorded")
def test_o1_on_the_committed_dev_matrix():
    """Pinned O1 result on dev (reports/phase3/o1.txt): 178/180 adjudicate correct, every floor met."""
    from engine.eval.phase3_report import Context, _meets

    ctx = Context("matrix-dev-full-1")
    outs, traces = ctx.o1()
    adj = [o for o in outs if o.task == "adjudicate"]
    assert sum(o.correct for o in adj) == 178 and len(adj) == 180
    assert sum(o.success for o in adj) == 170
    assert sum(t.escalated for t in traces) == 11
    assert _meets(outs, ctx.floors)
    no_deadline, _ = ctx.o1(O1Options(deadline_s=None))
    assert sum(o.correct for o in no_deadline if o.task == "adjudicate") == 178
    # ablations (reports/phase3/ablations.txt): V3 and V2 are each needed for the adjudicate floor
    for opts, correct in ((O1Options(second=None), 176), (O1Options(checks=("V0", "V1")), 177)):
        outs, _ = ctx.o1(opts)
        assert sum(o.correct for o in outs if o.task == "adjudicate") == correct
        assert not _meets(outs, ctx.floors)
