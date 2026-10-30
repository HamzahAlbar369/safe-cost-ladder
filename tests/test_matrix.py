"""Matrix runner, pacer and pilot subset (no network: fake SDK, temp cassettes and ledger)."""

from __future__ import annotations

import json
import threading

from engine.contracts import ModelCall, RateLimitInfo
from engine.eval import matrix as M
from engine.eval.data import load_split
from engine.eval.pacer import Pacer
from engine.eval.subsets import PILOT_SIZE, stratified_subset
from engine.llm.client import request_hash
from engine.tasks.request import build_request
from tests.conftest import FakeAnthropic

# --- pacer ----------------------------------------------------------------------------------------


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def test_pacer_caps_inflight_and_returns_wait_time():
    p = Pacer(2)
    assert p.acquire() >= 0 and p.acquire() >= 0 and p.inflight == 2
    got = []
    t = threading.Thread(target=lambda: got.append(p.acquire()))
    t.start()
    t.join(timeout=0.2)
    assert t.is_alive()  # third caller waits for a slot
    p.release(None, rate_limited=False)
    t.join(timeout=2)
    assert got and got[0] > 0  # the wait is measured
    assert p.inflight == 2


def test_pacer_halves_on_429_and_recovers():
    p = Pacer(8)
    p.acquire()
    p.release(RateLimitInfo(retry_after_s=0.0), rate_limited=True)
    assert p.allowed == 4 and p.rate_limited == 1
    for _ in range(20):
        p.acquire()
        p.release(None, rate_limited=False)
    assert p.allowed == 5  # creeps back up


def test_pacer_pauses_when_headers_show_low_headroom():
    p = Pacer(4)
    p.acquire()
    before = p.resume_at
    p.release(RateLimitInfo(requests_remaining=1, requests_limit=100), rate_limited=False)
    assert p.resume_at > before
    q = Pacer(4)
    q.acquire()
    q.release(RateLimitInfo(output_tokens_remaining=100), rate_limited=False, next_max_tokens=6144)
    assert q.resume_at > 0


# --- pilot subset ---------------------------------------------------------------------------------


def test_pilot_is_stratified_deterministic_and_bilingual():
    dev = load_split("dev")
    a, b = stratified_subset(dev), stratified_subset(dev)
    assert [t.id for t in a] == [t.id for t in b] and len(a) == PILOT_SIZE
    assert {t.task_type for t in a} == {"faq", "intent", "extract", "adjudicate"}
    assert {t.level for t in a} == {"L1", "L2", "L3", "L4", "L5"}
    assert 8 <= sum(t.language == "ar" for t in a) <= 16
    assert all(t.split == "dev" for t in a)


# --- runner ---------------------------------------------------------------------------------------


def run(tmp_path, tmp_store, tmp_ledger, tickets, fake, mode="live", cap=50.0, run_id="mx"):
    return M.run_matrix(
        "dev",
        tickets,
        mode=mode,
        run_id=run_id,
        cap_usd=cap,
        per_model_concurrency=2,
        git_sha="testsha",
        progress=lambda _m: None,
        store=tmp_store,
        ledger=tmp_ledger,
        sdk_client=fake,
        out_dir=tmp_path / run_id,
    )


def read_calls(tmp_path, run_id="mx"):
    lines = (tmp_path / run_id / "calls.jsonl").read_text("utf-8").splitlines()
    return [ModelCall.model_validate_json(x) for x in lines]


