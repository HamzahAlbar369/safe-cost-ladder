"""The 9-config matrix runner (SPEC §7.4): every ticket x every config, recorded once, evaluated by replay.

- Everything goes through `LLMClient` (record/replay, cost, budget guard, clean-tree rule).
- Resumable: cells already in this run's calls.jsonl are skipped, and in `auto` mode any request with a
  cassette is replayed instead of re-sent, so an interrupted run continues where it stopped at no extra cost.
- Parallel within the rate limits: one `Pacer` per model (limits are per model) driven by the response
  headers. Waiting in the pacer is stored as `queue_wait_ms`; `latency_ms` is send-to-receive only.
- Cache warm-up: each (model, task) gets one small real request first (the schema is in the cached prefix,
  and a schema's first call is slow, D2.3), so recorded latencies and cache behaviour are steady-state.
  Warm-up calls are stored with role "probe" and never enter metrics.
"""

from __future__ import annotations

import hashlib
import json
import random
import threading
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from engine.contracts import Effort, ModelCall, RunManifest, TaskType, Ticket
from engine.datagen.rules import load_version
from engine.eval.pacer import Pacer
from engine.llm.client import BudgetExceeded, CassetteStore, Ledger, LLMClient, Mode, RunBudget, request_hash
from engine.llm.pricing import MODELS_YAML, ROOT, pricebook
from engine.tasks.prompts import MAX_TOKENS, system_prompt
from engine.tasks.request import build_request, configs
from engine.verify.v0 import check_format

MAX_ATTEMPTS = (
    3  # data collection only: a cell that errors (no response) is re-sent; policies use their own budget
)
WARMUP_MAX_TOKENS = 64
SHUFFLE_SEED = 20261030
Cell = tuple[Ticket, str, Effort]


class MatrixSummary(BaseModel):
    run_id: str
    split: str
    n_cells: int
    n_recorded: int
    n_replayed: int
    n_live: int
    n_errors: int
    parse_rate: float
    spend_usd: float
    rate_limited: dict[str, int]
    wall_s: float


def runs_dir(run_id: str) -> Path:
    return ROOT / "runs" / run_id


def config_hash(version: str = "v1") -> str:
    """Hash of everything that determines a request besides the ticket: prompts, caps, prices file."""
    parts = [system_prompt(version), json.dumps(MAX_TOKENS, sort_keys=True), MODELS_YAML.read_text("utf-8")]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def plan_cells(tickets: list[Ticket]) -> list[Cell]:
    """All ticket x config cells. Tickets are shuffled (fixed seed) and configs interleaved so every
    (model, task) cache is touched continuously and no model idles behind another."""
    order = list(tickets)
    random.Random(SHUFFLE_SEED).shuffle(order)
    return [(t, model, effort) for t in order for model, effort, _ in configs()]


def pending_live(cells: list[Cell], store: CassetteStore, done: set[tuple[str, str]]) -> list[Cell]:
    prices = pricebook()
    return [
        c
        for c in cells
        if (c[0].id, prices.config_id(c[1], c[2])) not in done
        and store.get("anthropic", request_hash(build_request(*c))) is None
    ]


