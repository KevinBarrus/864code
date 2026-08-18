import pytest

from core.errors import AgentError
from core.model import TextDelta, ToolCall, ToolCallEvent, ToolResult
from evaluation.fakes import FakeModelClient, FakeToolHandler


@pytest.mark.asyncio
async def test_fake_model_client_replays_events_and_records_requests() -> None:
    """测试模型替身按脚本返回事件并记录请求"""

    client = FakeModelClient([[TextDelta("完成")]])
    events = [event async for event in client.stream_response([])]

    assert events == [TextDelta("完成")]
    assert client.requests == [[]]
    assert client.tools == [[]]


@pytest.mark.asyncio
async def test_fake_model_client_can_inject_error() -> None:
    """测试模型替身可以注入异常"""

    error = AgentError("network", "model_request", "网络失败")
    client = FakeModelClient([error])

    with pytest.raises(AgentError, match="网络失败"):
        _ = [event async for event in client.stream_response([])]


@pytest.mark.asyncio
async def test_fake_tool_handler_replays_result_and_records_call() -> None:
    """测试工具替身按脚本返回结果并记录调用"""

    call = ToolCall("call-1", "read_file", {"path": "a.txt"})
    handler = FakeToolHandler([ToolResult("call-1", "文件内容")])

    result = await handler(call)

    assert result == ToolResult("call-1", "文件内容")
    assert handler.calls == [call]


@pytest.mark.asyncio
async def test_fake_tool_handler_can_inject_error() -> None:
    """测试工具替身可以注入执行异常"""

    handler = FakeToolHandler([RuntimeError("执行失败")])

    with pytest.raises(RuntimeError, match="执行失败"):
        await handler(ToolCall("call-1", "read_file", {}))
