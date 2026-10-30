from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.llm.client import CassetteStore, Ledger


class FakeStream:
    def __init__(self, msg):
        self._msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._msg


class FakeAnthropic:
    """Stands in for anthropic.Anthropic; counts calls and returns a fixed message."""

    def __init__(self, text='{"answer": "yes"}', usage=None):
        self.calls: list[dict] = []
        self.text = text
        self.usage = usage or SimpleNamespace(
            input_tokens=100,
            cache_creation_input_tokens=2000,
            cache_read_input_tokens=0,
            output_tokens=300,
            output_tokens_details=SimpleNamespace(thinking_tokens=200),
        )
        self.messages = SimpleNamespace(stream=self._stream)

    def _stream(self, **params):
        self.calls.append(params)
        msg = SimpleNamespace(
            content=[
                SimpleNamespace(type="thinking", thinking=""),
                SimpleNamespace(type="text", text=self.text),
            ],
            stop_reason="end_turn",
            usage=self.usage,
            model=params["model"],
        )
        return FakeStream(msg)


@pytest.fixture
def tmp_store(tmp_path):
    return CassetteStore(tmp_path / "cassettes")


@pytest.fixture
def tmp_ledger(tmp_path):
    return Ledger(tmp_path / "spend.jsonl", budgets={"anthropic": 100.0, "openrouter": 5.0})
