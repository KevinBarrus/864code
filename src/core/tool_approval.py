"""提供工具审批选择组件。"""

import asyncio
import json

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
COMMAND_APPROVAL_OPTIONS = (
    APPROVAL_OPTIONS[0],
    APPROVAL_OPTIONS[2],
)
ARGUMENT_PREVIEW_LIMIT = 120


class ApprovalPrompt:
    """管理工具审批选项、键盘选择和异步结果。"""

    def __init__(
        self,
        definition: ToolDefinition,
        tool_call: ToolCall,
        allow_session: bool = True,
    ) -> None:
        """创建一次工具调用对应的审批面板。"""

        self.definition = definition
        self.tool_call = tool_call
        self._options = APPROVAL_OPTIONS if allow_session else COMMAND_APPROVAL_OPTIONS
        self._decisions = (
            (ApprovalDecision.ALLOW_ONCE, ApprovalDecision.ALLOW_SESSION, ApprovalDecision.DENY)
            if allow_session
            else (ApprovalDecision.ALLOW_ONCE, ApprovalDecision.DENY)
        )
        self.selected_index = 0
        self._result: asyncio.Future[ApprovalResult] = (
            asyncio.get_running_loop().create_future()
        )
        self.window = Window(
            content=FormattedTextControl(self._render, focusable=True),
            height=Dimension(min=5, preferred=7),
            dont_extend_height=True,
            wrap_lines=True,
            style="class:approval-area",
        )

    def move(self, offset: int) -> None:
        """按方向移动选中项并限制在选项范围内。"""

        self.selected_index = max(
            0,
            min(len(self._options) - 1, self.selected_index + offset),
        )

    def confirm(self) -> None:
        """确认当前选项并结束审批等待。"""

        self._resolve(ApprovalResult(self._decisions[self.selected_index]))

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
        """渲染工具名、参数预览和三项审批选项。"""

        fragments: list[tuple[str, str]] = [
            ("", f"Allow tool {self.definition.name}?\n"),
            ("", f"{_format_arguments(self.tool_call)}\n"),
        ]
        for index, option in enumerate(self._options):
            style = "class:approval-selected" if index == self.selected_index else ""
            prefix = "> " if index == self.selected_index else "  "
            fragments.append((style, f"{prefix}{option}"))
            if index < len(self._options) - 1:
                fragments.append(("", "\n"))
        return fragments


def _format_arguments(tool_call: ToolCall) -> str:
    """生成供用户审批的工具参数预览。"""

    arguments = tool_call.arguments
    if tool_call.name == "run_command" and isinstance(arguments.get("command"), str):
        return f"Command: {arguments['command']}"
    if isinstance(arguments.get("path"), str):
        preview = [f"Path: {arguments['path']}"]
        for key in ("content", "old_content", "new_content"):
            value = arguments.get(key)
            if isinstance(value, str):
                preview.append(f"{key}: {_summarize(value)}")
        return " | ".join(preview)
    return f"Arguments: {_summarize(json.dumps(arguments, ensure_ascii=False, sort_keys=True))}"


def _summarize(value: str) -> str:
    """限制审批预览中的长文本，同时保留原始长度。"""

    compact = " ".join(value.split())
    if len(compact) <= ARGUMENT_PREVIEW_LIMIT:
        return compact
    return f"{compact[:ARGUMENT_PREVIEW_LIMIT - 1]}… ({len(value)} chars)"
