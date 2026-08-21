"""提供嵌入输入区域的单选选择组件。"""

import asyncio

from prompt_toolkit.formatted_text import AnyFormattedText
from prompt_toolkit.layout import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension


class ChoicePicker:
    """单选列表，可在末尾附加特殊选项（如 new config）。"""

    # 窗口优先高度减去标题行后的可见选项数，用于滚动跟随
    _VISIBLE_CHOICES = 6

    def __init__(
        self,
        items: list[str],
        title: str,
        extra_options: list[str] | None = None,
    ) -> None:
        """创建单选面板，title 为提示语，extra_options 追加在列表末尾。"""

        self._items = list(items)
        self._title = title
        self._extra_options = list(extra_options or [])
        self._cursor = 0
        self._result: asyncio.Future[str | None] = (
            asyncio.get_running_loop().create_future()
        )
        self.window = Window(
            content=FormattedTextControl(self._render, focusable=True),
            height=Dimension(min=3, preferred=8),
            dont_extend_height=True,
            wrap_lines=True,
            style="class:approval-area",
        )
        self.window.vertical_scroll = 0

    @property
    def _choices(self) -> list[str]:
        """返回全部可选项目（含尾部特殊选项）。"""

        return [*self._items, *self._extra_options]

    def move(self, offset: int) -> None:
        """移动光标，越界时循环到另一端并保持选中项可见。"""

        choices = self._choices
        if not choices:
            return
        self._cursor = (self._cursor + offset) % len(choices)
        self._follow_cursor()

    def _follow_cursor(self) -> None:
        """滚动窗口让当前光标项始终可见。"""

        max_scroll = max(0, len(self._choices) - self._VISIBLE_CHOICES)
        desired_scroll = max(0, self._cursor - (self._VISIBLE_CHOICES - 1))
        self.window.vertical_scroll = min(max_scroll, desired_scroll)

    def confirm(self) -> None:
        """确认当前光标项并返回选择结果。"""

        choices = self._choices
        if choices:
            self._resolve(choices[self._cursor])

    def cancel(self) -> None:
        """取消本次选择。"""

        self._resolve(None)

    async def wait(self) -> str | None:
        """等待用户完成选择。"""

        return await self._result

    def _resolve(self, result: str | None) -> None:
        """只允许选择结果被设置一次。"""

        if not self._result.done():
            self._result.set_result(result)

    def _render(self) -> AnyFormattedText:
        """渲染提示语和单选列表，选中行用 › 前缀。"""

        fragments: list[tuple[str, str]] = [("", f"{self._title}\n\n")]
        for index, choice in enumerate(self._choices):
            prefix = "› " if index == self._cursor else "  "
            style = "class:approval-selected" if index == self._cursor else ""
            fragments.append((style, f"{prefix}{choice}\n"))
        return fragments
