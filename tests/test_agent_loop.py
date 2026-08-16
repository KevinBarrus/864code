from collections.abc import AsyncIterator, Sequence

import pytest

from core.agent_loop import AgentLoop, ToolExecutionEvent
from core.model import (
    Message,
    ModelEvent,
    TextDelta,
    ToolCall,
    ToolCallEvent,
)
from core.tools import ToolManager, create_read_file_tool


class FakeModelClient:
    """按请求次数返回工具调用和最终文本的模型客户端。"""

    def __init__(self) -> None:
        self.requests: list[list[Message]] = []
        self.tools: list[list[dict[str, object]]] = []

    async def stream_response(
        self,
        messages: Sequence[Message],
        tools: Sequence[dict[str, object]] = (),
    ) -> AsyncIterator[ModelEvent]:
        self.requests.append(list(messages))
        self.tools.append(list(tools))
        if len(self.requests) == 1:
            yield ToolCallEvent(
                ToolCall(
                    call_id="call-1",
                    name="read_file",
                    arguments={"path": "README.md"},
                )
            )
            return
        yield TextDelta("文件已经读取")


@pytest.mark.asyncio
async def test_agent_loop_executes_tool_and_continues_model_request(
    tmp_path,
) -> None:
    """测试 Agent Loop 执行工具后继续请求模型。"""

    (tmp_path / "README.md").write_text("项目说明", encoding="utf-8")
    client = FakeModelClient()
    manager = ToolManager()
    manager.register_local(*create_read_file_tool(tmp_path))
    events: list[object] = []

    async def collect_event(event: object) -> None:
        events.append(event)

    result = await AgentLoop(tool_manager=manager, client=client).run(
        [Message(role="user", content="读取说明")],
        on_event=collect_event,
    )

    assert result.final_content == "文件已经读取"
    assert result.messages[-1] == Message(role="assistant", content="文件已经读取")
    assert result.messages[-2] == Message(
        role="tool",
        content="项目说明",
        tool_call_id="call-1",
    )
    assert any(isinstance(event, ToolExecutionEvent) for event in events)
    assert len(client.requests) == 2
    assert client.tools[0][0]["function"]["name"] == "read_file"  # type: ignore[index]


@pytest.mark.asyncio
async def test_agent_loop_returns_unknown_tool_result_to_model() -> None:
    """测试未知工具不会被执行，而是将错误返回模型。"""

    class UnknownToolClient(FakeModelClient):
        async def stream_response(
            self,
            messages: Sequence[Message],
            tools: Sequence[dict[str, object]] = (),
        ) -> AsyncIterator[ModelEvent]:
            self.requests.append(list(messages))
            self.tools.append(list(tools))
            if len(self.requests) == 1:
                yield ToolCallEvent(
                    ToolCall("call-1", "missing", {})
                )
            else:
                yield TextDelta("工具不存在")

    client = UnknownToolClient()
    result = await AgentLoop(client, ToolManager()).run(
        [Message(role="user", content="调用未知工具")]
    )

    assert result.final_content == "工具不存在"
    assert "工具不存在：missing" in client.requests[1][-1].content
