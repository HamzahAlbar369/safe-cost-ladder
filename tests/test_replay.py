"""Record/replay determinism (SPEC §6.5) with a fake SDK: no network, no key."""

import pytest

from engine.contracts import LLMRequest
from engine.llm.client import LLMClient, ReplayMiss, request_hash
from tests.conftest import FakeAnthropic

REQ = LLMRequest(
    model="claude-opus-5-5", effort="low", system="STATIC", user="faq: q", max_tokens=1000, schema_name="faq"
)


def test_record_then_replay_is_identical(tmp_store, tmp_ledger):
    fake = FakeAnthropic()
    live = LLMClient("live", "r1", ledger=tmp_ledger, store=tmp_store, sdk_client=fake)
    a = live.call(REQ, ticket_id="t1", validate=lambda s: s.startswith("{"))
    assert len(fake.calls) == 1 and not a.call.replayed and a.call.parsed_ok

    replay = LLMClient("replay", "r2", ledger=tmp_ledger, store=tmp_store, sdk_client=None)
    b = replay.call(REQ, ticket_id="t1", validate=lambda s: s.startswith("{"))
    assert b.call.replayed
    assert b.response == a.response
    assert b.call.cost_usd == a.call.cost_usd
    assert b.call.latency_ms == a.call.latency_ms
    # replay spends nothing
    assert len(tmp_ledger.entries()) == 1


def test_replay_miss_raises(tmp_store, tmp_ledger):
    with pytest.raises(ReplayMiss):
        LLMClient("replay", "r", ledger=tmp_ledger, store=tmp_store).call(REQ, ticket_id="t")


def test_auto_uses_cassette_when_present(tmp_store, tmp_ledger):
    fake = FakeAnthropic()
    LLMClient("live", "r", ledger=tmp_ledger, store=tmp_store, sdk_client=fake).call(REQ, ticket_id="t")
    LLMClient("auto", "r", ledger=tmp_ledger, store=tmp_store, sdk_client=fake).call(REQ, ticket_id="t")
    assert len(fake.calls) == 1


def test_hash_covers_every_output_relevant_field():
    base = request_hash(REQ)
    for change in (
        {"model": "claude-sonnet-5-5"},
        {"effort": "high"},
        {"system": "STATIC2"},
        {"user": "faq: q2"},
        {"max_tokens": 1001},
        {"schema_name": "intent"},
        {"thinking": "adaptive"},
        {"repeat": 1},
    ):
        assert request_hash(REQ.model_copy(update=change)) != base, change
    assert request_hash(REQ) == base  # deterministic


def test_cache_layout_and_effort_params():
    p = LLMClient.build_params(REQ)
    assert p["system"] == [{"type": "text", "text": "STATIC", "cache_control": {"type": "ephemeral"}}]
    assert p["messages"] == [{"role": "user", "content": "faq: q"}]
    assert p["output_config"] == {"effort": "low"}
    assert "thinking" not in p
    assert LLMClient.build_params(REQ.model_copy(update={"thinking": "adaptive"}))["thinking"] == {
        "type": "adaptive"
    }


def test_cassette_never_contains_system_text_or_key(tmp_store, tmp_ledger):
    LLMClient("live", "r", ledger=tmp_ledger, store=tmp_store, sdk_client=FakeAnthropic()).call(
        REQ, ticket_id="t"
    )
    (path,) = tmp_store.all()
    raw = path.read_text(encoding="utf-8")
    assert "STATIC" not in raw and "system_sha256" in raw
    assert "sk-ant" not in raw
