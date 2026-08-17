"""测试上下文预算和 Token 估算。"""

import pytest

from core.context import (
    ContextBudget,
    ContextCompactionRequired,
    ContextManager,
    estimate_context_tokens,
    estimate_message_tokens,
    select_recent_messages,
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


def test_context_manager_returns_copy_when_context_is_within_budget() -> None:
    messages = [Message(role="user", content="你好")]
    manager = ContextManager(ContextBudget(100, 10, 50))

    result = manager.build(messages)

    assert result == messages
    assert result is not messages


def test_context_manager_requires_compaction_when_context_exceeds_budget() -> None:
    manager = ContextManager(ContextBudget(10, 2, 5))

    with pytest.raises(ContextCompactionRequired):
        manager.build([Message(role="user", content="a" * 40)])


def test_select_recent_messages_keeps_system_and_latest_complete_turns() -> None:
    messages = [
        Message(role="system", content="系统规则"),
        Message(role="user", content="旧问题"),
        Message(role="assistant", content="旧回答"),
        Message(role="user", content="新问题"),
        Message(role="assistant", content="新回答"),
    ]

    selected = select_recent_messages(messages, max_tokens=2)

    assert selected == [
        Message(role="system", content="系统规则"),
        Message(role="user", content="新问题"),
        Message(role="assistant", content="新回答"),
    ]


def test_select_recent_messages_keeps_tool_call_and_results_together() -> None:
    messages = [
        Message(role="user", content="读取文件"),
        Message(
            role="assistant",
            content="",
            tool_calls=(ToolCall("call-1", "read_file", {"path": "a.txt"}),),
        ),
        Message(role="tool", content="文件内容", tool_call_id="call-1"),
        Message(role="assistant", content="读取完成"),
    ]

    selected = select_recent_messages(messages, max_tokens=1)

    assert selected == messages


def test_select_recent_messages_rejects_non_positive_budget() -> None:
    with pytest.raises(ValueError):
        select_recent_messages([], max_tokens=0)
