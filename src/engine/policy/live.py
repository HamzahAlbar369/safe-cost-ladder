"""O1 run LIVE (SPEC §7.6: `engine final` runs the chosen policy live on held-out).

Same decisions as the replay in `policy.cascade` (same `passes` / `agree`, same options), but with real calls,
real threads and wall-clock time:
- faq / intent / extract: one call to the task's frozen static config;
- adjudicate: `first` and `second` are sent at the same moment; if `first` fails V0-V2, `top` starts at
  once (D3.5); otherwise O1 waits for `second` until max(first's return, D) from the start; accept `first`
  iff both pass and agree (second in time) or iff `first` passes (second late); else `top`. A late `second`
  is still awaited after the decision, outside the measured latency, so it is charged in full (as in replay).
Latency = wall clock from the start of the ticket to the decision (+ `top`). API errors: the SDK retries once
(`max_retries=1`, SPEC §8); a call with no response counts as failing V0. Every call is billed through
`LLMClient` (budget guard, ledger, cassette).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from engine.contracts import Frozen, ModelCall, Role, Ticket
from engine.eval.baselines import Outcome
from engine.eval.cells import Cell, cell_from_call
from engine.eval.floors import Floors
from engine.policy.cascade import O1Options, Trace, agree, passes


class LiveCall(Frozen):
    cell: Cell | None  # None = no response (API error after the SDK's one retry)
    calls: tuple[ModelCall, ...]


Caller = Callable[[Ticket, str, Role], LiveCall]  # (ticket, config_id, role) -> graded call


def make_caller(client, repeat: int) -> Caller:
    """Production caller: build the request exactly as the matrix does (the ticket's rules version picks the
    policy document), with a separate recording epoch so a live run is never served from matrix cassettes."""
    from engine.eval.matrix import cell_request
    from engine.tasks.request import configs

    by_id = {cid: (m, e) for m, e, cid in configs()}

    def call(ticket: Ticket, config_id: str, role: Role) -> LiveCall:
        model, effort = by_id[config_id]
        res = client.call(cell_request((ticket, model, effort), repeat), ticket_id=ticket.id, role=role)
        cell = cell_from_call(ticket, res.call, res.response) if res.response is not None else None
        return LiveCall(cell=cell, calls=(res.call,))

    return call


def _ok(c: LiveCall, checks: tuple[str, ...]) -> bool:
    return c.cell is not None and passes(c.cell, checks)


class LiveResult(Frozen):
    outcome: Outcome
    trace: Trace | None
    calls: tuple[ModelCall, ...]


def _outcome(
    t: Ticket, path: list[str], final: LiveCall, calls: list[ModelCall], ms: float, floors: Floors
) -> Outcome:
    correct = final.cell is not None and final.cell.correct
    return Outcome(
        ticket_id=t.id,
        task=t.task_type,
        language=t.language,
        path=tuple(path),
        correct=correct,
        success=correct and ms <= floors.per_task[t.task_type].budget_s * 1000,
        cost_nocache=sum(c.cost_usd_nocache for c in calls),
        cost_cached=sum(c.cost_usd for c in calls),
        latency_ms=ms,
    )


def run_ticket(
    t: Ticket, caller: Caller, floors: Floors, static: dict[str, str], o: O1Options, pool: ThreadPoolExecutor
) -> LiveResult:
    start = time.perf_counter()

    def elapsed_ms() -> float:
        return (time.perf_counter() - start) * 1000

    if t.task_type != "adjudicate":
        c = caller(t, static[t.task_type], "answer")
        ms = elapsed_ms()
        return LiveResult(
            outcome=_outcome(t, [static[t.task_type]], c, list(c.calls), ms, floors),
            trace=None,
            calls=c.calls,
        )

    fa: Future[LiveCall] = pool.submit(caller, t, o.first, "answer")
    fb: Future[LiveCall] = pool.submit(caller, t, o.second, "verify")
    a = fa.result()
    late = False
    if o.escalate_early and not _ok(a, o.checks):
        ok, reason = False, "first failed checks"
    else:
        # first is back now, so the decision point is max(now, D) from the start
        timeout = None if o.deadline_s is None else max(o.deadline_s - elapsed_ms() / 1000, 0.0)
        try:
            b = fb.result(timeout=timeout)
        except FutureTimeout:
            late, b = True, None
        if late:
            ok, reason = _ok(a, o.checks), "first failed (second late)"
        else:
            assert b is not None
            ok = _ok(a, o.checks) and _ok(b, o.checks) and agree(a.cell, b.cell)  # type: ignore[arg-type]
            reason = (
                "first failed checks"
                if not _ok(a, o.checks)
                else "second failed checks"
                if not _ok(b, o.checks)
                else "disagree"
            )
    path, final, ms = [o.first, o.second], a, 0.0
    if ok:
        ms = elapsed_ms()
    else:
        top = caller(t, o.top, "answer")
        ms = elapsed_ms()
        path, final = [*path, o.top], top
    b_done = fb.result()  # a late second opinion is still charged in full; not part of the latency
    calls = [*a.calls, *b_done.calls, *(final.calls if final is not a else ())]
    trace = Trace(ticket_id=t.id, escalated=not ok, reason="" if ok else reason, second_late=late)
    return LiveResult(outcome=_outcome(t, path, final, calls, ms, floors), trace=trace, calls=tuple(calls))


def run_live(
    tickets: list[Ticket],
    caller: Caller,
    floors: Floors,
    static: dict[str, str],
    o: O1Options,
    *,
    concurrency: int = 4,
    on_result: Callable[[LiveResult], None] | None = None,
) -> list[LiveResult]:
    """`concurrency` tickets in flight; each adjudicate ticket uses up to 3 calls of its own pool."""
    if o.tier0 or o.direct_top or o.router_overhead:
        raise ValueError("live O1 runs the final policy only: no Tier 0, no router (D3.4, D4.3)")
    with (
        ThreadPoolExecutor(max_workers=2 * concurrency) as calls_pool,
        ThreadPoolExecutor(concurrency) as tickets_pool,
    ):

        def one(t: Ticket) -> LiveResult:
            r = run_ticket(t, caller, floors, static, o, calls_pool)
            if on_result:
                on_result(r)
            return r

        return list(tickets_pool.map(one, tickets))
