from collections.abc import Sequence

import pytest

from core.model import ToolCall, ToolResult
from core.tools import (
    McpToolRegistrationError,
    McpToolRegistry,
    RegisteredMcpTool,
    ToolRegistry,
    ToolDefinition,
    ToolManager,
    ToolRoute,
)
from core.tools.registry import LocalToolRegistry, ToolRegistrationError


class FakeMcpProvider:
    """提供 MCP 注册表测试所需的最小假实现。"""

    async def list_tools(self) -> Sequence[ToolDefinition]:
        """返回一个测试工具定义。"""

        return [_definition()]

    async def call_tool(self, tool_call: ToolCall) -> ToolResult:
        """返回一个测试工具结果。"""

        return ToolResult(tool_call.call_id, "完成")


def _definition(
    source: str = "mcp",
    name: str = "remote_tool",
    provider_id: str = "test-server",
) -> ToolDefinition:
    """构造测试用 MCP 工具定义。"""

    return ToolDefinition(
        name=name,
        description="远程工具",
        parameters={"type": "object"},
        source=source,  # type: ignore[arg-type]
        permission="read",
        idempotent=True,
        provider_id=provider_id,
    )


def test_mcp_registry_registers_and_lists_tools() -> None:
    """测试 MCP 注册表可以保存工具和提供者。"""

    provider = FakeMcpProvider()
    registry = McpToolRegistry()
    definition = ToolDefinition(
        name="remote_tool",
        description="远程工具",
        parameters={"type": "object"},
        source="mcp",
        permission="read",
        idempotent=True,
        provider_id="filesystem_server",
    )

    registry.register(definition, provider)

    assert registry.get("filesystem_server", definition.name) is not None
    assert registry.get("filesystem_server", definition.name).provider is provider
    assert registry.definitions() == [definition]
    assert definition.route == ToolRoute("mcp", "filesystem_server")


def test_mcp_registry_rejects_invalid_source_and_duplicates() -> None:
    """测试 MCP 注册表拒绝本地工具和重复工具。"""

    provider = FakeMcpProvider()
    registry = McpToolRegistry()
    registry.register(_definition(), provider)

    with pytest.raises(McpToolRegistrationError, match="只能注册 mcp"):
        registry.register(_definition("local", "local_tool"), provider)
    with pytest.raises(McpToolRegistrationError, match="工具已注册"):
        registry.register(_definition(), provider)


def test_unified_registry_rejects_duplicate_names_across_sources() -> None:
    """测试统一注册表拒绝不同来源的同名工具。"""

    provider = FakeMcpProvider()
    mcp_definition = _definition("mcp", "search_log")
    local_definition = _definition("local", "search_log")
    unified = ToolRegistry()
    local = LocalToolRegistry()

    async def local_handler(tool_call: ToolCall) -> ToolResult:
        """返回本地测试结果。"""

        return ToolResult(tool_call.call_id, "本地完成")

    local.register(local_definition, local_handler)
    local_binding = local.get("search_log")
    assert local_binding is not None
    unified.register(local_binding)

    with pytest.raises(ToolRegistrationError, match="工具已注册"):
        unified.register(RegisteredMcpTool(mcp_definition, provider))


@pytest.mark.asyncio
async def test_tool_manager_executes_mcp_binding_from_unified_registry() -> None:
    """测试工具管理器可以执行统一注册表中的 MCP 工具。"""

    provider = FakeMcpProvider()
    definition = _definition()
    registry = ToolRegistry()
    registry.register(RegisteredMcpTool(definition, provider))

    result = await ToolManager(registry=registry).execute(
        ToolCall("call-1", definition.name, {})
    )

    assert result == ToolResult("call-1", "完成")


@pytest.mark.asyncio
async def test_tool_manager_discovers_mcp_provider_tools() -> None:
    """测试工具管理器可以发现并注册 MCP 工具。"""

    manager = ToolManager()
    await manager.register_mcp_provider(FakeMcpProvider())

    assert [definition.name for definition in manager.list_definitions()] == [
        "mcp_test-server_remote_tool"
    ]


@pytest.mark.asyncio
async def test_tool_manager_routes_same_tool_name_to_its_mcp_provider() -> None:
    """测试两个 MCP Provider 的同名工具可以分别注册和执行。"""

    class NamedProvider:
        def __init__(self, provider_id: str) -> None:
            self.provider_id = provider_id
            self.calls: list[str] = []

        async def list_tools(self) -> Sequence[ToolDefinition]:
            return [_definition(name="search", provider_id=self.provider_id)]

        async def call_tool(self, tool_call: ToolCall) -> ToolResult:
            self.calls.append(tool_call.name)
            return ToolResult(tool_call.call_id, self.provider_id)

    first = NamedProvider("first")
    second = NamedProvider("second")
    manager = ToolManager()
    await manager.register_mcp_provider(first)
    await manager.register_mcp_provider(second)

    first_result = await manager.execute(ToolCall("call-1", "mcp_first_search", {}))
    second_result = await manager.execute(ToolCall("call-2", "mcp_second_search", {}))

    assert first_result.content == "first"
    assert second_result.content == "second"
    assert first.calls == ["search"]
    assert second.calls == ["search"]
