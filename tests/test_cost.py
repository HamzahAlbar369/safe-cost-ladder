"""Cost accounting against hand-computed fixtures (SPEC §11.3). Prices: config/models.yaml."""

import pytest

from engine.contracts import Usage
from engine.llm.pricing import cost_usd, cost_usd_nocache, load_pricebook

PB = load_pricebook()


def test_prices_match_spec_2_2():
    h, s, o = (PB.price(m) for m in ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"))
    assert (h.input, h.output, h.cache_write_5m, h.cache_read) == (0.10, 0.50, 0.125, 0.01)
    assert (s.input, s.output, s.cache_write_5m, s.cache_read) == (2.00, 10.00, 2.50, 0.10)
    assert (o.input, o.output, o.cache_write_5m, o.cache_read) == (4.00, 20.00, 5.00, 0.20)
    assert PB.budgets == {"anthropic": 100.0, "openrouter": 5.0}


def test_opus_cost_hand_computed():
    # 100 uncached in @4 + 2000 cache write @5 + 0 read + 300 out @20
    # = 400 + 10000 + 6000 = 16400 / 1e6 = 0.0164
    u = Usage(input_tokens=100, cache_creation_tokens=2000, cache_read_tokens=0, output_tokens=300)
    assert cost_usd(PB.price("claude-opus-5-5"), u) == pytest.approx(0.0164)
    # no-cache headline: 2100 @4 + 300 @20 = 8400 + 6000 = 14400 -> 0.0144
    assert cost_usd_nocache(PB.price("claude-opus-5-5"), u) == pytest.approx(0.0144)


def test_sonnet_cache_read_hand_computed():
    # 150 in @2 + 2000 read @0.10 + 1000 out @10 = 300 + 200 + 10000 = 10500 -> 0.0105
    u = Usage(input_tokens=150, cache_read_tokens=2000, output_tokens=1000)
    assert cost_usd(PB.price("claude-sonnet-5-5"), u) == pytest.approx(0.0105)


def test_haiku_short_and_long_context():
    # short: 1000 in @0.10 + 500 out @0.50 = 100 + 250 = 350 -> 0.00035
    u = Usage(input_tokens=1000, output_tokens=500)
    assert cost_usd(PB.price("claude-haiku-5-5"), u) == pytest.approx(0.00035)
    # >100K prompt tokens (cache reads count): long-context rates for the whole request
    # 1000 in @0.50 + 100000 read @0.05 + 500 out @2.50 = 500 + 5000 + 1250 = 6750 -> 0.00675
    big = Usage(input_tokens=1000, cache_read_tokens=100_000, output_tokens=500)
    assert cost_usd(PB.price("claude-haiku-5-5"), big) == pytest.approx(0.00675)


def test_thinking_tokens_do_not_double_bill():
    a = Usage(input_tokens=10, output_tokens=300, thinking_tokens=200)
    b = Usage(input_tokens=10, output_tokens=300)
    p = PB.price("claude-opus-5-5")
    assert cost_usd(p, a) == cost_usd(p, b)


def test_config_ids():
    assert PB.config_id("claude-haiku-5-5", "low") == "haiku-low"
    assert PB.config_id("claude-opus-5-5", "high") == "opus-high"


def test_jev_rate_reproduces_documented_example():
    # Official Decisions API example: 476 input tokens -> usage.cost 0.000019992
    assert 476 * PB.price("typesafe/jev-1.14").input / 1e6 == pytest.approx(0.000019992)
