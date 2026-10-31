"""Five fresh demo tickets for `engine ask` (data/demo/tickets.jsonl), never part of any evaluation.

Same generator and rules engine as the splits (gold labels come only from the rules engine), another seed,
and a declared pick: faq EN, intent AR, extract EN, adjudicate AR (rules v1), adjudicate EN under rules v2
(the policy-change scenario). Each pick must not be a near-duplicate (5-gram Jaccard below gen.NEAR_DUP, the
split QA threshold) of any ticket of the same task in dev, shifted or held-out. Held-out is read only by this
automated duplicate scan (CLAUDE.md allows automated QA scans); only the maximum similarity is reported.
"""

from __future__ import annotations

import json
from pathlib import Path

from engine.contracts import Ticket
from engine.datagen.gen import NEAR_DUP, generate, jaccard, shingles
from engine.eval.data import GENERATED
from engine.llm.pricing import ROOT

DEMO_SEED = 20261031
OUT = ROOT / "data" / "demo" / "tickets.jsonl"
PICKS = (  # (source split of the fresh generation, task, language, rules version)
    ("dev", "faq", "en", "v1"),
    ("dev", "intent", "ar", "v1"),
    ("dev", "extract", "en", "v1"),
    ("dev", "adjudicate", "ar", "v1"),
    ("shifted", "adjudicate", "en", "v2"),
)


def _existing() -> dict[str, list[frozenset[str]]]:
    by_task: dict[str, list[frozenset[str]]] = {}
    for name in ("dev.jsonl", "shifted.jsonl", "heldout.jsonl"):
        for line in (GENERATED / name).read_text("utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                by_task.setdefault(d["task_type"], []).append(shingles(d["text"]))
    return by_task


def build(seed: int = DEMO_SEED, out: Path = OUT) -> tuple[list[Ticket], list[float]]:
    fresh = generate(seed)
    existing = _existing()
    picked, scores = [], []
    for i, (split, task, lang, version) in enumerate(PICKS, start=1):
        for t in sorted(fresh[split], key=lambda t: t.id):
            if (t.task_type, t.language, t.rules_version) != (task, lang, version):
                continue
            sh = shingles(t.text)
            sim = max((jaccard(sh, o) for o in existing[task]), default=0.0)
            if sim < NEAR_DUP:
                picked.append(t.model_copy(update={"id": f"demo-{i:02d}"}))
                scores.append(sim)
                break
        else:
            raise RuntimeError(f"no fresh {task}/{lang}/{version} ticket below the near-duplicate threshold")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(t.model_dump_json() + "\n" for t in picked), encoding="utf-8")
    return picked, scores


def load(path: Path = OUT) -> list[Ticket]:
    return [Ticket.model_validate_json(x) for x in path.read_text("utf-8").splitlines() if x.strip()]
