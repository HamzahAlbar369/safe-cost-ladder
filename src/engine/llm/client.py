"""Single gateway for Anthropic calls: record/replay (SPEC §6.5), cost, budget guard, cache layout (§6.2).

Keys come only from the environment (loaded from .env). They are never printed, logged or stored.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv

from engine import runinfo
from engine.contracts import (
    Cassette,
    LLMRequest,
    LLMResponse,
    ModelCall,
    Provider,
    Role,
    SpendEntry,
    Usage,
    utcnow,
)
from engine.llm.pricing import ROOT, ModelPrice, PriceBook, cost_usd, cost_usd_nocache, pricebook

Mode = Literal["live", "replay", "auto"]
CASSETTES = ROOT / "cassettes"
SPEND_LEDGER = ROOT / "runs" / "spend.jsonl"


class BudgetExceeded(RuntimeError):
    pass


class ReplayMiss(RuntimeError):
    pass


class MissingKey(RuntimeError):
    pass


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_key(name: str) -> str:
    """Return a key from the environment (after loading .env). Never echo it."""
    load_dotenv(ROOT / ".env", override=False)
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingKey(f"{name} is not set (expected in .env); live mode needs it, replay mode does not")
    return value


# --------------------------------------------------------------------------- ledger / budget guard


class Ledger:
    """Append-only spend ledger (runs/spend.jsonl) with a separate budget per provider."""

    def __init__(self, path: Path = SPEND_LEDGER, budgets: dict[str, float] | None = None) -> None:
        self.path = path
        self.budgets = budgets if budgets is not None else pricebook().budgets

    def entries(self) -> list[SpendEntry]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [SpendEntry.model_validate_json(line) for line in lines if line.strip()]

    def spent(self, provider: Provider) -> float:
        return sum(e.cost_usd for e in self.entries() if e.provider == provider)

    def remaining(self, provider: Provider) -> float:
        return self.budgets[provider] - self.spent(provider)

    def check(self, provider: Provider, estimate_usd: float, pending_usd: float = 0.0) -> None:
        left = self.remaining(provider) - pending_usd
        if estimate_usd > left:
            raise BudgetExceeded(
                f"{provider}: estimated ${estimate_usd:.4f} exceeds remaining budget ${left:.4f}"
            )

    def record(self, entry: SpendEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _LEDGER_LOCK, self.path.open("a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")


_LEDGER_LOCK = threading.Lock()


class RunBudget:
    """Per-run cap (the amount Hamzah approved). Reserves each call's worst case before it is sent, so
    concurrent calls can never jointly cross the cap; the reservation is replaced by the actual cost after."""

    def __init__(self, caps: dict[str, float]) -> None:
        self.caps = caps
        self.spent: dict[str, float] = {p: 0.0 for p in caps}
        self.reserved: dict[str, float] = {p: 0.0 for p in caps}
        self._lock = threading.Lock()

    def reserve(self, provider: Provider, estimate_usd: float, ledger: Ledger) -> None:
        with self._lock:
            pending = self.reserved.get(provider, 0.0)
            ledger.check(provider, estimate_usd, pending_usd=pending)
            cap = self.caps.get(provider, 0.0)
            committed = self.spent.get(provider, 0.0) + pending
            if committed + estimate_usd > cap:
                raise BudgetExceeded(
                    f"{provider}: run spend+reserved ${committed:.4f} + worst case "
                    f"${estimate_usd:.4f} would exceed the approved run cap ${cap:.2f}"
                )
            self.reserved[provider] = pending + estimate_usd

    def settle(self, provider: Provider, estimate_usd: float, actual_usd: float) -> None:
        with self._lock:
            self.reserved[provider] = self.reserved.get(provider, 0.0) - estimate_usd
            self.spent[provider] = self.spent.get(provider, 0.0) + actual_usd


def guard(ledger: Ledger, run_budget: RunBudget | None, provider: Provider, estimate_usd: float) -> None:
    """Budget guard run before every paid call."""
    if run_budget is not None:
        run_budget.reserve(provider, estimate_usd, ledger)
    else:
        ledger.check(provider, estimate_usd)


def settle(run_budget: RunBudget | None, provider: Provider, estimate_usd: float, actual_usd: float) -> None:
    if run_budget is not None:
        run_budget.settle(provider, estimate_usd, actual_usd)


# --------------------------------------------------------------------------- cassettes


class CassetteStore:
    def __init__(self, root: Path = CASSETTES) -> None:
        self.root = root

    def path(self, provider: Provider, request_hash: str) -> Path:
        return self.root / provider / f"{request_hash}.json"

    def get(self, provider: Provider, request_hash: str) -> Cassette | None:
        p = self.path(provider, request_hash)
        if not p.exists():
            return None
        return Cassette.model_validate_json(p.read_text(encoding="utf-8"))

    def put(self, cassette: Cassette) -> None:
        p = self.path(cassette.provider, cassette.request_hash)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(cassette.model_dump_json(indent=1), encoding="utf-8")

    def all(self) -> list[Path]:
        return sorted(self.root.glob("*/*.json")) if self.root.exists() else []


def request_record(req: LLMRequest) -> dict[str, Any]:
    """What gets hashed and stored. The system prompt is represented by its sha256."""
    rec = req.model_dump()
    rec["system_sha256"] = sha256(rec.pop("system"))
    return rec


def hash_record(record: dict[str, Any]) -> str:
    return sha256(canonical_json(record))


def request_hash(req: LLMRequest) -> str:
    return hash_record(request_record(req))


# --------------------------------------------------------------------------- estimates


def estimate_tokens(text: str) -> int:
    """Conservative upper bound on tokens (UTF-8 bytes / 2; Arabic is byte-heavy, so this over-counts)."""
    return math.ceil(len(text.encode("utf-8")) / 2)


def worst_case_cost(price: ModelPrice, req: LLMRequest) -> float:
    """Upper bound for the budget guard: whole prompt at the dearer of input/cache-write, full max_tokens."""
    prompt = estimate_tokens(req.system) + estimate_tokens(req.user)
    in_rate = max(price.input, price.cache_write_5m)
    return (prompt * in_rate + req.max_tokens * price.output) / 1_000_000


# --------------------------------------------------------------------------- client


class CallResult:
    def __init__(self, response: LLMResponse | None, call: ModelCall) -> None:
        self.response = response
        self.call = call


class LLMClient:
    def __init__(
        self,
        mode: Mode,
        run_id: str,
        *,
        ledger: Ledger | None = None,
        store: CassetteStore | None = None,
        run_budget: RunBudget | None = None,
        prices: PriceBook | None = None,
        sdk_client: Any = None,
        allow_dirty: bool = False,
    ) -> None:
        self.mode = mode
        self.run_id = run_id
        self.ledger = ledger or Ledger()
        self.store = store or CassetteStore()
        self.run_budget = run_budget
        self.prices = prices or pricebook()
        self._sdk = sdk_client
        self._tree_ok = allow_dirty  # only `engine smoke` may run paid calls on a dirty tree (D0.8)

    # -- public

    def call(
        self,
        req: LLMRequest,
        *,
        ticket_id: str,
        role: Role = "answer",
        validate: Callable[[str], bool] | None = None,
    ) -> CallResult:
        price = self.prices.price(req.model)
        if price.max_prompt_tokens is not None:
            est = estimate_tokens(req.system) + estimate_tokens(req.user)
            if est > price.max_prompt_tokens:
                raise ValueError(f"{req.model}: prompt estimate {est} exceeds {price.max_prompt_tokens}")
        h = request_hash(req)
        cassette = self.store.get("anthropic", h) if self.mode != "live" else None
        error: str | None = None
        response: LLMResponse | None = None
        replayed = cassette is not None

        if cassette is not None:
            response = LLMResponse.model_validate(cassette.response)
        elif self.mode == "replay":
            raise ReplayMiss(f"no cassette for request {h} ({req.model}, {req.effort}, ticket {ticket_id})")
        else:
            response, error = self._live(req, h, price)

        usage = response.usage if response else Usage()
        cost = cost_usd(price, usage)
        call = ModelCall(
            call_id=uuid.uuid4().hex,
            ticket_id=ticket_id,
            run_id=self.run_id,
            config_id=self.prices.config_id(req.model, req.effort),
            model=req.model,
            effort=req.effort,
            role=role,
            request_hash=h,
            input_tokens=usage.input_tokens,
            cache_creation_tokens=usage.cache_creation_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            output_tokens=usage.output_tokens,
            thinking_tokens=usage.thinking_tokens,
            latency_ms=response.latency_ms if response else 0.0,
            cost_usd=cost,
            cost_usd_nocache=cost_usd_nocache(price, usage),
            stop_reason=response.stop_reason if response else None,
            parsed_ok=bool(response and validate and validate(response.text)),
            error=error,
            replayed=replayed,
        )
        return CallResult(response, call)

    # -- live path

    def _sdk_client(self) -> Any:
        if self._sdk is None:
            import anthropic

            self._sdk = anthropic.Anthropic(api_key=load_key("ANTHROPIC_API_KEY"), max_retries=1)
        return self._sdk

    def _require_clean_tree(self) -> None:
        if not self._tree_ok:
            runinfo.require_clean_tree()
            self._tree_ok = True

    @staticmethod
    def build_params(req: LLMRequest) -> dict[str, Any]:
        """SPEC §6.2: one static system block (cached), user = task type + ticket text only."""
        block: dict[str, Any] = {"type": "text", "text": req.system}
        if req.cache:
            block["cache_control"] = {"type": "ephemeral"}
        params: dict[str, Any] = {
            "model": req.model,
            "max_tokens": req.max_tokens,
            "system": [block],
            "messages": [{"role": "user", "content": req.user}],
            "output_config": {"effort": req.effort},
        }
        if req.thinking == "adaptive":
            params["thinking"] = {"type": "adaptive"}
        return params

    def _live(self, req: LLMRequest, h: str, price: ModelPrice) -> tuple[LLMResponse | None, str | None]:
        import anthropic

        sdk = self._sdk_client()
        worst = worst_case_cost(price, req)
        self._require_clean_tree()
        guard(self.ledger, self.run_budget, "anthropic", worst)
        t0 = time.perf_counter()
        try:
            with sdk.messages.stream(**self.build_params(req)) as stream:
                msg = stream.get_final_message()
        except anthropic.APIStatusError as e:
            settle(self.run_budget, "anthropic", worst, 0.0)
            return None, f"{type(e).__name__} {e.status_code}: {_safe_error_message(e)}"
        except anthropic.APIConnectionError as e:
            settle(self.run_budget, "anthropic", worst, 0.0)
            return None, f"{type(e).__name__}"
        latency_ms = (time.perf_counter() - t0) * 1000
        response = LLMResponse(
            text="".join(b.text for b in msg.content if b.type == "text"),
            stop_reason=msg.stop_reason,
            usage=usage_from_sdk(msg.usage),
            latency_ms=round(latency_ms, 1),
            served_model=msg.model,
        )
        cost = cost_usd(price, response.usage)
        self.ledger.record(
            SpendEntry(
                provider="anthropic", run_id=self.run_id, request_hash=h, model=req.model, cost_usd=cost
            )
        )
        settle(self.run_budget, "anthropic", worst, cost)
        self.store.put(
            Cassette(
                request_hash=h,
                provider="anthropic",
                request=request_record(req),
                response=response.model_dump(),
                recorded_at=utcnow(),
            )
        )
        return response, None


def usage_from_sdk(u: Any) -> Usage:
    details = getattr(u, "output_tokens_details", None)
    return Usage(
        input_tokens=u.input_tokens or 0,
        cache_creation_tokens=u.cache_creation_input_tokens or 0,
        cache_read_tokens=u.cache_read_input_tokens or 0,
        output_tokens=u.output_tokens or 0,
        thinking_tokens=getattr(details, "thinking_tokens", None) if details else None,
    )


def _safe_error_message(e: Exception) -> str:
    body = getattr(e, "body", None)
    if isinstance(body, dict):
        err = body.get("error", {})
        if isinstance(err, dict) and "message" in err:
            return str(err["message"])[:300]
    return str(e)[:300]
