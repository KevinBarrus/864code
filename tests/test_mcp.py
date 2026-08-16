from collections.abc import Sequence

import pytest

from core.model import ToolCall, ToolResult
from core.tools import (
    McpToolRegistrationError,
    McpToolRegistry,
    ToolDefinition,
)


class FakeMcpProvider:
    """提供 MCP 注册表测试所需的最小假实现。"""

    async def list_tools(self) -> Sequence[ToolDefinition]:
        """返回一个测试工具定义。"""

        return []

    async def call_tool(self, tool_call: ToolCall) -> ToolResult:
        """返回一个测试工具结果。"""

        return ToolResult(tool_call.call_id, "完成")


def _definition(source: str = "mcp", name: str = "remote_tool") -> ToolDefinition:
    """构造测试用 MCP 工具定义。"""

    return ToolDefinition(
        name=name,
        description="远程工具",
        parameters={"type": "object"},
        source=source,  # type: ignore[arg-type]
        permission="read",
        idempotent=True,
    )


def test_mcp_registry_registers_and_lists_tools() -> None:
    """测试 MCP 注册表可以保存工具和提供者。"""

    provider = FakeMcpProvider()
    registry = McpToolRegistry()
    definition = _definition()

    registry.register(definition, provider)

    assert registry.get(definition.name) is not None
    assert registry.get(definition.name).provider is provider
    assert registry.definitions() == [definition]


def test_mcp_registry_rejects_invalid_source_and_duplicates() -> None:
    """测试 MCP 注册表拒绝本地工具和重复工具。"""

    provider = FakeMcpProvider()
    registry = McpToolRegistry()
    registry.register(_definition(), provider)

    with pytest.raises(McpToolRegistrationError, match="只能注册 mcp"):
        registry.register(_definition("local", "local_tool"), provider)
    with pytest.raises(McpToolRegistrationError, match="工具已注册"):
        registry.register(_definition(), provider)
