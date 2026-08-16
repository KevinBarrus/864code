"""提供工具审批选择组件。"""

import asyncio

from prompt_toolkit.formatted_text import AnyFormattedText
from prompt_toolkit.layout import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension

from .model import ToolCall
from .tools.permissions import ApprovalDecision, ApprovalResult
from .tools.types import ToolDefinition


APPROVAL_OPTIONS = (
    "Yes, proceed",
    "Yes, and don't ask again for this tool in this session",
    "No, and tell the model what to do instead",
)


class ApprovalPrompt:
    """管理工具审批选项、键盘选择和异步结果。"""

    def __init__(self, definition: ToolDefinition, tool_call: ToolCall) -> None:
        """创建一次工具调用对应的审批面板。"""

        self.definition = definition
        self.tool_call = tool_call
        self.selected_index = 0
        self._result: asyncio.Future[ApprovalResult] = (
            asyncio.get_running_loop().create_future()
        )
        self.window = Window(
            content=FormattedTextControl(self._render, focusable=True),
            height=Dimension(min=4, preferred=4, max=4),
            dont_extend_height=True,
            style="class:approval-area",
        )

    def move(self, offset: int) -> None:
        """按方向移动选中项并限制在选项范围内。"""

        self.selected_index = max(
            0,
            min(len(APPROVAL_OPTIONS) - 1, self.selected_index + offset),
        )

    def confirm(self) -> None:
        """确认当前选项并结束审批等待。"""

        decisions = (
            ApprovalDecision.ALLOW_ONCE,
            ApprovalDecision.ALLOW_SESSION,
            ApprovalDecision.DENY,
        )
        self._resolve(ApprovalResult(decisions[self.selected_index]))

    def reject(self) -> None:
        """使用安全默认值拒绝当前工具调用。"""

        self._resolve(ApprovalResult(ApprovalDecision.DENY))

    async def wait(self) -> ApprovalResult:
        """等待用户完成当前审批。"""

        return await self._result

    def _resolve(self, result: ApprovalResult) -> None:
        """只允许审批结果被设置一次。"""

        if not self._result.done():
            self._result.set_result(result)

    def _render(self) -> AnyFormattedText:
        """渲染工具名和三项审批选项。"""

        fragments: list[tuple[str, str]] = [
            ("", f"Allow tool {self.definition.name}?\n"),
        ]
        for index, option in enumerate(APPROVAL_OPTIONS):
            style = "class:approval-selected" if index == self.selected_index else ""
            prefix = "> " if index == self.selected_index else "  "
            fragments.append((style, f"{prefix}{option}"))
            if index < len(APPROVAL_OPTIONS) - 1:
                fragments.append(("", "\n"))
        return fragments
