"""管理本地工具定义和执行器的对应关系。"""

from dataclasses import dataclass
from typing import Protocol

from ..model import ToolCall, ToolResult
from .types import ToolDefinition, ToolHandler


class ToolRegistrationError(ValueError):
    """工具注册失败时抛出的异常。"""


class ToolBinding(Protocol):
    """定义统一注册表需要保存的工具绑定能力。"""

    definition: ToolDefinition

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        """执行绑定的工具并返回统一结果。"""


@dataclass(frozen=True)
class RegisteredTool:
    """保存工具定义和对应的本地执行器。"""

    definition: ToolDefinition
    handler: ToolHandler

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        """调用本地工具处理函数。"""

        return await self.handler(tool_call)


class LocalToolRegistry:
    """保存本地工具，不处理工具执行流程和权限判断。"""

    def __init__(self) -> None:
        """创建空的本地工具注册表。"""

        self._tools: dict[str, RegisteredTool] = {}

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        """注册一个本地工具，重复名称直接拒绝。"""

        if definition.source != "local":
            raise ToolRegistrationError("本地注册表只能注册 local 工具")
        if definition.name in self._tools:
            raise ToolRegistrationError(f"工具已注册：{definition.name}")
        self._tools[definition.name] = RegisteredTool(definition, handler)

    def get(self, name: str) -> RegisteredTool | None:
        """根据名称查找本地工具。"""

        return self._tools.get(name)

    def definitions(self) -> list[ToolDefinition]:
        """返回已注册的本地工具定义。"""

        return [tool.definition for tool in self._tools.values()]


class ToolRegistry:
    """保存所有来源的工具绑定并检查模型可见名称冲突。"""

    def __init__(self) -> None:
        """创建空的统一工具注册表。"""

        self._tools: dict[str, ToolBinding] = {}

    def register(self, binding: ToolBinding) -> None:
        """注册一个工具绑定，模型可见名称必须全局唯一。"""

        name = binding.definition.name
        if name in self._tools:
            raise ToolRegistrationError(f"工具已注册：{name}")
        self._tools[name] = binding

    def get(self, name: str) -> ToolBinding | None:
        """根据模型可见名称查找工具绑定。"""

        return self._tools.get(name)

    def definitions(self) -> list[ToolDefinition]:
        """返回所有来源的工具定义。"""

        return [tool.definition for tool in self._tools.values()]
