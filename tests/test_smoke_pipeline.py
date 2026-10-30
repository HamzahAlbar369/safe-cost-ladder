"""End-to-end smoke pipeline with fake Anthropic + Jev transports: no network, no key, no spend.

Verifies the plan runs, every check is produced, and a replay reproduces the live checks exactly.
"""

import json
from types import SimpleNamespace

import httpx
import pytest

from engine import smoke
from tests.conftest import FakeStream

ANSWERS = {
    "faq": {"answer": 2000},
    "intent": {"intent": "claim_status"},
    "extract": {
        "policy_number": "OMI-4471-2209",
        "accident_date": "2026-09-03",
        "report_number": "AR-558120",
        "damage_amount_sar": 12400,
        "fault_share": 25,
    },
    "adjudicate": {"decision": "approve", "payout_sar": 17000, "reasons": ["R3"], "inputs": {}},
}
EFFORT_OUT = {"low": 200, "medium": 600, "high": 1500}


class SmokeFakeSDK:
    """Mimics prompt caching per (model, effort, system) and effort-dependent output."""

    def __init__(self):
        self.cache: set[tuple] = set()
        self.messages = SimpleNamespace(stream=self._stream)
        self.models = SimpleNamespace(
            list=lambda: [
                SimpleNamespace(id=m, display_name=m, max_input_tokens=1, max_tokens=1) for m in smoke.MODELS
            ]
        )

    def _stream(self, **p):
        system = p["system"][0]["text"]
        effort = p["output_config"]["effort"]
        key = (p["model"], effort, system)
        prompt = len(system) // 4
        cacheable = prompt >= 512
        hit = cacheable and key in self.cache
        if cacheable:
            self.cache.add(key)
        task = p["messages"][0]["content"].split("\n", 1)[0].removeprefix("TASK: ")
        out = EFFORT_OUT[effort]
        usage = SimpleNamespace(
            input_tokens=40,
            cache_creation_input_tokens=0 if hit or not cacheable else prompt,
            cache_read_input_tokens=prompt if hit else 0,
            output_tokens=out,
            output_tokens_details=SimpleNamespace(thinking_tokens=out - 50),
        )
        msg = SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps(ANSWERS[task]))],
            stop_reason="end_turn",
            usage=usage,
            model=p["model"],
        )
        return FakeStream(msg)


def jev_transport(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    answers = {}
    for name, q in body["questions"].items():
        if q["type"] == "choice":
            answers[name] = {"type": "choice", "choice": "complex", "confidence": 0.8, "probabilities": {}}
        else:
            answers[name] = {"type": "noul", "noul": 0.7}
    return httpx.Response(
        200,
        json={
            "model": "typesafe/jev-1.14-x",
            "answers": answers,
            "usage": {"input_tokens": 300, "output_tokens": 9, "cost": 1.26e-05},
        },
    )


@pytest.fixture
def env(tmp_path, tmp_store, tmp_ledger, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-not-a-real-key")
    return tmp_path, tmp_store, tmp_ledger


def test_smoke_live_then_replay_reproduces(env):
    tmp_path, store, ledger = env
    http = httpx.Client(transport=httpx.MockTransport(jev_transport))
    report, calls, jev_calls = smoke.run(
        "live",
        {"anthropic": 50.0, "openrouter": 1.0},
        ledger=ledger,
        store=store,
        sdk=SmokeFakeSDK(),
        http=http,
        smoke_json=tmp_path / "smoke.json",
    )
    n_planned = sum(len(v) for v in smoke.plan_anthropic().values())
    assert len(calls) == n_planned and len(jev_calls) == 10
    c = report.checks
    assert (
        c["1_configs_parseable"]["configs_fail"] == [] and len(c["1_configs_parseable"]["configs_pass"]) == 9
    )
    assert c["2_effort_effect"]["claude-opus-5-5"]["effort_changes_output_measurably"]
    assert c["5_effort_vs_cache"]["claude-opus-5-5"]["effort_change_invalidates_cache"] is True
    assert c["4_min_cacheable_prefix"]["claude-haiku-5-5"]["full_static_prefix"]["cached"]
    assert c["6_thinking_vs_effort"]["claude-sonnet-5-5"]["thinking_on_when_omitted"] is True
    assert c["7_jev"]["reachable"] and c["7_jev"]["arabic"]["complexity_agreement_en_ar"] == "5/5"
    assert c["truncations"] == []
    assert report.models_api["missing"] == []
    # ledger: two providers, separate
    assert ledger.remaining("openrouter") == pytest.approx(5.0 - 10 * 1.26e-05)
    assert ledger.remaining("anthropic") < 100.0

    (tmp_path / "smoke.json").write_text(report.model_dump_json(), encoding="utf-8")
    replayed, rcalls, _ = smoke.run("replay", ledger=ledger, store=store, smoke_json=tmp_path / "smoke.json")
    assert all(x.call.replayed for x in rcalls)
    assert smoke.comparable(replayed.checks) == smoke.comparable(report.checks)


def test_estimate_has_breakdown_per_check():
    est = smoke.estimate()
    checks = {k.split(":")[0] for k in est["rows"]}
    assert checks == {"cache_size", "matrix", "thinking", "jev"}
    assert 0 < est["anthropic_expected"] < est["anthropic_worst"]
