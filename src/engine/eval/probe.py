"""Phase 2 entry check (D0.8): do all three models accept `output_config.format` together with
`output_config.effort` and adaptive thinking, and return schema-valid JSON for all four task schemas?

Four dev items (one per task, English and Arabic mixed) x 3 models x efforts low and high = 24 calls. These
are ordinary matrix requests (same builder), so their cassettes are reused by the matrix runner.
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from engine import runinfo
from engine.contracts import Effort, ModelCall, TaskType, Ticket, utcnow
from engine.datagen.rules import load_version
from engine.eval.data import load_split
from engine.llm.client import LLMClient, Mode, RunBudget
from engine.llm.pricing import ROOT, pricebook
from engine.tasks.graders import grade
from engine.tasks.request import build_request
from engine.tasks.schemas import schema_errors, schema_for

PROBE_EFFORTS: tuple[Effort, ...] = ("low", "high")
# (task, language, level) of the dev item used for each schema; first match in file order.
PROBE_ITEMS: tuple[tuple[TaskType, str, str | None], ...] = (
    ("faq", "en", None),
    ("intent", "ar", None),
    ("extract", "ar", None),
    ("adjudicate", "en", "L4"),
)


class ProbeCall(BaseModel):
    ticket_id: str
    task: str
    config_id: str
    ok: bool  # accepted, end_turn, parsed, schema-valid
    schema_errors: list[str]
    graded_correct: bool | None
    call: ModelCall


def probe_tickets() -> list[Ticket]:
    dev = load_split("dev")
    return [
        next(t for t in dev if t.task_type == task and t.language == lang and level in (None, t.level))
        for task, lang, level in PROBE_ITEMS
    ]


def probe_requests() -> list[tuple[Ticket, str, Effort]]:
    prices = pricebook()
    models = [m for m, p in prices.provider_of.items() if p == "anthropic"]
    return [(t, m, e) for m in models for e in PROBE_EFFORTS for t in probe_tickets()]


def _parse(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return None


def _errors(schema: dict[str, Any], text: str) -> list[str]:
    value = _parse(text)
    return ["not JSON"] if value is None else schema_errors(schema, value)


def _one(client: LLMClient, ticket: Ticket, model: str, effort: Effort) -> ProbeCall:
    schema = schema_for(ticket.task_type, load_version("v1"))
    req = build_request(ticket, model, effort)
    result = client.call(req, ticket_id=ticket.id, validate=lambda text: not _errors(schema, text))
    text = result.response.text if result.response else ""
    errors = _errors(schema, text) if result.response else [result.call.error or "no response"]
    out = _parse(text)
    graded = grade(ticket.task_type, ticket.gold.model_dump(mode="json"), out).correct if out else None
    ok = result.response is not None and result.call.stop_reason == "end_turn" and not errors
    return ProbeCall(
        ticket_id=ticket.id,
        task=ticket.task_type,
        config_id=result.call.config_id,
        ok=ok,
        schema_errors=errors,
        graded_correct=graded,
        call=result.call,
    )


def run(mode: Mode, cap_usd: float) -> tuple[str, list[ProbeCall]]:
    run_id = "probe-" + utcnow().strftime("%Y%m%dT%H%M%SZ")
    client = LLMClient(mode, run_id, run_budget=RunBudget({"anthropic": cap_usd}))
    by_model: dict[str, list[tuple[Ticket, str, Effort]]] = {}
    for item in probe_requests():
        by_model.setdefault(item[1], []).append(item)
    results: list[ProbeCall] = []
    lock = threading.Lock()

    def per_model(items: list[tuple[Ticket, str, Effort]]) -> None:
        for ticket, model, effort in items:  # sequential within a model: the first call warms the cache
            r = _one(client, ticket, model, effort)
            with lock:
                results.append(r)

    with ThreadPoolExecutor(max_workers=len(by_model)) as pool:
        list(pool.map(per_model, by_model.values()))
    return run_id, sorted(results, key=lambda r: (r.config_id, r.task))


def write(run_id: str, calls: list[ProbeCall]) -> Path:
    out = ROOT / "runs" / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "calls.jsonl").write_text("\n".join(c.model_dump_json() for c in calls) + "\n", encoding="utf-8")
    summary = {
        "run_id": run_id,
        "git_sha": runinfo.git_sha(),
        "n_calls": len(calls),
        "n_ok": sum(c.ok for c in calls),
        "cost_usd": round(sum(c.call.cost_usd for c in calls), 6),
        "cost_usd_nocache": round(sum(c.call.cost_usd_nocache for c in calls), 6),
        "failures": [
            {"config": c.config_id, "task": c.task, "errors": c.schema_errors, "stop": c.call.stop_reason}
            for c in calls
            if not c.ok
        ],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return out
