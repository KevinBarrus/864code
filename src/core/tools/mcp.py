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


class McpToolRegistry:
    """保存 MCP 工具，不负责通信、权限判断和工具执行。"""

    def __init__(self) -> None:
        """创建空的 MCP 工具注册表。"""

        self._tools: dict[str, RegisteredMcpTool] = {}

    def register(
        self,
        definition: ToolDefinition,
        provider: McpToolProvider,
    ) -> None:
        """注册一个 MCP 工具，重复名称直接拒绝。"""

        if definition.source != "mcp":
            raise McpToolRegistrationError("MCP 注册表只能注册 mcp 工具")
        if definition.name in self._tools:
            raise McpToolRegistrationError(f"工具已注册：{definition.name}")
        self._tools[definition.name] = RegisteredMcpTool(definition, provider)

    def get(self, name: str) -> RegisteredMcpTool | None:
        """根据名称查找 MCP 工具。"""

        return self._tools.get(name)

    def definitions(self) -> list[ToolDefinition]:
        """返回已注册的 MCP 工具定义。"""

        return [tool.definition for tool in self._tools.values()]
