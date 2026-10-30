"""Committed data matches the generator and MANIFEST (SPEC §4.2 step 5, §11.6). Held-out is hashed, never read
item by item: only its bytes' sha256 is compared (automated QA, CLAUDE.md held-out rule)."""

from __future__ import annotations

import json

import pytest

from engine.contracts import Ticket
from engine.datagen import gen as G
from engine.datagen import publish

pytestmark = pytest.mark.skipif(
    not publish.MANIFEST.exists(), reason="no generated data yet (run `engine gen`)"
)


def _manifest() -> dict:
    return json.loads(publish.MANIFEST.read_text(encoding="utf-8"))


def test_files_match_manifest_hashes():
    m = _manifest()
    for split in G.SPLITS:
        blob = publish.split_path(split).read_bytes()
        assert publish.sha256(blob) == m["files"][f"{split}.jsonl"]["sha256"], split
    assert m["heldout_sealed"]["sha256"] == m["files"]["heldout.jsonl"]["sha256"]


def test_generator_reproduces_committed_data_byte_for_byte():
    m = _manifest()
    regenerated = G.generate()
    for split, tickets in regenerated.items():
        assert publish.sha256(publish.serialise(tickets)) == m["files"][f"{split}.jsonl"]["sha256"], split


def test_manifest_records_qa_passed_and_no_label_flags():
    m = _manifest()
    assert all(v["pass"] for v in m["qa"].values())
    assert m["decision_distribution"]["flags"] == []


def test_review_file_has_30_en_and_20_ar_dev_items_only():
    text = publish.REVIEW.read_text(encoding="utf-8")
    heads = [ln for ln in text.splitlines() if ln.startswith("## ")]
    assert len(heads) == 50
    assert all(h.startswith("## dev-") for h in heads)
    assert sum(" · en/" in h for h in heads) == 30 and sum(" · ar/" in h for h in heads) == 20


def test_dev_and_shifted_parse_as_tickets():
    for split in ("dev", "shifted"):  # held-out is not parsed here
        for line in publish.split_path(split).read_text(encoding="utf-8").splitlines():
            Ticket.model_validate_json(line)


def _dev() -> list[Ticket]:
    lines = publish.split_path("dev").read_text(encoding="utf-8").splitlines()
    return [Ticket.model_validate_json(line) for line in lines]


def test_review_covers_every_adjudication_level_and_decision():
    adj = [t for t in publish.pick_review(_dev()) if t.task_type == "adjudicate"]
    assert {t.level for t in adj} == {"L3", "L4", "L5"}
    assert {t.gold.decision for t in adj} == {"approve", "partial", "deny", "need_info"}


def test_review_batches_partition_the_review_items():
    items = publish.pick_review(_dev())
    batches = publish.review_batches(items)
    assert [len(b) for b in batches] == [10] * 5
    assert sorted(t.id for b in batches for t in b) == sorted(t.id for t in items)
    for b in batches:
        assert sum(t.language == "en" for t in b) == 6 and sum(t.language == "ar" for t in b) == 4
        assert {t.task_type for t in b} == {"faq", "intent", "extract", "adjudicate"}


def test_blind_batches_show_no_gold_level_or_trace_and_match_gold_files():
    for n in range(1, 6):
        blind = (publish.REVIEW.parent / f"batch_{n}_blind.md").read_text(encoding="utf-8")
        gold = (publish.REVIEW.parent / f"batch_{n}_gold.md").read_text(encoding="utf-8")
        for leak in ('"decision"', '"answer"', '"intent"', "Gold:", "| R", " L3", " L4", " L5", "rules v"):
            assert leak not in blind, (n, leak)
        ids_blind = [ln.split(" · ")[0][3:] for ln in blind.splitlines() if ln.startswith("## ")]
        ids_gold = [ln[3:] for ln in gold.splitlines() if ln.startswith("## ")]
        assert ids_blind == ids_gold and len(ids_blind) == 10
        assert all(i.startswith("dev-") for i in ids_blind)
