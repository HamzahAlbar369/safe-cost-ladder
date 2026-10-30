"""TypeSafe Jev (System One decision model) via OpenRouter, with the same record/replay + budget path.

Schema confirmed 2026-10-30 from OpenRouter's OpenAPI spec for `POST /api/alpha/decisions`
(https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request.md):
  request  {model, state: str|object|array, questions: {name: question}}
  question noul   {type, instructions, criteria?: {"true", "false"}}
           choice {type, instructions, criteria: {label: guidance}}
           score  {type, instructions, criteria: [level guidance, ...]}
  response {id, model, provider, answers: {name: answer}, usage: {input_tokens, output_tokens, cost}}
  answer   noul {noul: p_yes} · choice {choice, confidence, probabilities} · score {score, confidence,
           probabilities, legend}
Billing: input tokens only; usage.cost (USD) is authoritative.
"""

from __future__ import annotations

import time
from typing import Any, Literal

import httpx

from engine.contracts import Cassette, JevRequest, JevResponse, SpendEntry, utcnow
from engine.llm.client import (
    CassetteStore,
    Ledger,
    Mode,
    ReplayMiss,
    RunBudget,
    canonical_json,
    estimate_tokens,
    hash_record,
    load_key,
)
from engine.llm.pricing import PriceBook, pricebook

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
JEV_MODEL = "typesafe/jev-1.14"


def noul(instructions: str, true: str | None = None, false: str | None = None) -> dict[str, Any]:
    q: dict[str, Any] = {"type": "noul", "instructions": instructions}
    if true is not None and false is not None:
        q["criteria"] = {"true": true, "false": false}
    return q


def choice(instructions: str, criteria: dict[str, str]) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def score(instructions: str, levels: list[str]) -> dict[str, Any]:
    if not levels:
        raise ValueError("score questions need at least one level")
    return {"type": "score", "instructions": instructions, "criteria": levels}


def jev_request_hash(req: JevRequest) -> str:
    return hash_record(req.model_dump())


def jev_payload(req: JevRequest) -> dict[str, Any]:
    return {"model": req.model, "state": req.state, "questions": req.questions}


class JevError(RuntimeError):
    pass


class JevClient:
    def __init__(
        self,
        mode: Mode,
        run_id: str,
        *,
        ledger: Ledger | None = None,
        store: CassetteStore | None = None,
        run_budget: RunBudget | None = None,
        prices: PriceBook | None = None,
        http: httpx.Client | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        self.mode = mode
        self.run_id = run_id
        self.ledger = ledger or Ledger()
        self.store = store or CassetteStore()
        self.run_budget = run_budget
        self.prices = prices or pricebook()
        self._http = http
        self.timeout_s = timeout_s

    def estimate(self, req: JevRequest) -> float:
        tokens = estimate_tokens(canonical_json(jev_payload(req)))
        return tokens * self.prices.price(req.model).input / 1_000_000

    def ask(self, req: JevRequest) -> tuple[JevResponse, bool]:
        """Returns (response, replayed)."""
        h = jev_request_hash(req)
        cassette = self.store.get("openrouter", h) if self.mode != "live" else None
        if cassette is not None:
            return JevResponse.model_validate(cassette.response), True
        if self.mode == "replay":
            raise ReplayMiss(f"no Jev cassette for request {h}")
        return self._live(req, h), False

    def _live(self, req: JevRequest, h: str) -> JevResponse:
        est = self.estimate(req)
        self.ledger.check("openrouter", est)
        if self.run_budget is not None:
            self.run_budget.check("openrouter", est)
        http = self._http or httpx.Client(timeout=self.timeout_s)
        headers = {"Authorization": f"Bearer {load_key('OPENROUTER_API_KEY')}"}
        t0 = time.perf_counter()
        try:
            r = http.post(DECISIONS_URL, json=jev_payload(req), headers=headers)
        except httpx.HTTPError as e:
            raise JevError(f"{type(e).__name__}") from None
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        if r.status_code != 200:
            raise JevError(f"HTTP {r.status_code}: {_error_message(r)}")
        body = r.json()
        usage = body.get("usage", {})
        resp = JevResponse(
            answers=body["answers"],
            served_model=body.get("model", req.model),
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            cost_usd=usage.get("cost"),
            latency_ms=latency_ms,
        )
        cost = resp.cost_usd if resp.cost_usd is not None else self._cost_from_tokens(req, resp)
        self.ledger.record(
            SpendEntry(
                provider="openrouter", run_id=self.run_id, request_hash=h, model=req.model, cost_usd=cost
            )
        )
        if self.run_budget is not None:
            self.run_budget.add("openrouter", cost)
        self.store.put(
            Cassette(
                request_hash=h,
                provider="openrouter",
                request=req.model_dump(),
                response=resp.model_dump(),
                recorded_at=utcnow(),
            )
        )
        return resp

    def _cost_from_tokens(self, req: JevRequest, resp: JevResponse) -> float:
        p = self.prices.price(req.model)
        return (resp.input_tokens * p.input + resp.output_tokens * p.output) / 1_000_000


def answer_value(answer: dict[str, Any]) -> tuple[Any, float | None]:
    """(value, confidence) for any answer type. Noul confidence = max(p, 1-p)."""
    kind: Literal["noul", "choice", "score"] = answer["type"]
    if kind == "noul":
        p = float(answer["noul"])
        return p, max(p, 1 - p)
    if kind == "choice":
        return answer["choice"], answer.get("confidence")
    return float(answer["score"]), answer.get("confidence")


def _error_message(r: httpx.Response) -> str:
    try:
        return str(r.json().get("error", {}).get("message", ""))[:300]
    except ValueError:
        return r.text[:300]
