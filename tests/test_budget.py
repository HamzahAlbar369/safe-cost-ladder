"""Budget guard: per-provider ledger and per-run cap (CLAUDE.md money rule)."""

import pytest

from engine.contracts import LLMRequest, SpendEntry
from engine.llm.client import BudgetExceeded, Ledger, LLMClient, RunBudget, worst_case_cost
from engine.llm.pricing import load_pricebook
from tests.conftest import FakeAnthropic

REQ = LLMRequest(model="claude-opus-5-5", effort="high", system="S" * 4000, user="u", max_tokens=20000)


def test_ledger_tracks_providers_separately(tmp_ledger):
    tmp_ledger.record(SpendEntry(provider="anthropic", run_id="r", request_hash="h", model="m", cost_usd=1.5))
    tmp_ledger.record(
        SpendEntry(provider="openrouter", run_id="r", request_hash="h", model="j", cost_usd=0.25)
    )
    assert tmp_ledger.remaining("anthropic") == pytest.approx(98.5)
    assert tmp_ledger.remaining("openrouter") == pytest.approx(4.75)


def test_ledger_blocks_call_over_remaining(tmp_path, tmp_store):
    ledger = Ledger(tmp_path / "s.jsonl", budgets={"anthropic": 0.10, "openrouter": 5.0})
    fake = FakeAnthropic()
    with pytest.raises(BudgetExceeded):
        LLMClient("live", "r", ledger=ledger, store=tmp_store, sdk_client=fake).call(REQ, ticket_id="t")
    assert fake.calls == []  # aborted before the API call


def test_run_cap_blocks_before_call(tmp_ledger, tmp_store):
    fake = FakeAnthropic()
    client = LLMClient(
        "live",
        "r",
        ledger=tmp_ledger,
        store=tmp_store,
        run_budget=RunBudget({"anthropic": 0.05}),
        sdk_client=fake,
    )
    with pytest.raises(BudgetExceeded):
        client.call(REQ, ticket_id="t")
    assert fake.calls == []


def test_live_call_is_ledgered_with_actual_cost(tmp_ledger, tmp_store):
    budget = RunBudget({"anthropic": 5.0})
    res = LLMClient(
        "live", "r", ledger=tmp_ledger, store=tmp_store, run_budget=budget, sdk_client=FakeAnthropic()
    ).call(REQ, ticket_id="t")
    (entry,) = tmp_ledger.entries()
    assert entry.provider == "anthropic" and entry.cost_usd == pytest.approx(res.call.cost_usd)
    assert budget.spent["anthropic"] == pytest.approx(res.call.cost_usd)


def test_worst_case_is_an_upper_bound():
    p = load_pricebook().price("claude-opus-5-5")
    # 4000 ASCII bytes -> 2000 tokens @5 (cache write) + 1 token + 20000 out @20
    assert worst_case_cost(p, REQ) == pytest.approx((2001 * 5 + 20000 * 20) / 1e6)


def test_concurrent_reservations_cannot_jointly_cross_cap(tmp_ledger):
    budget = RunBudget({"anthropic": 1.0})
    budget.reserve("anthropic", 0.6, tmp_ledger)  # in flight, not yet settled
    with pytest.raises(BudgetExceeded):
        budget.reserve("anthropic", 0.6, tmp_ledger)
    budget.settle("anthropic", 0.6, 0.1)  # actual cost far below worst case frees the reservation
    budget.reserve("anthropic", 0.6, tmp_ledger)
    assert budget.spent["anthropic"] == pytest.approx(0.1)
