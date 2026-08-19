"""统一调度已注册工具。"""

import asyncio
from dataclasses import replace

from ..errors import AgentError
from ..model import ToolCall, ToolResult
from .mcp import McpToolProvider, McpToolRegistry
from .mcp import RegisteredMcpTool
from .registry import RegisteredTool, ToolRegistry
from .permissions import ApprovalDecision, PermissionDenied, PermissionManager
from .types import ToolDefinition, ToolHandler
from .validation import ToolArgumentError, validate_tool_arguments


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
            model_name = f"mcp_{definition.provider_id}_{definition.name}"
            mcp_registry.register(
                replace(
                    definition,
                    name=model_name,
                    provider_tool_name=definition.name,
                ),
                provider,
            )
        for definition in mcp_registry.definitions():
            binding = mcp_registry.get(
                definition.provider_id,
                definition.provider_tool_name or definition.name,
            )
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
                error_category="invalid_request",
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
                    error_category="tool_permission",
                )
            return await registered.execute(tool_call)
        except asyncio.CancelledError:
            raise
        except ToolArgumentError as exc:
            return _tool_error_result(
                tool_call,
                AgentError(
                    category="invalid_request",
                    operation="tool_validation",
                    user_message=f"工具参数无效：{exc}",
                    model_message=f"工具参数无效：{exc}",
                    cause=exc,
                ),
            )
        except PermissionDenied as exc:
            return _tool_error_result(
                tool_call,
                AgentError(
                    category="tool_permission",
                    operation="tool_authorization",
                    user_message="工具调用被拒绝",
                    model_message=f"工具调用被拒绝：{exc}",
                    cause=exc,
                ),
            )
        except ValueError as exc:
            return _tool_error_result(
                tool_call,
                AgentError(
                    category="tool_execution",
                    operation="tool_execution",
                    user_message="工具执行失败",
                    model_message=f"工具执行失败：{exc}",
                    cause=exc,
                ),
            )
        except Exception as exc:
            return _tool_error_result(
                tool_call,
                AgentError(
                    category="tool_execution",
                    operation="tool_execution",
                    user_message="工具执行失败",
                    model_message="工具执行失败，请根据错误调整后续操作",
                    cause=exc,
                ),
            )


def _tool_error_result(tool_call: ToolCall, error: AgentError) -> ToolResult:
    """将内部工具异常转换为模型可见的安全结果。"""

    return ToolResult(
        call_id=tool_call.call_id,
        content=error.model_message or error.user_message,
        is_error=True,
        error_category=error.category,
    )
