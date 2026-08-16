"""统一调度已注册工具。"""

import asyncio

from ..model import ToolCall, ToolResult
from .mcp import McpToolProvider, McpToolRegistry
from .mcp import RegisteredMcpTool
from .registry import RegisteredTool, ToolRegistry
from .permissions import ApprovalDecision, PermissionDenied, PermissionManager
from .types import ToolDefinition, ToolHandler
from .validation import validate_tool_arguments


class ToolManager:
    """负责本地工具的注册、查找和异常转换。"""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        permission_manager: PermissionManager | None = None,
    ) -> None:
        """创建工具管理器，并准备注册表和权限管理器。"""

        self._registry = registry or ToolRegistry()
        self._permission_manager = permission_manager or PermissionManager()

    def register_local(
        self,
        definition: ToolDefinition,
        handler: ToolHandler,
    ) -> None:
        """向本地工具层注册一个工具。"""

        self._registry.register(RegisteredTool(definition, handler))

    def list_definitions(self) -> list[ToolDefinition]:
        """返回当前已注册的工具定义。"""

        return self._registry.definitions()

    async def register_mcp_provider(self, provider: McpToolProvider) -> None:
        """发现 MCP 工具并注册到统一工具注册表。"""

        mcp_registry = McpToolRegistry()
        for definition in await provider.list_tools():
            mcp_registry.register(definition, provider)
        for definition in mcp_registry.definitions():
            binding = mcp_registry.get(definition.name)
            assert isinstance(binding, RegisteredMcpTool)
            self._registry.register(binding)

    def model_tools(self) -> list[dict[str, object]]:
        """将已注册工具转换为模型工具定义。"""

        return [
            {
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": definition.parameters,
                },
            }
            for definition in self.list_definitions()
        ]

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        """查找并执行工具，将普通异常转换为工具错误结果。"""

        registered = self._registry.get(tool_call.name)
        if registered is None:
            return ToolResult(
                call_id=tool_call.call_id,
                content=f"工具不存在：{tool_call.name}",
                is_error=True,
            )

        try:
            validate_tool_arguments(registered.definition, tool_call)
            approval = await self._permission_manager.authorize(
                registered.definition,
                tool_call,
            )
            if approval.decision == ApprovalDecision.DENY:
                feedback = f" 用户反馈：{approval.feedback}" if approval.feedback else ""
                return ToolResult(
                    call_id=tool_call.call_id,
                    content=f"工具调用被拒绝。{feedback}".strip(),
                    is_error=True,
                )
            return await registered.execute(tool_call)
        except asyncio.CancelledError:
            raise
        except PermissionDenied as exc:
            return ToolResult(
                call_id=tool_call.call_id,
                content=f"工具调用被拒绝：{exc}",
                is_error=True,
            )
        except Exception as exc:
            return ToolResult(
                call_id=tool_call.call_id,
                content=f"工具执行失败：{exc}",
                is_error=True,
            )
