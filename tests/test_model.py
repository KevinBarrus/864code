from collections.abc import AsyncIterator, Sequence

import pytest

from core.model import Message, ModelClient, ToolCall, ToolResult


class FakeModelClient:
    """用于测试应用层是否只依赖 ModelClient 接口。"""

    async def stream_chat(
        self,
        messages: Sequence[Message],
    ) -> AsyncIterator[str]:
        """返回固定文本片段，模拟模型的流式响应。"""

        assert messages == [Message(role="user", content="你好")]
        yield "你"
        yield "好"


async def _collect(chunks: AsyncIterator[str]) -> str:
    """收集流式文本，模拟 UI 消费模型输出的方式。"""

    """收集流式文本，模拟 UI 消费模型输出的方式。"""

    result = ""
    async for chunk in chunks:
        result += chunk
    return result


@pytest.mark.asyncio
async def test_model_client_streams_text_chunks() -> None:
    """测试模型客户端接口可以被异步调用并消费流式文本。"""

    client: ModelClient = FakeModelClient()

    answer = await _collect(
        client.stream_chat([Message(role="user", content="你好")])
    )

    assert answer == "你好"


def test_message_supports_assistant_tool_calls() -> None:
    """测试 assistant 消息可以保存工具调用。"""

    tool_call = ToolCall(
        call_id="call-1",
        name="read_file",
        arguments={"path": "README.md"},
    )

    message = Message(
        role="assistant",
        content="",
        tool_calls=(tool_call,),
    )

    assert message.tool_calls == (tool_call,)


def test_tool_message_supports_tool_result_reference() -> None:
    """测试 tool 消息可以关联对应的工具调用。"""

    result = ToolResult(call_id="call-1", content="文件内容")
    message = Message(
        role="tool",
        content=result.content,
        tool_call_id=result.call_id,
    )

    assert message.role == "tool"
    assert message.tool_call_id == "call-1"
    assert result.is_error is False
