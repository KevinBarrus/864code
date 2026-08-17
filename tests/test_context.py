"""测试上下文预算和 Token 估算。"""

import pytest

from core.context import (
    ContextBudget,
    ContextCompactionRequired,
    ContextManager,
    ContextSummaryError,
    CONTEXT_FALLBACK_NOTICE,
    estimate_context_tokens,
    estimate_message_tokens,
    generate_context_summary,
    select_recent_messages,
)
from core.model import Message, ModelClientError, ToolCall


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


def test_context_manager_build_fallback_keeps_recent_messages_and_notice() -> None:
    messages = [
        Message(role="system", content="系统规则"),
        Message(role="user", content="旧问题"),
        Message(role="assistant", content="旧回答"),
        Message(role="user", content="新问题"),
        Message(role="assistant", content="新回答"),
    ]
    manager = ContextManager(ContextBudget(100, 10, 2))

    result = manager.build_fallback(messages)

    assert result == [
        Message(role="system", content="系统规则"),
        Message(role="system", content=CONTEXT_FALLBACK_NOTICE),
        Message(role="user", content="新问题"),
        Message(role="assistant", content="新回答"),
    ]
    assert messages[1].content == "旧问题"


def test_context_manager_build_fallback_keeps_tool_chain() -> None:
    messages = [
        Message(role="user", content="读取文件"),
        Message(
            role="assistant",
            content="",
            tool_calls=(ToolCall("call-1", "read_file", {"path": "a.txt"}),),
        ),
        Message(role="tool", content="文件内容", tool_call_id="call-1"),
    ]
    manager = ContextManager(ContextBudget(100, 10, 1))

    result = manager.build_fallback(messages)

    assert result[0] == Message(role="system", content=CONTEXT_FALLBACK_NOTICE)
    assert result[1:] == messages


class FakeSummaryClient:
    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = responses
        self.calls = 0

    async def stream_chat(self, messages):
        response = self.responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        yield response

    async def stream_response(self, messages, tools=()):
        raise AssertionError("摘要测试不应调用 stream_response")


SUMMARY = """## Goal
目标
## Progress
进展
## Key Decisions
决策
## Next Steps
下一步
## Critical Context
上下文
"""


@pytest.mark.asyncio
async def test_generate_context_summary_returns_structured_summary() -> None:
    client = FakeSummaryClient([SUMMARY])

    result = await generate_context_summary(
        client,
        [Message(role="user", content="完成任务")],
    )

    assert result == SUMMARY.strip()
    assert client.calls == 1


@pytest.mark.asyncio
async def test_generate_context_summary_retries_after_model_error() -> None:
    client = FakeSummaryClient([ModelClientError("网络错误"), SUMMARY])

    result = await generate_context_summary(
        client,
        [Message(role="user", content="完成任务")],
    )

    assert result == SUMMARY.strip()
    assert client.calls == 2


@pytest.mark.asyncio
async def test_generate_context_summary_raises_after_retries() -> None:
    client = FakeSummaryClient(
        [ModelClientError("网络错误"), SUMMARY.replace("## Critical Context", "")]
    )

    with pytest.raises(ContextSummaryError):
        await generate_context_summary(
            client,
            [Message(role="user", content="完成任务")],
        )

    assert client.calls == 2
