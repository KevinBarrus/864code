"""测试上下文预算和 Token 估算。"""

import pytest

from core.context import (
    ContextBudget,
    estimate_context_tokens,
    estimate_message_tokens,
)
from core.model import Message, ToolCall


def test_context_budget_exposes_compaction_threshold() -> None:
    budget = ContextBudget(
        context_window=1000,
        reserve_tokens=200,
        keep_recent_tokens=500,
    )

    assert budget.compaction_threshold == 800


@pytest.mark.parametrize(
    "kwargs",
    [
        {"context_window": 0, "reserve_tokens": 0, "keep_recent_tokens": 1},
        {"context_window": 100, "reserve_tokens": 100, "keep_recent_tokens": 1},
        {"context_window": 100, "reserve_tokens": 0, "keep_recent_tokens": 0},
    ],
)
def test_context_budget_rejects_invalid_values(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        ContextBudget(**kwargs)


def test_estimate_message_tokens_uses_four_characters_per_token() -> None:
    assert estimate_message_tokens(Message(role="user", content="a" * 9)) == 3


def test_estimate_message_tokens_includes_tool_call_arguments() -> None:
    message = Message(
        role="assistant",
        content="",
        tool_calls=(ToolCall("call-1", "read_file", {"path": "a.txt"}),),
    )

    assert estimate_message_tokens(message) > 0


def test_estimate_context_tokens_sums_messages() -> None:
    messages = [
        Message(role="user", content="a" * 4),
        Message(role="assistant", content="b" * 8),
    ]

    assert estimate_context_tokens(messages) == 3
