"""统一调度已注册工具。"""

import asyncio

from ..model import ToolCall, ToolResult
from .registry import LocalToolRegistry
from .types import ToolDefinition, ToolHandler


class ToolManager:
    """负责本地工具的注册、查找和异常转换。"""

    def __init__(self, local_registry: LocalToolRegistry | None = None) -> None:
        """创建工具管理器，并准备本地工具注册表。"""

        self._local_registry = local_registry or LocalToolRegistry()

    def register_local(
        self,
        definition: ToolDefinition,
        handler: ToolHandler,
    ) -> None:
        """向本地工具层注册一个工具。"""

        self._local_registry.register(definition, handler)

    def list_definitions(self) -> list[ToolDefinition]:
        """返回当前已注册的工具定义。"""

        return self._local_registry.definitions()

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        """查找并执行工具，将普通异常转换为工具错误结果。"""

        registered = self._local_registry.get(tool_call.name)
        if registered is None:
            return ToolResult(
                call_id=tool_call.call_id,
                content=f"工具不存在：{tool_call.name}",
                is_error=True,
            )

        try:
            return await registered.handler(tool_call)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return ToolResult(
                call_id=tool_call.call_id,
                content=f"工具执行失败：{exc}",
                is_error=True,
            )
