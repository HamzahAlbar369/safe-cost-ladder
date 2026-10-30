"""The committed dev matrix must replay exactly from its cassettes with no key (Phase 2 gate)."""

import pytest

from engine.eval import replay
from engine.eval.data import load_split
from engine.llm.pricing import ROOT

RUN = "matrix-dev-full-1"


@pytest.mark.skipif(not (ROOT / "runs" / RUN / "calls.jsonl").exists(), reason="dev matrix not recorded")
def test_dev_matrix_replays_exactly_and_covers_every_cell():
    tickets = load_split("dev")
    assert replay.compare(RUN, tickets, repeat=1) == []
    from engine.eval.cells import build_cells

    cells, problems = build_cells([RUN], tickets)
    assert problems == [] and len(cells) == len(tickets) * 9
