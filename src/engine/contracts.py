"""Pydantic v2 data contracts (SPEC §5): calls, ledger, cassettes, run manifest, smoke, and Phase 1 data."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


# --- Phase 1 data (SPEC §3.1, §4, §5). FICTIONAL. -----------------------------------------------

TaskType = Literal["faq", "intent", "extract", "adjudicate"]
Level = Literal["L1", "L2", "L3", "L4", "L5"]
Language = Literal["en", "ar"]
Dialect = Literal["msa", "saudi", "mixed", "none"]  # "none" for English
Split = Literal["dev", "heldout", "shifted"]
Scenario = Literal["normal", "adversarial", "policy_change"]
DecisionLabel = Literal["approve", "partial", "deny", "need_info"]
IntentLabel = Literal[
    "new_claim",
    "claim_status",
    "coverage_question",
    "document_submission",
    "complaint",
    "policy_change",
    "payment_issue",
    "fault_dispute",
    "other",
]


class Case(Frozen):
    """Facts of one claim. Gold is computed from these (rules engine), never from text (D1.6)."""

    claim_type: Literal["own_damage", "third_party_claim"]
    cover: Literal["TPL", "COMP"]
    peril: str = "collision"  # or an out_of_scope_perils key (R0)
    policy_number: str
    policy_end_date: date
    accident_date: date
    report_date: date  # date the claim was reported to the insurer
    late_justification: str | None = None  # late_report_justifications key
    report_source: Literal["najm", "traffic_police"]
    report_number: str | None = None
    other_party: Literal["insured", "uninsured", "unknown", "none"]
    fault_share: int | None = None  # policyholder's share, percent
    damage_amount_sar: int | None = None  # own repair estimate (own_damage) or third party's damage
    sum_insured_sar: int | None = None  # COMP schedule value
    technical_total_loss: bool = False
    documents: tuple[str, ...] = ()  # required_documents keys provided
    conflict_damage_sar: int | None = None  # a second, contradicting damage amount stated (R7)
    violations: tuple[str, ...] = ()  # third_party_deny / third_party_recovery keys
    violation_caused_accident: bool = False  # CMIR 7.16: the report shows the violation caused it
    licence_status: Literal["valid", "none", "expired", "wrong_class", "forfeited"] = "valid"
    licence_renewal_date: date | None = None  # for an expired licence
    driver: str = "insured"  # authorised_drivers key, or "unauthorised_<who>"


class TraceStep(Frozen):
    rule: str
    check: str
    fired: bool
    detail: str = ""


class AdjudicateGold(Frozen):
    decision: DecisionLabel
    payout_sar: int
    reasons: tuple[str, ...]
    inputs: dict[str, Any]


class Adjudication(Frozen):
    gold: AdjudicateGold
    trace: tuple[TraceStep, ...]


class FaqGold(Frozen):
    answer: int | str


class IntentGold(Frozen):
    intent: IntentLabel


class ExtractGold(Frozen):
    policy_number: str | None
    accident_date: date | None
    report_number: str | None
    damage_amount_sar: int | None
    fault_share: int | None


class TicketMeta(Frozen):
    rule_ids: tuple[str, ...] = ()
    distractors: tuple[str, ...] = ()
    scenario: Scenario = "normal"
    adversarial_kind: str | None = None
    facts: tuple[str, ...] = ()  # gold-relevant surface values (fact-preservation check)
    case: Case | None = None
    trace: tuple[TraceStep, ...] = ()
    faq_key: str | None = None
    design: str = ""  # sampler scenario name (for the review file and QA)


class Ticket(Frozen):
    id: str
    split: Split
    task_type: TaskType
    level: Level
    language: Language
    dialect: Dialect
    template_family: str
    rules_version: Literal["v1", "v2"]
    parallel_pair_id: str | None = None
    text: str
    gold: AdjudicateGold | FaqGold | IntentGold | ExtractGold
    meta: TicketMeta

    @model_validator(mode="after")
    def _gold_matches_task(self) -> Ticket:
        expected = {
            "faq": FaqGold,
            "intent": IntentGold,
            "extract": ExtractGold,
            "adjudicate": AdjudicateGold,
        }
        if not isinstance(self.gold, expected[self.task_type]):
            raise ValueError(f"{self.id}: gold type does not match task {self.task_type}")
        return self
