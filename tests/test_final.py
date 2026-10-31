"""`engine final` (SPEC §7.6): the guard is tested WITHOUT loading held-out data; the live O1 executor with
a fake caller (real threads and sleeps, no network)."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from typer.testing import CliRunner

from engine import final as F
from engine import runinfo
from engine.cli import app
from engine.contracts import ModelCall
from engine.eval.data import SealedSplit, load_split
from engine.policy.cascade import O1Options
from engine.policy.live import LiveCall, run_ticket
from tests.test_o1 import COST, cell, floors, ticket


def fake_git(tags: str = ""):
    def _git(*args: str) -> str:
        if args[:2] == ("tag", "--points-at"):
            return tags
        if args[:1] == ("rev-parse",):
            return "abc123"
        raise AssertionError(f"unexpected git call {args}")

    return _git


@pytest.fixture
def no_heldout(monkeypatch, tmp_path):
    """Any attempt to read held-out fails the test: the loader is replaced and the path points nowhere."""
    calls = []
    monkeypatch.setattr(F, "load_heldout", lambda *a, **k: calls.append(a) or pytest.fail("held-out loaded"))
    monkeypatch.setattr(F, "HELDOUT", tmp_path / "does-not-exist.jsonl")
    return calls


def test_guard_refuses_without_a_freeze_tag(monkeypatch, no_heldout):
    monkeypatch.setattr(runinfo, "_git", fake_git("floors-v1"))
    with pytest.raises(F.FinalRefused, match="freeze-"):
        F.guard()
    assert no_heldout == []


def test_guard_refuses_a_dirty_tree_even_when_tagged(monkeypatch, no_heldout):
    monkeypatch.setattr(runinfo, "_git", fake_git("freeze-v1"))
    monkeypatch.setattr(runinfo, "tree_status", lambda: " M src/engine/tasks/prompts.py")
    with pytest.raises(F.FinalRefused, match="code changes"):
        F.guard()
    assert no_heldout == []


def test_guard_passes_on_a_clean_tagged_head_and_ignores_run_outputs(monkeypatch, no_heldout):
    monkeypatch.setattr(runinfo, "_git", fake_git("floors-v1\nfreeze-v1"))
    monkeypatch.setattr(runinfo, "tree_status", lambda: "?? runs/o1-live-heldout-freeze-v1/calls.jsonl")
    token = F.guard()
    assert token.tag == "freeze-v1" and token.sha == "abc123"
    assert F.run_ids(token) == ("matrix-heldout-freeze-v1", "o1-live-heldout-freeze-v1")
    assert no_heldout == []


def test_cli_final_refuses_before_reading_heldout(monkeypatch, no_heldout):
    monkeypatch.setattr(runinfo, "_git", fake_git(""))
    result = CliRunner().invoke(app, ["final", "--estimate"])
    assert result.exit_code == 2 and "freeze-" in result.output
    assert no_heldout == []


def test_load_heldout_needs_the_token_and_the_sealed_hash(tmp_path):
    data, manifest = tmp_path / "h.jsonl", tmp_path / "MANIFEST.json"
    data.write_bytes(b"")
    manifest.write_text('{"heldout_sealed": {"sha256": "0000"}}', encoding="utf-8")
    with pytest.raises(F.FinalRefused, match="token"):
        F.load_heldout("freeze-v1", data, manifest)  # type: ignore[arg-type]
    with pytest.raises(F.FinalRefused, match="sealed"):
        F.load_heldout(F.GuardToken(tag="freeze-v1", sha="x"), data, manifest)


def test_heldout_stays_sealed_for_every_other_loader():
    with pytest.raises(SealedSplit):
        load_split("heldout")


# --- live O1 executor -----------------------------------------------------------------------------


def call_record(t, cfg: str) -> ModelCall:
    return ModelCall(
        call_id=cfg, ticket_id=t.id, run_id="test", config_id=cfg, model=cfg, effort=None, role="answer",
        request_hash=cfg, input_tokens=1, cache_creation_tokens=0, cache_read_tokens=0, output_tokens=1,
        latency_ms=0.0, cost_usd=COST[cfg] / 4, cost_usd_nocache=COST[cfg], stop_reason="end_turn",
        parsed_ok=True, replayed=False,
    )  # fmt: skip


def fake_caller(spec: dict[str, dict]):
    """spec: config -> {"sleep": seconds, plus `cell` kwargs}."""

    def call(t, cfg, role):
        kw = dict(spec[cfg])
        time.sleep(kw.pop("sleep"))
        return LiveCall(cell=cell(t, cfg, latency_s=0, **kw), calls=(call_record(t, cfg),))

    return call


def live(spec, o=None):
    t = ticket()
    with ThreadPoolExecutor(4) as pool:
        start = time.perf_counter()
        r = run_ticket(t, fake_caller(spec), floors(), {}, o or O1Options(deadline_s=0.3), pool)
        wall = time.perf_counter() - start
    return r, wall


def test_live_accepts_when_both_agree_and_charges_both():
    r, _ = live({"haiku-low": {"sleep": 0.05}, "haiku-medium": {"sleep": 0.1}, "opus-low": {"sleep": 0}})
    assert r.outcome.path == ("haiku-low", "haiku-medium") and r.outcome.correct
    assert r.outcome.cost_nocache == pytest.approx(COST["haiku-low"] + COST["haiku-medium"])
    assert 0.09 <= r.outcome.latency_ms / 1000 < 0.3  # waited for the second opinion, not the deadline


def test_live_escalates_at_once_when_first_fails_checks_and_still_charges_the_late_second():
    r, wall = live(
        {
            "haiku-low": {"sleep": 0.05, "failed": ("V2",), "correct": False},
            "haiku-medium": {"sleep": 0.6},
            "opus-low": {"sleep": 0.05},
        }
    )
    assert r.outcome.path == ("haiku-low", "haiku-medium", "opus-low") and r.outcome.correct
    assert r.outcome.latency_ms / 1000 < 0.3  # D3.5: did not wait for haiku-medium (0.6 s)
    assert wall >= 0.55  # ...but its call completed and is charged
    assert r.outcome.cost_nocache == pytest.approx(sum(COST.values()))
    assert r.trace.reason == "first failed checks"


def test_live_late_second_opinion_falls_back_to_first_at_the_deadline():
    r, _ = live({"haiku-low": {"sleep": 0.05}, "haiku-medium": {"sleep": 0.7}, "opus-low": {"sleep": 0}})
    assert r.outcome.path == ("haiku-low", "haiku-medium") and r.trace.second_late
    assert 0.28 <= r.outcome.latency_ms / 1000 < 0.6  # decided at D = 0.3 s, not at 0.7 s


def test_live_disagreement_escalates_to_top():
    r, _ = live(
        {
            "haiku-low": {"sleep": 0.02},
            "haiku-medium": {"sleep": 0.05, "decision": "deny"},
            "opus-low": {"sleep": 0},
        }
    )
    assert r.outcome.path[-1] == "opus-low" and r.trace.reason == "disagree"


def test_live_refuses_options_outside_the_final_policy():
    from engine.policy.live import run_live

    with pytest.raises(ValueError):
        run_live([], fake_caller({}), floors(), {}, O1Options(tier0=True))
