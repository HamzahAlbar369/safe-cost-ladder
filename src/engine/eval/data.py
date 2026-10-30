"""Split loading. Held-out is never loaded here: only `engine final` may read it (CLAUDE.md, SPEC §7.6)."""

from __future__ import annotations

from engine.contracts import Ticket
from engine.llm.pricing import ROOT

GENERATED = ROOT / "data" / "generated"


class SealedSplit(RuntimeError):
    pass


def load_split(split: str) -> list[Ticket]:
    if split == "heldout":
        raise SealedSplit("heldout is sealed: only `engine final` (clean freeze-* tag) may load it")
    path = GENERATED / f"{split}.jsonl"
    return [Ticket.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines()]
