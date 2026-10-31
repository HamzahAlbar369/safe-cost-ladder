"""O1 (SPEC §7.3): per-task cheapest config meeting the floor + risk-tiered verification on adjudicate.

Evaluated by counterfactual replay over recorded cells (SPEC §7.4): no API calls. Adjudicate (D3.2):

1. `first` (haiku-low) and `second` (haiku-medium, the V3 second opinion, SPEC §6.3) start in parallel.
2. Wait for `second` until `deadline_s` after the start (never cutting `first` short). If `second` is back by
   the time a decision can be made, accept `first` iff both answers pass V0-V2 AND agree (same decision,
   payout within 1 SAR). If `second` is late, accept `first` iff it passes V0-V2 alone.
3. Otherwise escalate to `top` (opus-low), started at the decision time; its answer is final.

Latency = decision time (+ `top` if escalated). Cost = every call on the path; a late second opinion is
charged in full (conservative: a cancelled stream is not assumed to be refunded). Ablations are options:
`second=None` drops V3 (sequential haiku-low -> opus-low on a V0-V2 failure), `checks` drops V2,
`deadline_s=None` is O1 as first specified (wait for both).
"""

from __future__ import annotations

from engine.contracts import Frozen, Ticket
from engine.eval.baselines import CellIndex, Outcome
from engine.eval.cells import Cell
from engine.eval.floors import Floors
from engine.tasks.graders import grade
from engine.tier0 import Tier0, Tier0Result

ALL_CHECKS = ("V0", "V1", "V2")
PAYOUT_TOLERANCE_SAR = 1.0


class O1Options(Frozen):
    first: str = "haiku-low"
    second: str | None = "haiku-medium"  # None = drop V3
    top: str = "opus-low"
    deadline_s: float | None = 6.0  # None = wait for the second opinion however long it takes
    checks: tuple[str, ...] = ALL_CHECKS  # verifier levels that can reject (drop V2 = ("V0", "V1"))
    tier0: bool = True  # Tier 0 (empty reject, duplicate reuse, FAQ table) in front of every task
    direct_top: frozenset[str] = frozenset()  # adjudicate ticket ids a router sends straight to `top` (O2/O3)
    # router cost (USD) and latency (ms) per adjudicate ticket, added before the cascade (SPEC §7.4)
    router_overhead: dict[str, tuple[float, float]] = {}


class Trace(Frozen):
    """Why an adjudicate ticket ended where it did (for the report)."""

    ticket_id: str
    escalated: bool
    reason: (
        str  # "" | "first failed checks" | "second failed checks" | "disagree" | "first failed (second late)"
    )
    second_late: bool


def passes(cell: Cell, checks: tuple[str, ...]) -> bool:
    return not any(level in checks for level in cell.failed_checks)


def agree(a: Cell, b: Cell) -> bool:
    if a.decision is None or a.decision != b.decision:
        return False
    if a.payout_sar is None or b.payout_sar is None:
        return a.payout_sar is None and b.payout_sar is None
    return abs(a.payout_sar - b.payout_sar) <= PAYOUT_TOLERANCE_SAR


def _outcome(t: Ticket, path: list[Cell], final: Cell, latency_ms: float, floors: Floors) -> Outcome:
    return Outcome(
        ticket_id=t.id,
        task=t.task_type,
        language=t.language,
        path=tuple(c.config_id for c in path),
        correct=final.correct,
        success=final.correct and latency_ms <= floors.per_task[t.task_type].budget_s * 1000,
        cost_nocache=sum(c.cost_usd_nocache for c in path),
        cost_cached=sum(c.cost_usd for c in path),
        latency_ms=latency_ms,
    )


def adjudicate(t: Ticket, index: CellIndex, floors: Floors, o: O1Options) -> tuple[Outcome, Trace]:
    a, top = index[(t.id, o.first)], index[(t.id, o.top)]
    if t.id in o.direct_top:  # router: confident this ticket needs the top rung
        return _outcome(t, [top], top, top.latency_ms, floors), Trace(
            ticket_id=t.id, escalated=False, reason="routed to top", second_late=False
        )
    if o.second is None:
        ok, reason, late, path, decided = passes(a, o.checks), "first failed checks", False, [a], a.latency_ms
    else:
        b = index[(t.id, o.second)]
        path = [a, b]
        deadline = float("inf") if o.deadline_s is None else o.deadline_s * 1000
        late = b.latency_ms > max(a.latency_ms, deadline)
        if late:
            decided = max(a.latency_ms, deadline)
            ok, reason = passes(a, o.checks), "first failed (second late)"
        else:
            decided = max(a.latency_ms, b.latency_ms)
            ok = passes(a, o.checks) and passes(b, o.checks) and agree(a, b)
            reason = (
                "first failed checks"
                if not passes(a, o.checks)
                else "second failed checks"
                if not passes(b, o.checks)
                else "disagree"
            )
    if ok:
        return _outcome(t, path, a, decided, floors), Trace(
            ticket_id=t.id, escalated=False, reason="", second_late=late
        )
    return _outcome(t, [*path, top], top, decided + top.latency_ms, floors), Trace(
        ticket_id=t.id, escalated=True, reason=reason, second_late=late
    )


def run_o1(
    tickets: list[Ticket], index: CellIndex, floors: Floors, static: dict[str, str], o: O1Options
) -> tuple[list[Outcome], list[Trace]]:
    """`static` = per task, the cheapest config meeting the floor (B3's choice); used for faq/intent/extract,
    which have no verification step (V0 never failed for those configs on dev)."""
    outcomes, traces = [], []
    tier0 = Tier0() if o.tier0 else None
    by_id: dict[str, Outcome] = {}
    for t in tickets:
        hit = tier0.check(t.id, t.task_type, t.text) if tier0 else None
        if hit is not None and hit.action != "pass":
            out = _tier0_outcome(t, hit, by_id)
        elif t.task_type == "adjudicate":
            out, tr = adjudicate(t, index, floors, o)
            if t.id in o.router_overhead:
                cost, ms = o.router_overhead[t.id]
                lat = out.latency_ms + ms
                budget_ms = floors.per_task[t.task_type].budget_s * 1000
                out = out.model_copy(
                    update={
                        "cost_nocache": out.cost_nocache + cost,
                        "cost_cached": out.cost_cached + cost,
                        "latency_ms": lat,
                        "success": out.correct and lat <= budget_ms,
                    }
                )
            traces.append(tr)
        else:
            cell = index[(t.id, static[t.task_type])]
            out = _outcome(t, [cell], cell, cell.latency_ms, floors)
        outcomes.append(out)
        by_id[t.id] = out
    return outcomes, traces


def _tier0_outcome(t: Ticket, hit: Tier0Result, by_id: dict[str, Outcome]) -> Outcome:
    """A Tier 0 answer: no model call, cost 0, latency 0 (local work is microseconds)."""
    if hit.action == "duplicate":
        correct = by_id[hit.duplicate_of].correct  # same text and task -> same gold (deterministic rules)
    elif hit.action == "faq":
        correct = grade("faq", t.gold.model_dump(mode="json"), {"answer": hit.faq_answer}).correct
    else:  # reject_empty: no answer, a failed task
        correct = False
    return Outcome(
        ticket_id=t.id,
        task=t.task_type,
        language=t.language,
        path=(f"tier0:{hit.action}",),
        correct=correct,
        success=correct,
        cost_nocache=0.0,
        cost_cached=0.0,
        latency_ms=0.0,
    )
