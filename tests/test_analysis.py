"""Floors, baselines, oracle, ladder and bootstrap on small synthetic cells (hand-computable)."""

from __future__ import annotations

import pytest

from engine.eval import bootstrap as B
from engine.eval.analysis import analyse, pareto_ladder
from engine.eval.baselines import baselines, best_config, index_cells, oracle, run_policy, summarize
from engine.eval.cells import Cell
from engine.eval.data import load_split
from engine.eval.floors import derive_floors, round_up_half_second

CONFIGS = ("haiku-low", "sonnet-low", "opus-high")
COST = {"haiku-low": 0.01, "sonnet-low": 0.10, "opus-high": 0.40}  # headline cost per call


def tickets():
    dev = load_split("dev")
    return [
        next(t for t in dev if t.task_type == task and t.language == lang)
        for task in ("faq", "intent", "extract", "adjudicate")
        for lang in ("en", "ar")
    ]


def cell(t, cfg, *, correct=True, parsed=True, latency=1000.0):
    return Cell(
        ticket_id=t.id,
        task=t.task_type,
        level=t.level,
        language=t.language,
        config_id=cfg,
        model=cfg.split("-")[0],
        effort=cfg.split("-")[1],
        correct=correct,
        fields={},
        parsed_ok=parsed,
        verified=parsed,
        truncated=False,
        cost_usd=COST[cfg] / 2,
        cost_usd_nocache=COST[cfg],
        latency_ms=latency,
        queue_wait_ms=0.0,
        input_tokens=1,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        output_tokens=1,
        thinking_tokens=None,
        stop_reason="end_turn",
        replayed=False,
    )


def all_cells(rule):
    return [cell(t, cfg, **rule(t, cfg)) for t in tickets() for cfg in CONFIGS]


def haiku_fails_adjudicate(t, cfg):
    return {"correct": not (cfg == "haiku-low" and t.task_type == "adjudicate")}


def test_round_up_half_second():
    assert [round_up_half_second(x) for x in (0.2, 6.0, 6.01, 6.5, 6.51)] == [0.5, 6.0, 6.5, 6.5, 7.0]


def test_floor_uses_best_config_with_cost_tiebreak_and_tolerance():
    f = derive_floors(all_cells(lambda t, c: {}))
    for task, tf in f.per_task.items():
        assert tf.best_config == "haiku-low" and tf.best_accuracy == 1.0  # ties -> cheapest
        assert tf.floor == pytest.approx(1.0 - {"adjudicate": 0.01}.get(task, 0.02))
        assert tf.budget_s == 1.0 and {s.config for s in tf.tied_best} == set(CONFIGS)


def test_baselines_and_oracle_by_hand():
    cells = all_cells(haiku_fails_adjudicate)
    floors = derive_floors(cells)
    index, ts = index_cells(cells), tickets()
    assert (
        floors.per_task["adjudicate"].best_config == "sonnet-low"
    )  # haiku wrong, ties sonnet/opus -> cheaper
    chosen = baselines(index, floors)
    names = {n.split(":")[0]: n for n in chosen}
    assert best_config(index) == "sonnet-low"
    b2 = summarize(run_policy(chosen[names["B2"]], ts, index, floors))
    assert b2["accuracy"] == pytest.approx(6 / 8) and b2["usd_nocache"] == pytest.approx(0.08)
    b5 = run_policy(chosen[names["B5"]], ts, index, floors)  # haiku parses fine, so it never escalates
    assert all(o.path == ("haiku-low",) for o in b5)
    b3 = run_policy(chosen[names["B3"]], ts, index, floors)
    assert {o.path[0] for o in b3 if o.task == "adjudicate"} == {"sonnet-low"}
    assert {o.path[0] for o in b3 if o.task == "faq"} == {"haiku-low"}
    orc = summarize(run_policy(oracle(index, floors), ts, index, floors))
    assert orc["success_rate"] == 1.0 and orc["usd_nocache"] == pytest.approx(6 * 0.01 + 2 * 0.10)


def test_cascade_escalates_only_on_v0_failure_and_sums_cost_and_latency():
    cells = [
        cell(t, cfg, parsed=not (cfg == "haiku-low" and t.language == "ar"), correct=cfg != "haiku-low")
        for t in tickets()
        for cfg in CONFIGS
    ]
    floors = derive_floors(cells)
    index, ts = index_cells(cells), tickets()
    b5 = next(c for n, c in baselines(index, floors).items() if n.startswith("B5"))
    outs = {o.ticket_id: o for o in run_policy(b5, ts, index, floors)}
    ar = next(t for t in ts if t.language == "ar")
    en = next(t for t in ts if t.language == "en")
    assert outs[ar.id].path == ("haiku-low", "sonnet-low") and outs[ar.id].cost_nocache == pytest.approx(0.11)
    assert outs[ar.id].latency_ms == 2000.0 and outs[ar.id].correct
    assert outs[en.id].path == ("haiku-low",) and not outs[en.id].correct  # parsed but wrong: no escalation


