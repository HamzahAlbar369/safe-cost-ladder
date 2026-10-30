"""Replay check (Phase 2 gate): replaying a recorded matrix through the record/replay client, with no key
and no network, must reproduce the live run's per-call costs, latencies, token counts and every metric."""

from __future__ import annotations

from engine.contracts import ModelCall, Ticket
from engine.datagen.rules import load_version
from engine.eval.cells import Cell, cells_from_calls, read_calls
from engine.llm.client import CassetteStore, LLMClient
from engine.tasks.request import build_request
from engine.verify.v0 import check_format

CALL_FIELDS = (
    "ticket_id",
    "config_id",
    "model",
    "effort",
    "request_hash",
    "input_tokens",
    "cache_creation_tokens",
    "cache_read_tokens",
    "output_tokens",
    "thinking_tokens",
    "latency_ms",
    "cost_usd",
    "cost_usd_nocache",
    "stop_reason",
    "parsed_ok",
)
CELL_IGNORED = {
    "replayed",
    "queue_wait_ms",
}  # the only fields that legitimately differ between live and replay


def replay_calls(
    run_id: str, tickets: list[Ticket], repeat: int = 0, store: CassetteStore | None = None
) -> list[tuple[str, ModelCall]]:
    """Re-issue every recorded answer call of the run in replay mode (a miss raises ReplayMiss)."""
    client = LLMClient("replay", run_id + "-replay", store=store)
    by_id = {t.id: t for t in tickets}
    rules = load_version("v1")
    out = []
    for live in read_calls(run_id):
        if live.role != "answer":
            continue
        ticket = by_id[live.ticket_id]
        req = build_request(ticket, live.model, live.effort, repeat=repeat)  # type: ignore[arg-type]

        def valid(text: str, task=ticket.task_type) -> bool:
            return check_format(task, text, rules, stop_reason="end_turn").passed

        out.append((run_id, client.call(req, ticket_id=ticket.id, validate=valid).call))
    return out


def compare(
    run_id: str, tickets: list[Ticket], repeat: int = 0, store: CassetteStore | None = None
) -> list[str]:
    """Differences between the live record and its replay; empty means exact reproduction."""
    problems: list[str] = []
    live = [c for c in read_calls(run_id) if c.role == "answer"]
    replayed = replay_calls(run_id, tickets, repeat, store)
    if len(live) != len(replayed):
        return [f"{len(live)} live calls but {len(replayed)} replayed"]
    for a, (_, b) in zip(live, replayed, strict=True):
        for f in CALL_FIELDS:
            if getattr(a, f) != getattr(b, f):
                problems.append(
                    f"{a.ticket_id} {a.config_id}: {f} live={getattr(a, f)!r} replay={getattr(b, f)!r}"
                )
        if not b.replayed:
            problems.append(f"{a.ticket_id} {a.config_id}: replay did not come from a cassette")
    live_cells, _ = cells_from_calls([(run_id, c) for c in live], tickets, store)
    replay_cells, _ = cells_from_calls(replayed, tickets, store)
    if _canonical(live_cells) != _canonical(replay_cells):
        problems.append("metrics cells differ between live and replay")
    return problems


def _canonical(cells: list[Cell]) -> list[dict]:
    return sorted(
        ({k: v for k, v in c.model_dump().items() if k not in CELL_IGNORED} for c in cells),
        key=lambda d: (d["ticket_id"], d["config_id"]),
    )
