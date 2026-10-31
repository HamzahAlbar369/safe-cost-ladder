"""`engine ask`: the demo set is the declared pick, a dry run never calls the API, replay is honest,
and the estimate fits the $1 demo cap. No paid call is made here."""

from __future__ import annotations

import io

from rich.console import Console

from engine import ask as A
from engine.datagen.demo_tickets import PICKS, load
from engine.policy.cascade import O1Options
from engine.report import collect as C


def _console() -> Console:
    return Console(file=io.StringIO(), width=100)


def test_demo_tickets_are_the_declared_pick():
    tickets = load()
    assert [t.id for t in tickets] == [f"demo-{i:02d}" for i in range(1, 6)]
    for t, (_, task, lang, version) in zip(tickets, PICKS, strict=True):
        assert (t.task_type, t.language, t.rules_version) == (task, lang, version)


def test_dry_run_makes_no_call(monkeypatch):
    monkeypatch.setattr(A, "has_key", lambda: True)

    def boom(*a, **k):
        raise AssertionError("a dry run must not build a client")

    monkeypatch.setattr("engine.llm.client.LLMClient", boom)
    assert (
        A.run("demo-05", compare=True, rules=None, replay=False, yes=False, cap=1.0, console=_console()) == 0
    )


def test_replay_without_recording_says_so():
    con = _console()
    assert A.run("demo-04", compare=False, rules=None, replay=True, yes=False, cap=1.0, console=con) in (0, 1)


def test_worst_case_plan_fits_the_demo_cap():
    m = C.load()
    static = {k: m["o1_config"][k] for k in ("faq", "intent", "extract", "adjudicate")}
    for t in load():
        est = A.estimate(t, A.plan(t, O1Options(), static, m["o1_config"]["b1"], compare=True))
        assert est.cost_with_caching < A.DEMO_CAP_USD
