from collections.abc import Awaitable, Callable

import pytest

from core.model import ToolCall, ToolResult
from core.tools import LocalToolRegistry, ToolDefinition, ToolManager
from core.tools.registry import ToolRegistrationError


def _definition(
    name: str = "read_file",
    source: str = "local",
) -> ToolDefinition:
    """构造测试用工具定义。"""

    return ToolDefinition(
        name=name,
        description="读取文件",
        parameters={"type": "object"},
        source=source,  # type: ignore[arg-type]
        permission="read",
        idempotent=True,
    )


def _handler(content: str = "完成") -> Callable[[ToolCall], Awaitable[ToolResult]]:
    """构造返回固定结果的测试执行器。"""

    async def execute(tool_call: ToolCall) -> ToolResult:
        return ToolResult(call_id=tool_call.call_id, content=content)

    return execute


def test_local_registry_registers_and_lists_tools() -> None:
    """测试本地注册表可以注册、查找和列出工具。"""

    registry = LocalToolRegistry()
    definition = _definition()
    registry.register(definition, _handler())

    assert registry.get("read_file") is not None
    assert registry.definitions() == [definition]


def test_local_registry_rejects_duplicate_or_non_local_tools() -> None:
    """测试本地注册表拒绝重复工具和 MCP 工具。"""

    registry = LocalToolRegistry()
    registry.register(_definition(), _handler())

    with pytest.raises(ToolRegistrationError, match="工具已注册"):
        registry.register(_definition(), _handler())
    with pytest.raises(ToolRegistrationError, match="只能注册 local"):
        registry.register(_definition("mcp_tool", "mcp"), _handler())


@pytest.mark.asyncio
async def test_tool_manager_executes_registered_tool() -> None:
    """测试工具管理器可以调度已注册工具。"""

    manager = ToolManager()
    manager.register_local(_definition(), _handler("文件内容"))

    result = await manager.execute(
        ToolCall(call_id="call-1", name="read_file", arguments={})
    )

    assert result == ToolResult(call_id="call-1", content="文件内容")


@pytest.mark.asyncio
async def test_tool_manager_returns_error_for_unknown_tool() -> None:
    """测试调用不存在的工具时返回结构化错误。"""

    result = await ToolManager().execute(
        ToolCall(call_id="call-1", name="missing", arguments={})
    )

    assert result.is_error is True
    assert result.call_id == "call-1"
    assert "工具不存在" in result.content


@pytest.mark.asyncio
async def test_tool_manager_converts_handler_error() -> None:
    """测试工具执行异常会转换为结构化错误。"""

    async def fail(tool_call: ToolCall) -> ToolResult:
        raise RuntimeError("读取失败")

    manager = ToolManager()
    manager.register_local(_definition(), fail)

    result = await manager.execute(
        ToolCall(call_id="call-1", name="read_file", arguments={})
    )

    assert result == ToolResult(
        call_id="call-1",
        content="工具执行失败：读取失败",
        is_error=True,
    )