def test_success_needs_latency_within_budget():
    cells = [
        cell(t, cfg, latency=1000.0 if cfg != "opus-high" else 9000.0) for t in tickets() for cfg in CONFIGS
    ]
    floors = derive_floors(cells)  # best = haiku-low (cheapest of the ties) -> budget 1.0 s
    index, ts = index_cells(cells), tickets()
    slow = run_policy(lambda t: ("opus-high",), ts, index, floors)
    assert all(o.correct and not o.success for o in slow)
    assert summarize(slow)["cpst_nocache"] == float("inf")


def test_pareto_ladder_removes_dominated_configs():
    cells = [cell(t, cfg, correct=cfg != "haiku-low") for t in tickets() for cfg in CONFIGS]
    ladder, dropped = pareto_ladder(cells, "faq")
    assert [r.config for r in ladder] == ["haiku-low", "sonnet-low"] or [r.config for r in ladder] == [
        "sonnet-low"
    ]
    assert "opus-high" in dropped  # same accuracy as sonnet-low at 4x the cost


def test_analysis_runs_end_to_end_and_oracle_is_cheapest_per_success():
    cells = all_cells(haiku_fails_adjudicate)
    a = analyse(cells, tickets(), derive_floors(cells))
    by = {r.name.split(":")[0]: r for r in a.rows}
    # CPST alone can favour a cheap policy that fails the hard tickets, so the oracle is the best on success
    assert by["Oracle"].summary["success_rate"] == max(r.summary["success_rate"] for r in a.rows)
    assert by["Oracle"].meets_floors and not by["B2"].meets_floors  # haiku-low is wrong on adjudicate here
    assert by["Oracle"].summary["cpst_nocache"] <= by["B1"].summary["cpst_nocache"]
    assert 0 <= (by["B1"].gap_captured or 0) <= 1 and a.headroom["go"] in (True, False)
    lo, hi = by["B1"].cpst_nocache_ci
    assert lo <= by["B1"].summary["cpst_nocache"] <= hi


def test_bootstrap_is_seeded_paired_and_exact_on_constant_data():
    s1, s2 = B.resample_indices(10), B.resample_indices(10)
    assert s1 == s2 and len(s1) == B.RESAMPLES
    cost, win = [2.0] * 10, [1.0] * 10
    assert B.cpst_ci(cost, win, s1) == (2.0, 2.0)
    assert B.paired_diff_ci((cost, win), ([1.0] * 10, win), s1) == (1.0, 1.0)
    assert B.paired_diff_ci((cost, win), ([1.0] * 10, win), s1, relative=True) == (0.5, 0.5)


def test_premium_budget_rule_uses_the_most_expensive_tied_config():
    cells = [
        cell(t, cfg, latency={"haiku-low": 1000.0, "sonnet-low": 2000.0, "opus-high": 4000.0}[cfg])
        for t in tickets()
        for cfg in CONFIGS
    ]
    cheapest = derive_floors(cells, "cheapest").per_task["faq"]
    premium = derive_floors(cells, "premium").per_task["faq"]
    assert (cheapest.budget_config, cheapest.budget_s) == ("haiku-low", 1.0)
    assert (premium.budget_config, premium.budget_s) == ("opus-high", 4.0)
    assert cheapest.floor == premium.floor and cheapest.best_config == premium.best_config
    index, ts = index_cells(cells), tickets()
    strict = run_policy(lambda t: ("opus-high",), ts, index, derive_floors(cells, "cheapest"))
    relaxed = run_policy(lambda t: ("opus-high",), ts, index, derive_floors(cells, "premium"))
    assert not any(o.success for o in strict) and all(o.success for o in relaxed)


def test_policy_yaml_records_status_and_budget_rule(tmp_path):
    import yaml

    from engine.eval.floors import write_policy_yaml

    floors = derive_floors(all_cells(lambda t, c: {}), "premium")
    path = tmp_path / "policy.yaml"
    write_policy_yaml(floors, ["r"], "sha", path, budget_rule="premium", frozen=True)
    doc = yaml.safe_load(path.read_text("utf-8"))
    assert doc["status"] == "frozen" and doc["budget_rule"] == "premium"
    assert doc["latency_budget_config"]["faq"] == "opus-high"
    write_policy_yaml(floors, ["r"], "sha", path)
    assert yaml.safe_load(path.read_text("utf-8"))["status"] == "proposed"
