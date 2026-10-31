"""Jev router (SPEC §6.4, D3.3): zero-shot typed questions over the ticket text only (no policy document).

Mapping, declared in DECISIONS.md D3.3 BEFORE the run: an adjudicate ticket goes straight to opus-low iff
P(complexity = "complex") >= tau, with tau chosen on dev by the same rule as the local router (lowest headline
CPST meeting every floor). Otherwise the normal O1 path runs. `needs_calculation` and `missing_information` are
recorded for the report only; they do not enter the mapping. Jev's cost and latency are added to every
adjudicate ticket it is asked about (it runs before the cascade, SPEC §7.4).
"""

from __future__ import annotations

import json

from engine.contracts import JevRequest, JevResponse, Ticket
from engine.eval.matrix import runs_dir
from engine.llm.client import Ledger, RunBudget
from engine.llm.jev import JEV_MODEL, JevClient, JevError, choice, jev_request_hash, noul

RUN_ID = "jev-router-dev-1"
QUESTIONS = {
    "complexity": choice(
        "A customer ticket asks a motor-insurance claims desk to decide a claim (approve, partial, deny or "
        "need more information) and the payout. How hard is it to decide this claim correctly?",
        {
            "simple": "one clear situation; a single rule decides it; at most one simple calculation",
            "moderate": "a payout calculation with a deductible or a fault share, or one exclusion to check",
            "complex": "several interacting conditions: exclusions or licence/authorisation questions, caps or "
            "total loss, conflicting or missing documents or amounts, late reporting, unusual parties",
        },
    ),
    "needs_calculation": noul("Does deciding this claim require calculating a payout amount?"),
    "missing_information": noul("Is information or a document needed to decide this claim missing?"),
}


def request(t: Ticket, repeat: int = 0) -> JevRequest:
    return JevRequest(model=JEV_MODEL, state=t.text, questions=QUESTIONS, repeat=repeat)


def warmup_request() -> JevRequest:
    """Untimed cold-start call (Phase 0: first call 42.8 s); its result is not used."""
    return JevRequest(model=JEV_MODEL, state="warm-up", questions=QUESTIONS, repeat=1)


def p_complex(resp: JevResponse) -> float:
    return float(resp.answers["complexity"]["probabilities"].get("complex", 0.0))


def estimate(tickets: list[Ticket]) -> float:
    jc = JevClient("replay", "estimate")
    return jc.estimate(warmup_request()) + sum(jc.estimate(request(t)) for t in tickets)


def run(tickets: list[Ticket], mode: str, cap_usd: float | None = None) -> dict[str, JevResponse]:
    """Ask Jev about every ticket (live calls record cassettes; replay needs no key). Writes runs/<RUN_ID>/jev.jsonl."""
    budget = RunBudget({"openrouter": cap_usd}) if cap_usd is not None else None
    jc = JevClient(mode, RUN_ID, ledger=Ledger(), run_budget=budget)
    out_dir = runs_dir(RUN_ID)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, answers = [], {}
    for item_id, req in [("warm-up", warmup_request()), *((t.id, request(t)) for t in tickets)]:
        try:
            resp, replayed = jc.ask(req)
            err = None
        except JevError as e:  # one retry (retry budget 1, SPEC §8), then record the failure
            try:
                resp, replayed = jc.ask(req)
                err = None
            except JevError as e2:
                resp, replayed, err = None, False, f"{e} / {e2}"
        rows.append(
            {
                "request_hash": jev_request_hash(req),
                "item_id": item_id,
                "role": "probe" if item_id == "warm-up" else "router",
                "replayed": replayed,
                "error": err,
                "response": resp.model_dump(mode="json") if resp else None,
            }
        )
        if resp is not None and item_id != "warm-up":
            answers[item_id] = resp
    if mode != "replay":
        (out_dir / "jev.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
        )
    return answers
