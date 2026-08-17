"""测试上下文预算和 Token 估算。"""

import pytest

from core.context import (
    ContextBudget,
    ContextBuildResult,
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
from core.session_store import CompactionRecord


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
        self.messages = []

    async def stream_chat(self, messages):
        self.messages.append(messages)
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
    assert "简短结构化摘要" in client.messages[1][0].content


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


@pytest.mark.asyncio
async def test_context_manager_build_for_model_uses_summary_when_over_budget() -> None:
    client = FakeSummaryClient([SUMMARY])
    manager = ContextManager(ContextBudget(4, 1, 2))
    messages = [
        Message(role="user", content="旧问题"),
        Message(role="assistant", content="旧回答"),
        Message(role="user", content="新问题"),
        Message(role="assistant", content="新回答"),
    ]

    result = await manager.build_for_model(client, messages)

    assert result[0].role == "system"
    assert "## Goal" in result[0].content
    assert result[1:] == messages[-2:]
    assert client.calls == 1


@pytest.mark.asyncio
async def test_context_manager_build_for_model_uses_fallback_after_summary_failure() -> None:
    client = FakeSummaryClient(
        [ModelClientError("网络错误"), ModelClientError("网络错误")]
    )
    manager = ContextManager(ContextBudget(4, 1, 2))
    messages = [
        Message(role="user", content="旧问题"),
        Message(role="assistant", content="旧回答"),
        Message(role="user", content="新问题"),
        Message(role="assistant", content="新回答"),
    ]

    result = await manager.build_for_model(client, messages)

    assert result[0] == Message(role="system", content=CONTEXT_FALLBACK_NOTICE)
    assert result[1:] == messages[-2:]
    assert client.calls == 2


@pytest.mark.asyncio
async def test_context_manager_marks_fallback_result() -> None:
    client = FakeSummaryClient(
        [ModelClientError("网络错误"), ModelClientError("网络错误")]
    )
    manager = ContextManager(ContextBudget(4, 1, 2))
    messages = [
        Message(role="user", content="旧问题"),
        Message(role="assistant", content="旧回答"),
        Message(role="user", content="新问题"),
        Message(role="assistant", content="新回答"),
    ]

    result = await manager.build_for_model_result(client, messages)

    assert result.fallback_used is True
    assert result.compaction is None


@pytest.mark.asyncio
async def test_second_compaction_boundary_uses_full_session_history() -> None:
    client = FakeSummaryClient([SUMMARY])
    manager = ContextManager(ContextBudget(4, 1, 2))
    messages = [
        Message(role="user", content="第一轮"),
        Message(role="assistant", content="第一轮回复"),
        Message(role="user", content="第二轮"),
        Message(role="assistant", content="第二轮回复"),
        Message(role="user", content="第三轮"),
        Message(role="assistant", content="第三轮回复"),
    ]
    previous = CompactionRecord("第一轮摘要", 2, 6)

    result = await manager.build_for_model_result(client, messages, [previous])

    assert result.compaction is not None
    assert result.compaction.first_kept_message_index == 4
    assert result.messages[-2:] == messages[-2:]


@pytest.mark.asyncio
async def test_context_manager_uses_latest_restored_compaction() -> None:
    client = FakeSummaryClient([])
    manager = ContextManager(ContextBudget(100, 10, 20))
    messages = [
        Message(role="user", content="旧问题"),
        Message(role="assistant", content="旧回答"),
        Message(role="user", content="保留的问题"),
        Message(role="assistant", content="保留的回答"),
    ]
    compaction = CompactionRecord("已经完成旧任务", 2, 100)

    result = await manager.build_for_model(client, messages, [compaction])

    assert result == [
        Message(role="system", content="Conversation summary:\n已经完成旧任务"),
        Message(role="user", content="保留的问题"),
        Message(role="assistant", content="保留的回答"),
    ]
    assert client.calls == 0


@pytest.mark.asyncio
async def test_context_manager_returns_compaction_record_after_summary() -> None:
    client = FakeSummaryClient([SUMMARY])
    manager = ContextManager(ContextBudget(4, 1, 2))
    messages = [
        Message(role="user", content="旧问题"),
        Message(role="assistant", content="旧回答"),
        Message(role="user", content="新问题"),
        Message(role="assistant", content="新回答"),
    ]

    result = await manager.build_for_model_result(client, messages)

    assert isinstance(result, ContextBuildResult)
    assert result.compaction is not None
    assert result.compaction.first_kept_message_index == 2
    assert result.compaction.tokens_before == 4
