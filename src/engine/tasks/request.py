"""Build the Anthropic request for one (ticket, config) pair (SPEC §6.2). Single place, so the probe, the
matrix and the live policies all produce identical cassette keys."""

from __future__ import annotations

from functools import cache
from typing import Any

from engine.contracts import Effort, LLMRequest, TaskType, Ticket
from engine.datagen.rules import load_version
from engine.llm.pricing import PriceBook, pricebook
from engine.tasks.prompts import MAX_TOKENS, system_prompt, user_prompt
from engine.tasks.schemas import schema_for


@cache
def _schema(task: TaskType, version: str) -> dict[str, Any]:
    return schema_for(task, load_version(version))  # parsed once: the matrix builds thousands of requests


def build_request(ticket: Ticket, model: str, effort: Effort, version: str = "v1") -> LLMRequest:
    return LLMRequest(
        model=model,
        effort=effort,
        system=system_prompt(version),
        user=user_prompt(ticket.task_type, ticket.text),
        max_tokens=MAX_TOKENS[ticket.task_type],
        schema_name=ticket.task_type,
        output_schema=_schema(ticket.task_type, version),
        thinking="adaptive",
        cache=True,
    )


def configs(prices: PriceBook | None = None) -> list[tuple[str, Effort, str]]:
    """The 9 configs as (model, effort, config_id), cheapest model first, low -> high."""
    prices = prices or pricebook()
    anthropic = [m for m, p in prices.provider_of.items() if p == "anthropic"]
    return [(m, e, prices.config_id(m, e)) for m in anthropic for e in prices.efforts]  # type: ignore[misc]