def test_matrix_records_every_cell_warms_each_model_task_and_is_resumable(tmp_path, tmp_store, tmp_ledger):
    tickets = [t for t in load_split("dev") if t.task_type in ("faq", "intent")][:4]
    fake = FakeAnthropic(text='{"answer": "yes"}')
    s = run(tmp_path, tmp_store, tmp_ledger, tickets, fake)
    calls = read_calls(tmp_path)
    answers = [c for c in calls if c.role == "answer"]
    warm = [c for c in calls if c.role == "probe"]
    assert s.n_cells == s.n_recorded == len(answers) == 4 * 9 and s.n_errors == 0
    tasks = {t.task_type for t in tickets}
    assert len(warm) == 3 * len(tasks)  # one per (model, task), none counted as data
    assert len(fake.calls) == len(answers) + len(warm)
    assert {c.config_id for c in answers} == {
        f"{m}-{e}" for m in ("haiku", "sonnet", "opus") for e in ("low", "medium", "high")
    }
    assert all(c.queue_wait_ms >= 0 for c in answers)
    manifest = json.loads((tmp_path / "mx" / "manifest.json").read_text("utf-8"))
    assert manifest["manifest"]["git_sha"] == "testsha" and manifest["summary"]["n_live"] == 36

    # resume: nothing left to do, no new API calls, no duplicate rows
    n = len(fake.calls)
    again = run(tmp_path, tmp_store, tmp_ledger, tickets, fake)
    assert again.n_cells == 0 and len(fake.calls) == n
    assert len(read_calls(tmp_path)) == len(calls)


def test_matrix_replay_in_a_new_run_makes_no_calls_and_keeps_recorded_cost(tmp_path, tmp_store, tmp_ledger):
    tickets = [t for t in load_split("dev") if t.task_type == "faq"][:2]
    fake = FakeAnthropic(text='{"answer": "yes"}')
    run(tmp_path, tmp_store, tmp_ledger, tickets, fake, run_id="a")
    n = len(fake.calls)
    s = run(tmp_path, tmp_store, tmp_ledger, tickets, fake, mode="auto", run_id="b")
    assert len(fake.calls) == n and s.n_replayed == 18 and s.n_live == 0 and s.spend_usd == 0
    live, replay = read_calls(tmp_path, "a"), read_calls(tmp_path, "b")

    def cost(cs):
        return sorted((c.ticket_id, c.config_id, round(c.cost_usd, 9)) for c in cs if c.role == "answer")

    assert cost(live) == cost(replay)
    assert all(c.queue_wait_ms == 0 for c in replay)  # replays never queued


def test_matrix_stops_at_the_run_cap(tmp_path, tmp_store, tmp_ledger):
    tickets = [t for t in load_split("dev") if t.task_type == "adjudicate"][:3]
    fake = FakeAnthropic(text='{"answer": "yes"}')
    try:
        run(tmp_path, tmp_store, tmp_ledger, tickets, fake, cap=0.05)
    except Exception as e:  # BudgetExceeded surfaces from a worker thread
        assert "cap" in str(e) or "budget" in str(e)
    else:
        raise AssertionError("expected the run cap to stop the matrix")
    assert tmp_ledger.spent("anthropic") <= 0.05


def test_pending_live_skips_recorded_cassettes(tmp_path, tmp_store, tmp_ledger):
    tickets = [t for t in load_split("dev") if t.task_type == "faq"][:1]
    fake = FakeAnthropic(text='{"answer": "yes"}')
    run(tmp_path, tmp_store, tmp_ledger, tickets, fake)
    cells = M.plan_cells(tickets)
    assert M.pending_live(cells, tmp_store, set()) == []
    other = [t for t in load_split("dev") if t.task_type == "intent"][:1]
    assert len(M.pending_live(M.plan_cells(other), tmp_store, set())) == 9
    assert tmp_store.get("anthropic", request_hash(build_request(*cells[0])))


def test_epoch_repeat_changes_every_cassette_key_and_connections_are_prewarmed(
    tmp_path, tmp_store, tmp_ledger
):
    t = [x for x in load_split("dev") if x.task_type == "faq"][:1]
    a, b = (
        build_request(t[0], "claude-opus-5-5", "low"),
        build_request(t[0], "claude-opus-5-5", "low", repeat=1),
    )
    assert request_hash(a) != request_hash(b)

    class Models:
        def __init__(self):
            self.n = 0

        def retrieve(self, _id):
            self.n += 1

    fake = FakeAnthropic(text='{"answer": "yes"}')
    fake.models = Models()
    run(tmp_path, tmp_store, tmp_ledger, t, fake)
    assert fake.models.n == 2 * 3  # per-model concurrency x 3 models, once per run
