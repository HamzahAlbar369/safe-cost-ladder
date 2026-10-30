"""Jev client against the documented Decisions response (mocked transport; no network, no key needed)."""

import httpx
import pytest

from engine.contracts import JevRequest
from engine.llm import jev
from engine.llm.client import ReplayMiss

# Response body copied from OpenRouter's documented example for POST /api/alpha/decisions.
DOC_RESPONSE = {
    "answers": {
        "is_bug": {"noul": 0.96, "type": "noul"},
        "team": {
            "choice": "payments",
            "confidence": 0.75,
            "probabilities": {"account": 0, "frontend": 0.16, "payments": 0.84},
            "type": "choice",
        },
    },
    "id": "gen-dec-1789738314-X5e5eKGQdvR9rblyX250",
    "model": "typesafe/jev-1.13-20260917",
    "provider": "TypeSafe",
    "usage": {"cost": 0.000019992, "input_tokens": 476, "output_tokens": 70},
}

REQ = JevRequest(
    model=jev.JEV_MODEL,
    state="My checkout page shows a blank screen after I click Pay.",
    questions={
        "is_bug": jev.noul("Is the customer reporting a software defect?"),
        "team": jev.choice("Which team?", {"payments": "Billing", "frontend": "UI", "account": "Login"}),
    },
)


@pytest.fixture
def transport_calls(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-not-a-real-key")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=DOC_RESPONSE)

    return calls, httpx.Client(transport=httpx.MockTransport(handler))


def test_payload_matches_documented_schema():
    p = jev.jev_payload(REQ)
    assert set(p) == {"model", "state", "questions"}
    assert p["questions"]["team"]["type"] == "choice" and "criteria" in p["questions"]["team"]
    assert jev.score("How urgent?", ["low", "high"])["criteria"] == ["low", "high"]


def test_live_records_cost_from_usage_and_replays(tmp_store, tmp_ledger, transport_calls):
    calls, http = transport_calls
    c = jev.JevClient("live", "r", ledger=tmp_ledger, store=tmp_store, http=http)
    resp, replayed = c.ask(REQ)
    assert not replayed and len(calls) == 1
    assert str(calls[0].url) == jev.DECISIONS_URL
    assert calls[0].headers["authorization"].startswith("Bearer ")
    (entry,) = tmp_ledger.entries()
    assert entry.provider == "openrouter" and entry.cost_usd == pytest.approx(0.000019992)
    assert tmp_ledger.remaining("anthropic") == 100.0

    again, replayed = jev.JevClient("replay", "r2", ledger=tmp_ledger, store=tmp_store).ask(REQ)
    assert replayed and again == resp


def test_replay_miss(tmp_store, tmp_ledger):
    with pytest.raises(ReplayMiss):
        jev.JevClient("replay", "r", ledger=tmp_ledger, store=tmp_store).ask(REQ)


def test_answer_value():
    assert jev.answer_value(DOC_RESPONSE["answers"]["team"]) == ("payments", 0.75)
    v, conf = jev.answer_value(DOC_RESPONSE["answers"]["is_bug"])
    assert v == 0.96 and conf == pytest.approx(0.96)


def test_http_error_is_reported_without_key(tmp_store, tmp_ledger, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-not-a-real-key")
    http = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"error": {"message": "bad"}}))
    )
    with pytest.raises(jev.JevError) as ei:
        jev.JevClient("live", "r", ledger=tmp_ledger, store=tmp_store, http=http).ask(REQ)
    assert "test-not-a-real-key" not in str(ei.value)
    assert tmp_ledger.entries() == []
