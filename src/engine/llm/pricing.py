"""Prices from config/models.yaml and USD cost from reported usage (CLAUDE.md: prices live only there)."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from engine.contracts import Provider, Usage

ROOT = Path(__file__).resolve().parents[3]
MODELS_YAML = ROOT / "config" / "models.yaml"
PER_MTOK = 1_000_000


class Rates(BaseModel):
    model_config = ConfigDict(extra="ignore")

    input: float
    output: float
    cache_write_5m: float = 0.0
    cache_read: float = 0.0


class ModelPrice(Rates):
    short: str = ""
    max_prompt_tokens: int | None = None
    long_context: Rates | None = None


class PriceBook(BaseModel):
    verified_on: str
    source: str
    budgets: dict[str, float]
    efforts: list[str]
    models: dict[str, ModelPrice]
    provider_of: dict[str, Provider]

    def price(self, model: str) -> ModelPrice:
        if model not in self.models:
            raise KeyError(f"no price for model {model!r} in config/models.yaml")
        return self.models[model]

    def config_id(self, model: str, effort: str) -> str:
        return f"{self.price(model).short}-{effort}"


def load_pricebook(path: Path = MODELS_YAML) -> PriceBook:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    models: dict[str, ModelPrice] = {}
    provider_of: dict[str, Provider] = {}
    for provider in ("anthropic", "openrouter"):
        for mid, spec in raw[provider]["models"].items():
            models[mid] = ModelPrice(**spec)
            provider_of[mid] = provider
    return PriceBook(
        verified_on=raw["verified_on"],
        source=raw["source"],
        budgets={p: float(raw[p]["budget_usd"]) for p in ("anthropic", "openrouter")},
        efforts=raw["anthropic"]["efforts"],
        models=models,
        provider_of=provider_of,
    )


@cache
def pricebook() -> PriceBook:
    return load_pricebook()


def _rates_for(price: ModelPrice, prompt_tokens: int) -> Rates:
    if price.max_prompt_tokens is not None and prompt_tokens > price.max_prompt_tokens:
        if price.long_context is None:
            raise ValueError("prompt exceeds max_prompt_tokens and no long-context rates are configured")
        return price.long_context
    return price


def cost_usd(price: ModelPrice, usage: Usage) -> float:
    """Actual cost: uncached input, cache writes (5m TTL), cache reads and output at their own rates."""
    r = _rates_for(price, usage.prompt_tokens)
    total = (
        usage.input_tokens * r.input
        + usage.cache_creation_tokens * r.cache_write_5m
        + usage.cache_read_tokens * r.cache_read
        + usage.output_tokens * r.output
    )
    return total / PER_MTOK


def cost_usd_nocache(price: ModelPrice, usage: Usage) -> float:
    """Headline cost (SPEC §7.5): every prompt token at the base input rate."""
    r = _rates_for(price, usage.prompt_tokens)
    return (usage.prompt_tokens * r.input + usage.output_tokens * r.output) / PER_MTOK
