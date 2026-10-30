"""Matrix cells: one graded, verified record per (ticket, config), built from a run's calls.jsonl and the
cassettes. Everything downstream (baselines, oracle, floors, ladders) is a pure function of these cells, so
evaluating a policy costs no API calls (SPEC §7.4)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from engine.contracts import LLMResponse, ModelCall, Ticket
from engine.datagen.rules import load_version
from engine.eval.matrix import runs_dir
from engine.llm.client import CassetteStore
from engine.tasks.graders import grade
from engine.verify import accepted, parse_output, verify


class Cell(BaseModel):
    ticket_id: str
    task: str
    level: str
    language: str
    config_id: str
    model: str
    effort: str
    correct: bool
    fields: dict[str, bool]
    parsed_ok: bool  # V0 passed (finished normally, valid JSON, schema-valid, in range)
    verified: bool  # V0-V2 all passed (the verifier would accept this answer)
    failed_checks: tuple[str, ...] = ()  # which of V0 / V1 / V2 rejected the answer
    check_reasons: tuple[str, ...] = ()  # why, one entry per failed check
    truncated: bool  # stop_reason max_tokens
    cost_usd: float  # Cost with caching (actual)
    cost_usd_nocache: float  # Cost without caching (headline)
    latency_ms: float  # request sent -> response received
    queue_wait_ms: float
    input_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    output_tokens: int
    thinking_tokens: int | None
    stop_reason: str | None
    replayed: bool
    # adjudicate answer as the model stated it (V3 second opinion compares these); None if absent/unparsed
    decision: str | None = None
    payout_sar: float | None = None


def read_calls(run_id: str) -> list[ModelCall]:
    path: Path = runs_dir(run_id) / "calls.jsonl"
    return [ModelCall.model_validate_json(x) for x in path.read_text("utf-8").splitlines() if x.strip()]


def build_cells(
    run_ids: list[str], tickets: list[Ticket], store: CassetteStore | None = None
) -> tuple[list[Cell], list[str]]:
    """Cells for every answer call in the runs (later runs win on duplicates). Also returns the problems found
    (calls without a response, missing cassettes) so a gate can require an empty list."""
    calls = [(run_id, call) for run_id in run_ids for call in read_calls(run_id)]
    return cells_from_calls(calls, tickets, store)


def cells_from_calls(
    calls: list[tuple[str, ModelCall]], tickets: list[Ticket], store: CassetteStore | None = None
) -> tuple[list[Cell], list[str]]:
    store = store or CassetteStore()
    by_id = {t.id: t for t in tickets}
    rules = {v: load_version(v) for v in ("v1", "v2")}
    cells: dict[tuple[str, str], Cell] = {}
    problems: list[str] = []
    for run_id, call in calls:
        if call.role != "answer":
            continue
        ticket = by_id.get(call.ticket_id)
        if ticket is None:
            problems.append(f"{run_id}: unknown ticket {call.ticket_id}")
            continue
        cassette = store.get("anthropic", call.request_hash)
        if call.error or cassette is None:
            problems.append(f"{run_id}: {call.ticket_id} {call.config_id} has no recorded response")
            continue
        response = LLMResponse.model_validate(cassette.response)
        cells[(call.ticket_id, call.config_id)] = _cell(ticket, call, response, rules[ticket.rules_version])
    return list(cells.values()), problems


def _cell(ticket: Ticket, call: ModelCall, response: LLMResponse, rules) -> Cell:
    task = ticket.task_type
    verdicts = verify(task, response.text, ticket.text, rules, stop_reason=response.stop_reason)
    out = parse_output(response.text)
    g = grade(task, ticket.gold.model_dump(mode="json"), out)
    parsed = verdicts[0].passed
    return Cell(
        ticket_id=ticket.id,
        task=task,
        level=ticket.level,
        language=ticket.language,
        config_id=call.config_id,
        model=call.model,
        effort=call.effort or "",
        correct=g.correct and parsed,  # a malformed or truncated answer is a failed task (SPEC §3.1)
        fields=g.fields,
        parsed_ok=parsed,
        verified=accepted(verdicts),
        failed_checks=tuple(v.level for v in verdicts if not v.passed),
        check_reasons=tuple(f"{v.level}: {'; '.join(v.reasons)}" for v in verdicts if not v.passed),
        truncated=response.stop_reason == "max_tokens",
        cost_usd=call.cost_usd,
        cost_usd_nocache=call.cost_usd_nocache,
        latency_ms=call.latency_ms,
        queue_wait_ms=call.queue_wait_ms,
        input_tokens=call.input_tokens,
        cache_creation_tokens=call.cache_creation_tokens,
        cache_read_tokens=call.cache_read_tokens,
        output_tokens=call.output_tokens,
        thinking_tokens=call.thinking_tokens,
        stop_reason=response.stop_reason,
        replayed=call.replayed,
        **_adjudicate_answer(task, out),
    )


def _adjudicate_answer(task: str, out) -> dict:
    if task != "adjudicate" or not isinstance(out, dict):
        return {}
    payout = out.get("payout_sar")
    decision = out.get("decision")
    return {
        "decision": decision if isinstance(decision, str) else None,
        "payout_sar": float(payout)
        if isinstance(payout, int | float) and not isinstance(payout, bool)
        else None,
    }
