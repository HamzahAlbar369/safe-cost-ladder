"""Request builder, sealed-split guard, probe plan and estimator (no network)."""

import pytest

from engine.eval.data import SealedSplit, load_split
from engine.eval.estimate import estimate_requests
from engine.eval.probe import PROBE_EFFORTS, probe_requests, probe_tickets
from engine.llm.client import LLMClient, request_hash
from engine.tasks.request import build_request, configs


def test_heldout_cannot_be_loaded_outside_engine_final():
    with pytest.raises(SealedSplit):
        load_split("heldout")
    assert len(load_split("dev")) == 400


def test_nine_configs_in_order():
    ids = [c[2] for c in configs()]
    assert ids == [f"{m}-{e}" for m in ("haiku", "sonnet", "opus") for e in ("low", "medium", "high")]


def test_request_is_structured_adaptive_and_shares_one_system_prefix():
    t = load_split("dev")
    a = build_request(t[0], "claude-opus-5-5", "low")
    b = build_request(next(x for x in t if x.task_type == "adjudicate"), "claude-opus-5-5", "high")
    assert a.system == b.system  # one cached prefix across tasks and efforts
    assert a.thinking == "adaptive" and a.output_schema is not None and a.cache
    params = LLMClient.build_params(b)
    assert params["output_config"]["effort"] == "high"
    assert params["output_config"]["format"]["type"] == "json_schema"
    assert params["thinking"] == {"type": "adaptive"}
    assert request_hash(a) != request_hash(b)


def test_probe_plan_covers_all_schemas_models_and_two_efforts():
    plan = probe_requests()
    assert len(plan) == 4 * 3 * len(PROBE_EFFORTS) == 24
    assert {t.task_type for t in probe_tickets()} == {"faq", "intent", "extract", "adjudicate"}
    assert {t.language for t in probe_tickets()} == {"en", "ar"}


def test_estimate_orders_cached_below_uncached_below_worst():
    reqs = [(t.task_type, build_request(t, m, e)) for t, m, e in probe_requests()]
    e = estimate_requests(reqs, concurrency=3)
    assert 0 < e.cost_with_caching < e.cost_without_caching < e.worst_case
    assert e.calls == 24
