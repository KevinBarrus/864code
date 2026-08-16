"""管理本地工具定义和执行器的对应关系。"""

from dataclasses import dataclass

from ..model import ToolCall, ToolResult
from .types import ToolDefinition, ToolHandler


class ToolRegistrationError(ValueError):
    """工具注册失败时抛出的异常。"""


@dataclass(frozen=True)
class RegisteredTool:
    """保存工具定义和对应的本地执行器。"""

    definition: ToolDefinition
    handler: ToolHandler


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
