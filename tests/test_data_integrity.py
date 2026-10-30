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
