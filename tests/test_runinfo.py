"""Paid calls refuse a dirty tree (DECISIONS D0.8); only `engine smoke` opts out; replay never checks."""

import pytest

from engine import runinfo
from engine.contracts import LLMRequest
from engine.llm.client import LLMClient
from tests.conftest import FakeAnthropic

REQ = LLMRequest(model="claude-haiku-5-5", effort="low", system="S", user="u", max_tokens=100)


@pytest.fixture
def dirty(monkeypatch):
    monkeypatch.setattr(runinfo, "tree_status", lambda: " M src/engine/tasks/prompts.py")


def test_live_call_refuses_dirty_tree(dirty, tmp_ledger, tmp_store):
    fake = FakeAnthropic()
    with pytest.raises(runinfo.DirtyTree, match="prompts.py"):
        LLMClient("live", "r", ledger=tmp_ledger, store=tmp_store, sdk_client=fake).call(REQ, ticket_id="t")
    assert fake.calls == [] and tmp_ledger.entries() == []


def test_smoke_opt_out_allows_dirty_tree(dirty, tmp_ledger, tmp_store):
    fake = FakeAnthropic()
    client = LLMClient("live", "r", ledger=tmp_ledger, store=tmp_store, sdk_client=fake, allow_dirty=True)
    client.call(REQ, ticket_id="t")
    assert len(fake.calls) == 1


def test_replay_never_checks_tree(dirty, tmp_ledger, tmp_store):
    LLMClient(
        "live", "r", ledger=tmp_ledger, store=tmp_store, sdk_client=FakeAnthropic(), allow_dirty=True
    ).call(REQ, ticket_id="t")
    LLMClient("replay", "r", ledger=tmp_ledger, store=tmp_store).call(REQ, ticket_id="t")


def test_jev_refuses_dirty_tree(dirty, tmp_ledger, tmp_store, monkeypatch):
    import httpx

    from engine.contracts import JevRequest
    from engine.llm import jev

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-not-a-real-key")
    calls = []
    http = httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(500)))
    req = JevRequest(model=jev.JEV_MODEL, state="x", questions={"q": jev.noul("?")})
    with pytest.raises(runinfo.DirtyTree):
        jev.JevClient("live", "r", ledger=tmp_ledger, store=tmp_store, http=http).ask(req)
    assert calls == []


def test_git_sha_marks_dirty(dirty):
    assert runinfo.git_sha().endswith("-dirty")


def test_dirty_message_keeps_full_paths(monkeypatch):
    monkeypatch.setattr(runinfo, "tree_status", lambda: " M docs/DECISIONS.md\n?? src/new.py")
    with pytest.raises(runinfo.DirtyTree, match=r"\(docs/DECISIONS.md, src/new.py\)"):
        runinfo.require_clean_tree()


def test_porcelain_leading_space_survives(monkeypatch):
    import subprocess
    from types import SimpleNamespace

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=" M docs/SPEC.md\n"))
    assert runinfo._git("status", "--porcelain") == " M docs/SPEC.md"


def test_harness_outputs_do_not_make_the_tree_dirty(monkeypatch):
    out = "\n".join(["?? runs/matrix-dev-pilot-1/", " M runs/spend.jsonl", "?? cassettes/anthropic/abc.json"])
    monkeypatch.setattr(runinfo, "tree_status", lambda: out)
    runinfo.require_clean_tree()
    assert not runinfo.git_sha().endswith("-dirty")
    monkeypatch.setattr(runinfo, "tree_status", lambda: "\n".join([out, " M src/engine/tasks/prompts.py"]))
    with pytest.raises(runinfo.DirtyTree, match="prompts.py"):
        runinfo.require_clean_tree()
    assert runinfo.git_sha().endswith("-dirty")