def load_done(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    calls = [ModelCall.model_validate_json(x) for x in path.read_text("utf-8").splitlines() if x.strip()]
    return {(c.ticket_id, c.config_id) for c in calls if c.role == "answer" and c.error is None}


class _Sink:
    """Append-only calls.jsonl writer shared by the worker threads."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._f = path.open("a", encoding="utf-8")
        self._lock = threading.Lock()

    def write(self, call: ModelCall) -> None:
        with self._lock:
            self._f.write(call.model_dump_json() + "\n")
            self._f.flush()

    def close(self) -> None:
        self._f.close()


def _is_rate_limit(call: ModelCall) -> bool:
    return bool(call.error) and ("429" in call.error[:40] or "RateLimit" in call.error[:40])


def run_matrix(
    split: str,
    tickets: list[Ticket],
    *,
    mode: Mode,
    run_id: str,
    cap_usd: float,
    per_model_concurrency: int,
    git_sha: str,
    progress: Callable[[str], None] = print,
    store: CassetteStore | None = None,
    ledger: Ledger | None = None,
    sdk_client: Any = None,
    out_dir: Path | None = None,
) -> MatrixSummary:
    started = time.perf_counter()
    store = store or CassetteStore()
    out_dir = out_dir or runs_dir(run_id)
    calls_path = out_dir / "calls.jsonl"
    done = load_done(calls_path)
    cells = [c for c in plan_cells(tickets) if (c[0].id, pricebook().config_id(c[1], c[2])) not in done]
    budget = RunBudget({"anthropic": cap_usd})

    def make_client(m: Mode) -> LLMClient:
        return LLMClient(m, run_id, ledger=ledger, store=store, run_budget=budget, sdk_client=sdk_client)

    client = make_client(mode)
    rules = load_version("v1")
    pacers = {m: Pacer(per_model_concurrency) for m, _, _ in configs()}
    sink = _Sink(calls_path)
    live_cells = pending_live(cells, store, done) if mode != "replay" else []
    if live_cells:
        _warm_up(live_cells, make_client("live"), sink, progress)

    counts: Counter[str] = Counter()
    lock = threading.Lock()
    stop = threading.Event()

    def one(cell: Cell) -> None:
        if stop.is_set():
            return
        ticket, model, effort = cell
        req = build_request(ticket, model, effort)

        def valid(text: str) -> bool:
            return check_format(ticket.task_type, text, rules, stop_reason="end_turn").passed

        call = None
        for _ in range(MAX_ATTEMPTS):
            pacer = pacers[model]
            wait_ms = pacer.acquire(req.max_tokens)
            result = None
            try:
                result = client.call(req, ticket_id=ticket.id, validate=valid, queue_wait_ms=wait_ms)
            except BudgetExceeded:
                stop.set()
                raise
            finally:
                limited = result is not None and _is_rate_limit(result.call)
                pacer.release(
                    result.rate_limit if result else None,
                    rate_limited=limited,
                    next_max_tokens=req.max_tokens,
                )
            call = result.call
            if call.replayed:
                call = call.model_copy(update={"queue_wait_ms": 0.0})  # replays never queued
            if result.response is not None:
                break
        assert call is not None
        sink.write(call)
        with lock:
            counts["total"] += 1
            counts["replayed" if call.replayed else "live"] += 1
            counts["errors"] += int(call.error is not None)
            counts["parsed"] += int(call.parsed_ok)
            if counts["total"] % 25 == 0 or counts["total"] == len(cells):
                progress(
                    f"  {counts['total']}/{len(cells)} cells | live {counts['live']} "
                    f"replayed {counts['replayed']} errors {counts['errors']} | "
                    f"spend ${budget.spent['anthropic']:.4f} | {time.perf_counter() - started:.0f}s"
                )

    workers = per_model_concurrency * len(pacers)
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(one, cells))
    finally:
        sink.close()

    total = max(counts["total"], 1)
    summary = MatrixSummary(
        run_id=run_id,
        split=split,
        n_cells=len(cells),
        n_recorded=counts["total"],
        n_replayed=counts["replayed"],
        n_live=counts["live"],
        n_errors=counts["errors"],
        parse_rate=counts["parsed"] / total,
        spend_usd=round(budget.spent["anthropic"], 6),
        rate_limited={m: p.rate_limited for m, p in pacers.items()},
        wall_s=round(time.perf_counter() - started, 1),
    )
    manifest = RunManifest(
        run_id=run_id,
        git_sha=git_sha,
        config_hash=config_hash(),
        split=split,
        policies=["matrix"],
        spend_usd={"anthropic": summary.spend_usd},
    )
    (out_dir / "manifest.json").write_text(
        json.dumps(
            {"manifest": json.loads(manifest.model_dump_json()), "summary": summary.model_dump()}, indent=1
        ),
        encoding="utf-8",
    )
    return summary


def _warm_up(live_cells: list[Cell], client: LLMClient, sink: _Sink, progress: Callable[[str], None]) -> None:
    """One real, tiny request per (model, task) with live work pending, sequential per model. A fresh `repeat`
    makes the key unique so it is always sent (never replayed) and never collides with a matrix cassette."""
    first: dict[tuple[str, TaskType], Cell] = {}
    for cell in live_cells:
        first.setdefault((cell[1], cell[0].task_type), cell)
    repeat = int(time.time())
    progress(f"  warming {len(first)} (model, task) caches")
    by_model: dict[str, list[Cell]] = {}
    for (model, _task), cell in first.items():
        by_model.setdefault(model, []).append(cell)

    def warm(cells: list[Cell]) -> None:
        for ticket, model, _effort in cells:
            req = build_request(ticket, model, "low").model_copy(
                update={"max_tokens": WARMUP_MAX_TOKENS, "repeat": repeat}
            )
            sink.write(client.call(req, ticket_id=ticket.id, role="probe").call)

    with ThreadPoolExecutor(max_workers=len(by_model)) as pool:
        list(pool.map(warm, by_model.values()))
