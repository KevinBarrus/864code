"""定义 MCP 工具提供者和注册表接口。"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ..model import ToolCall, ToolResult
from .types import ToolDefinition


class McpToolProvider(Protocol):
    """定义 MCP 服务向核心运行时提供的最小能力。"""

    async def list_tools(self) -> Sequence[ToolDefinition]:
        """返回 MCP 服务提供的工具定义。"""

    async def call_tool(self, tool_call: ToolCall) -> ToolResult:
        """执行一次 MCP 工具调用并返回统一结果。"""


class McpToolRegistrationError(ValueError):
    """MCP 工具注册失败时抛出的异常。"""


@dataclass(frozen=True)
class RegisteredMcpTool:
    """保存 MCP 工具定义和所属提供者。"""

    definition: ToolDefinition
    provider: McpToolProvider

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        """调用 MCP 提供者并返回统一工具结果。"""

        return await self.provider.call_tool(
            ToolCall(
                call_id=tool_call.call_id,
                name=self.definition.provider_tool_name or self.definition.name,
                arguments=tool_call.arguments,
            )
        )


class McpToolRegistry:
    """保存 MCP 工具，不负责通信、权限判断和工具执行。"""

    def __init__(self) -> None:
        """创建空的 MCP 工具注册表。"""

        self._tools: dict[tuple[str, str], RegisteredMcpTool] = {}

    def register(
        self,
        definition: ToolDefinition,
        provider: McpToolProvider,
    ) -> None:
        """按 Provider 和原始工具名注册一个 MCP 工具。"""

        if definition.source != "mcp":
            raise McpToolRegistrationError("mcp registry only accepts mcp tools")
        if not definition.provider_id or definition.provider_id == "builtin":
            raise McpToolRegistrationError("mcp tool is missing a valid provider_id")
        key = (definition.provider_id, definition.provider_tool_name or definition.name)
        if key in self._tools:
            raise McpToolRegistrationError(f"tool already registered: {key[1]}")
        self._tools[key] = RegisteredMcpTool(definition, provider)

    def get(self, provider_id: str, name: str) -> RegisteredMcpTool | None:
        """根据 Provider 和原始工具名查找 MCP 工具。"""

        return self._tools.get((provider_id, name))

    def definitions(self) -> list[ToolDefinition]:
        """返回已注册的 MCP 工具定义。"""

        return [tool.definition for tool in self._tools.values()]
