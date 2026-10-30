"""Pydantic v2 data contracts (SPEC §5). Phase 0 subset: calls, ledger, cassettes, run manifest, smoke."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Effort = Literal["low", "medium", "high"]
Role = Literal["answer", "verify", "router", "probe"]
Provider = Literal["anthropic", "openrouter"]
ThinkingMode = Literal["default", "adaptive"]  # "default" = thinking param omitted


def utcnow() -> datetime:
    return datetime.now(UTC)


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Usage(Frozen):
    """Token usage exactly as the provider reported it (never compared across models)."""

    input_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0  # billed output; includes thinking tokens
    thinking_tokens: int | None = None  # breakdown of output_tokens when reported

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_creation_tokens + self.cache_read_tokens


class LLMRequest(Frozen):
    """Everything that determines an Anthropic answer. Hashed into the cassette key (SPEC §6.5)."""

    model: str
    effort: Effort
    system: str
    user: str
    max_tokens: int
    schema_name: str = ""  # identifies the output schema embedded in the prompt
    thinking: ThinkingMode = "default"
    cache: bool = True  # cache_control on the static system block (SPEC §6.2)
    repeat: int = 0  # distinguishes deliberate repeats of an identical request (cache probes)


class LLMResponse(Frozen):
    text: str
    stop_reason: str | None
    usage: Usage
    latency_ms: float
    served_model: str


class Cassette(Frozen):
    """One recorded call. `request` holds a sha256 of the system prompt, not the prompt itself."""

    request_hash: str
    provider: Provider
    request: dict[str, Any]
    response: dict[str, Any]
    recorded_at: datetime


class ModelCall(Frozen):
    """One record per API call (SPEC §5)."""

    call_id: str
    ticket_id: str
    run_id: str
    config_id: str
    model: str
    effort: Effort | None
    role: Role
    request_hash: str
    input_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    output_tokens: int
    thinking_tokens: int | None = None
    latency_ms: float
    cost_usd: float
    cost_usd_nocache: float
    stop_reason: str | None
    parsed_ok: bool
    error: str | None = None
    replayed: bool
    ts: datetime = Field(default_factory=utcnow)


class SpendEntry(Frozen):
    """One line of runs/spend.jsonl. Budgets are tracked per provider."""

    ts: datetime = Field(default_factory=utcnow)
    provider: Provider
    run_id: str
    request_hash: str
    model: str
    cost_usd: float
    note: str = ""


class RunManifest(Frozen):
    run_id: str
    git_sha: str
    config_hash: str
    split: str
    policies: list[str]
    created_at: datetime = Field(default_factory=utcnow)
    spend_usd: dict[str, float]


class JevRequest(Frozen):
    """Decisions request (OpenRouter `POST /api/alpha/decisions`, TypeSafe System One shape)."""

    model: str
    state: str | dict[str, Any]
    questions: dict[str, dict[str, Any]]
    repeat: int = 0


class JevResponse(Frozen):
    answers: dict[str, dict[str, Any]]
    served_model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None  # usage.cost as reported by OpenRouter
    latency_ms: float


class SmokeReport(BaseModel):
    """runs/smoke.json: §2.3 checks 1–7."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    git_sha: str
    created_at: datetime = Field(default_factory=utcnow)
    mode: str
    models_api: dict[str, Any]
    checks: dict[str, Any]
    spend_usd: dict[str, float]
    notes: list[str] = []
