"""Phase 4: the frozen dev choices are applied unchanged to shifted (nothing re-derived on shifted)."""

from __future__ import annotations

import pytest

from engine.eval.baselines import index_cells
from engine.policy.cascade import O1Options
from engine.policy.frozen import FrozenChoices, frozen_baselines
from tests.test_o1 import cell, floors, ticket


def test_frozen_baselines_use_the_dev_configs_and_follow_v0_on_the_new_split():
    t = ticket()
    fc = FrozenChoices(
        dev_run="x",
        floors=floors(),
        static={"faq": "haiku-low", "intent": "haiku-low", "extract": "haiku-low", "adjudicate": "opus-low"},
        b1="opus-low",
        b4=None,
        o1=O1Options(),
    )
    ok = index_cells([cell(t, "haiku-low", latency_s=1), cell(t, "opus-low", latency_s=2)])
    bad = index_cells([cell(t, "haiku-low", latency_s=1, failed=("V0",)), cell(t, "opus-low", latency_s=2)])
    b = frozen_baselines(fc, ok)
    assert sorted(b) == [
        "B1: always-best (opus-low)",
        "B2: always-cheapest (haiku-low)",
        "B3: best static config per task (chosen on dev)",
        "B5: naive cascade (haiku-low -> B1 on V0 failure)",
    ]
    assert b["B1: always-best (opus-low)"](t) == ("opus-low",)
    assert b["B3: best static config per task (chosen on dev)"](t) == ("opus-low",)
    assert b["B5: naive cascade (haiku-low -> B1 on V0 failure)"](t) == ("haiku-low",)
    b5 = frozen_baselines(fc, bad)["B5: naive cascade (haiku-low -> B1 on V0 failure)"]
    assert b5(t) == ("haiku-low", "opus-low")


@pytest.mark.slow
def test_shifted_is_scored_with_the_frozen_dev_choices():
    from engine.eval.phase4_report import SHIFTED_RUN, SplitContext
    from engine.policy.controller import load_policy
    from engine.policy.frozen import frozen_choices

    fc = frozen_choices()
    assert fc.static == {
        "faq": "haiku-low",
        "intent": "haiku-high",
        "extract": "haiku-low",
        "adjudicate": "opus-low",
    }  # reports/phase3/o1.txt
    assert fc.b1 == "opus-low"
    policy = load_policy()
    assert {t: f.floor for t, f in fc.floors.per_task.items()} == policy.floors
    ctx = SplitContext(SHIFTED_RUN, "shifted", fc)
    assert ctx.floors is fc.floors and ctx.static is fc.static
    assert len(ctx.tickets) == 200 and len(ctx.cells) == 1800
