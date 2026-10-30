"""Solvability check (Phase 2 gate): every failure of the strongest config is dumped with everything needed to
decide whether it is a generator bug, genuinely ambiguous, or genuinely hard. The categories are assigned by a
human-readable review (docs/SOLVABILITY.md); this module only gathers the evidence."""

from __future__ import annotations

import json

from engine.contracts import Frozen, LLMResponse, Ticket
from engine.datagen.rules import load_version
from engine.eval.cells import Cell, read_calls
from engine.llm.client import CassetteStore
from engine.verify import verify


class Failure(Frozen):
    ticket_id: str
    task: str
    level: str
    language: str
    template_family: str
    design: str
    text: str
    gold: dict
    model_output: dict | str | None
    wrong_fields: tuple[str, ...]
    verdicts: tuple[str, ...]  # e.g. "V2 failed: payout ..." / "V0-V2 passed"
    trace: tuple[str, ...]  # rule-by-rule engine trace for adjudication


def failures(
    run_id: str, config_id: str, tickets: list[Ticket], cells: list[Cell], store: CassetteStore | None = None
) -> list[Failure]:
    store = store or CassetteStore()
    by_id = {t.id: t for t in tickets}
    cell_of = {c.ticket_id: c for c in cells if c.config_id == config_id}
    calls = {c.ticket_id: c for c in read_calls(run_id) if c.role == "answer" and c.config_id == config_id}
    out = []
    for tid, cell in sorted(cell_of.items()):
        if cell.correct:
            continue
        t = by_id[tid]
        cassette = store.get("anthropic", calls[tid].request_hash)
        response = LLMResponse.model_validate(cassette.response) if cassette else None
        text = response.text if response else ""
        try:
            model_output: dict | str | None = json.loads(text)
        except ValueError:
            model_output = text or None
        rules = load_version(t.rules_version)
        verdicts = verify(
            t.task_type, text, t.text, rules, stop_reason=response.stop_reason if response else None
        )
        failed = [f"{v.level} failed: {'; '.join(v.reasons)}" for v in verdicts if not v.passed]
        out.append(
            Failure(
                ticket_id=tid,
                task=t.task_type,
                level=t.level,
                language=t.language,
                template_family=t.template_family,
                design=t.meta.design,
                text=t.text,
                gold=t.gold.model_dump(mode="json"),
                model_output=model_output,
                wrong_fields=tuple(k for k, ok in cell.fields.items() if not ok) or ("answer",),
                verdicts=tuple(failed) or ("V0-V2 passed",),
                trace=tuple(f"{s.rule}: {s.check} -> {s.fired} {s.detail}" for s in t.meta.trace),
            )
        )
    return out
