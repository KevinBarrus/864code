"""实现工具权限判断和外部确认回调。"""

from collections.abc import Awaitable, Callable

from ..model import ToolCall
from .types import ToolDefinition


class PermissionDenied(PermissionError):
    """工具没有获得执行权限时抛出的异常。"""


ApprovalHandler = Callable[[ToolDefinition, ToolCall], Awaitable[bool]]


class PermissionManager:
    """集中判断工具是否可以执行，不依赖 TUI 实现。"""

    def __init__(self, approval_handler: ApprovalHandler | None = None) -> None:
        """记录由应用层注入的确认回调。"""

        self._approval_handler = approval_handler

    async def authorize(
        self,
        definition: ToolDefinition,
        tool_call: ToolCall,
    ) -> None:
        """自动放行只读工具，其它工具交给外部确认。"""

        if definition.permission == "read":
            return
        if self._approval_handler is None:
            raise PermissionDenied("该工具需要用户确认")
        if not await self._approval_handler(definition, tool_call):
            raise PermissionDenied("用户拒绝了工具调用")
